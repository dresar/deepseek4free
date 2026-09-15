from typing import Optional, Dict, Any, Generator, List, Union, Set, Callable
from pathlib import Path
import json
import time
import threading
import os
import re
import queue
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed, wait as futures_wait

from .api import (
    DeepSeekAPI,
    DeepSeekError,
    AuthenticationError,
    RateLimitError,
    NetworkError,
    CloudflareError,
    APIError,
)

try:
    import dotenv
except ImportError:
    dotenv = None


class TokenStatus(str, Enum):
    HEALTHY = "healthy"
    COOLDOWN = "cooldown"
    INVALID = "invalid"
    DISABLED = "disabled"


class PoolStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_RECENTLY_USED = "lru"


class PoolError(DeepSeekError):
    """Base exception for DeepSeekPool errors"""
    pass


class NoAvailableTokensError(PoolError):
    """Raised when no healthy tokens are available in the pool"""
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class TokenEntry:
    """Represents a single DeepSeek account token and its runtime state."""

    def __init__(
        self,
        token: str,
        name: Optional[str] = None,
        api_factory: Optional[Callable[[str], DeepSeekAPI]] = None,
    ):
        clean_token = token.strip().strip('"').strip("'")
        if not clean_token:
            raise ValueError("Token must be a non-empty string")

        self.token: str = clean_token
        self.name: str = name or self.mask_token(self.token)
        self.status: TokenStatus = TokenStatus.HEALTHY
        self.cooldown_until: float = 0.0
        self.last_used: float = 0.0
        self.latency_ms: float = 0.0
        self.consecutive_failures: int = 0
        self.total_requests: int = 0
        self.total_successes: int = 0
        self.total_errors: int = 0
        self.last_error: Optional[str] = None
        self.active_session_id: Optional[str] = None

        self._api: Optional[DeepSeekAPI] = None
        self._api_factory: Callable[[str], DeepSeekAPI] = api_factory or DeepSeekAPI
        self._lock = threading.RLock()

    @staticmethod
    def mask_token(token: str) -> str:
        """Mask a sensitive token string for logging or status display."""
        if not token:
            return ""
        if len(token) <= 8:
            return "****"
        return f"{token[:4]}...{token[-4:]}"

    def is_healthy(self) -> bool:
        """Check if token is healthy, automatically recovering expired cooldowns."""
        with self._lock:
            if self.status in (TokenStatus.INVALID, TokenStatus.DISABLED):
                return False
            if self.status == TokenStatus.COOLDOWN:
                if time.time() >= self.cooldown_until:
                    self.status = TokenStatus.HEALTHY
                    self.cooldown_until = 0.0
                    return True
                return False
            return self.status == TokenStatus.HEALTHY

    @property
    def cooldown_remaining(self) -> float:
        """Return remaining cooldown in seconds, or 0.0 if not in cooldown."""
        with self._lock:
            if self.status != TokenStatus.COOLDOWN:
                return 0.0
            return max(0.0, self.cooldown_until - time.time())

    def mark_cooldown(self, duration: float = 300.0, reason: str = "") -> None:
        """Mark this token as temporarily cooling down."""
        with self._lock:
            self.status = TokenStatus.COOLDOWN
            self.cooldown_until = time.time() + duration
            self.consecutive_failures += 1
            self.total_errors += 1
            self.last_error = reason

    def mark_invalid(self, reason: str = "") -> None:
        """Mark this token permanently invalid (e.g. 401 Unauthorized)."""
        with self._lock:
            self.status = TokenStatus.INVALID
            self.cooldown_until = 0.0
            self.consecutive_failures += 1
            self.total_errors += 1
            self.last_error = reason

    def mark_success(self, latency_ms: Optional[float] = None) -> None:
        """Record a successful request on this token."""
        with self._lock:
            self.consecutive_failures = 0
            self.total_successes += 1
            self.last_error = None
            if latency_ms is not None:
                self.latency_ms = latency_ms
            if self.status == TokenStatus.COOLDOWN:
                self.status = TokenStatus.HEALTHY
                self.cooldown_until = 0.0

    def get_api(self) -> DeepSeekAPI:
        """Get or lazily initialize the DeepSeekAPI client instance."""
        if self._api is None:
            with self._lock:
                if self._api is None:
                    self._api = self._api_factory(self.token)
        return self._api

    def get_or_create_session(self, force_new: bool = False) -> str:
        """Get existing session ID or create a fresh one for per-token session isolation."""
        with self._lock:
            if self.active_session_id is None or force_new:
                api = self.get_api()
                self.active_session_id = api.create_chat_session()
            return self.active_session_id

    def reset_session(self) -> str:
        """Force creation of a brand new chat session ID."""
        return self.get_or_create_session(force_new=True)

    def to_dict(self) -> Dict[str, Any]:
        """Export token statistics and status as a dictionary."""
        with self._lock:
            return {
                "name": self.name,
                "token_masked": self.mask_token(self.token),
                "status": self.status.value,
                "cooldown_remaining": round(self.cooldown_remaining, 1),
                "last_used": self.last_used,
                "latency_ms": round(self.latency_ms, 1),
                "total_requests": self.total_requests,
                "total_successes": self.total_successes,
                "total_errors": self.total_errors,
                "consecutive_failures": self.consecutive_failures,
                "has_active_session": bool(self.active_session_id),
                "last_error": self.last_error,
            }


class DeepSeekPool:
    """
    High-capacity token pool with load balancing, per-token session isolation,
    smart failover, automatic cooldown recovery, /boost acceleration, and /learn auto-discovery.
    """

    def __init__(
        self,
        tokens: Optional[Union[List[str], str]] = None,
        tokens_file: Optional[Union[str, Path]] = None,
        strategy: Union[str, PoolStrategy] = PoolStrategy.ROUND_ROBIN,
        cooldown_seconds: float = 300.0,
        max_retries: int = 3,
        env_file: Optional[Union[str, Path]] = None,
        api_factory: Optional[Callable[[str], DeepSeekAPI]] = None,
    ):
        self._tokens: List[TokenEntry] = []
        self._tokens_map: Dict[str, TokenEntry] = {}
        self._session_to_token: Dict[str, str] = {}
        self._rr_index: int = 0
        self._lock = threading.RLock()
        self._boost_enabled: bool = False

        if isinstance(strategy, str):
            strategy = PoolStrategy(strategy.lower())
        self.strategy: PoolStrategy = strategy

        self.cooldown_seconds: float = float(cooldown_seconds)
        self.max_retries: int = int(max_retries)
        self.api_factory: Optional[Callable[[str], DeepSeekAPI]] = api_factory
        self.source_file: Optional[Path] = None
        self.last_used_token: Optional[str] = None
        self.last_used_session_id: Optional[str] = None

        if tokens:
            if isinstance(tokens, str):
                tokens_list = [t.strip() for t in tokens.replace(";", ",").split(",") if t.strip()]
            else:
                tokens_list = [str(t).strip() for t in tokens if str(t).strip()]
            for tok in tokens_list:
                self.add_token(tok)

        elif tokens_file:
            path = Path(tokens_file)
            self.load_tokens_from_file(path)
            self.source_file = path

        else:
            loaded_count = self._discover_and_load_tokens(env_file=env_file)
            if loaded_count == 0:
                self._load_from_env(env_file=env_file)

    def _discover_and_load_tokens(self, env_file: Optional[Union[str, Path]] = None) -> int:
        """Search current working directory and module directory for tokens file."""
        candidates = [
            Path("tokens.txt"),
            Path(__file__).resolve().parent.parent / "tokens.txt",
            Path("tokens.json"),
            Path(__file__).resolve().parent.parent / "tokens.json",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                try:
                    count = self.load_tokens_from_file(candidate)
                    if count > 0:
                        self.source_file = candidate
                        return count
                except Exception:
                    pass
        return 0

    def _load_from_env(self, env_file: Optional[Union[str, Path]] = None) -> int:
        """Load fallback token from environment variables or .env file."""
        if dotenv:
            if env_file and Path(env_file).exists():
                dotenv.load_dotenv(env_file)
            else:
                default_env = Path(__file__).resolve().parent.parent / ".env"
                if default_env.exists():
                    dotenv.load_dotenv(default_env)
                else:
                    dotenv.load_dotenv()

        auth_tokens_env = os.getenv("DEEPSEEK_AUTH_TOKENS") or os.getenv("DEEPSEEK_TOKENS")
        if auth_tokens_env:
            tokens_list = [t.strip() for t in auth_tokens_env.replace(";", ",").split(",") if t.strip()]
            for tok in tokens_list:
                self.add_token(tok)
            return len(tokens_list)

        single_token = os.getenv("DEEPSEEK_AUTH_TOKEN")
        if single_token and single_token.strip():
            self.add_token(single_token.strip())
            return 1

        return 0

    def load_tokens_from_file(self, filepath: Union[str, Path]) -> int:
        """
        Load tokens from a file (.txt or .json).
        - .txt: One token per line (strips comments # or //, ignores empty lines).
        - .json: List of strings, list of objects with 'token' key, or dict.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Tokens file not found: {path}")

        count = 0
        suffix = path.suffix.lower()

        if suffix == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw_tokens: List[Dict[str, str]] = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        raw_tokens.append({"token": item.strip()})
                    elif isinstance(item, dict) and "token" in item:
                        raw_tokens.append({
                            "token": str(item["token"]).strip(),
                            "name": item.get("name")
                        })
            elif isinstance(data, dict):
                if "tokens" in data and isinstance(data["tokens"], list):
                    for item in data["tokens"]:
                        if isinstance(item, str):
                            raw_tokens.append({"token": item.strip()})
                        elif isinstance(item, dict) and "token" in item:
                            raw_tokens.append({
                                "token": str(item["token"]).strip(),
                                "name": item.get("name")
                            })
                else:
                    for k, v in data.items():
                        if isinstance(v, str):
                            raw_tokens.append({"token": v.strip(), "name": str(k)})

            for tok_info in raw_tokens:
                if self.add_token(tok_info["token"], name=tok_info.get("name")):
                    count += 1

        else:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    # Strip inline comments
                    for marker in ("#", "//"):
                        if marker in stripped:
                            stripped = stripped.split(marker, 1)[0].strip()
                    clean_tok = stripped.strip('"\' ,;')
                    if clean_tok:
                        if self.add_token(clean_tok):
                            count += 1

        self.source_file = path
        return count

    def add_token(
        self,
        token: str,
        name: Optional[str] = None,
        save_to_file: bool = False
    ) -> bool:
        """Add a new token to the pool. Returns True if added, False if duplicate."""
        clean_token = token.strip().strip('"').strip("'")
        if not clean_token:
            return False

        with self._lock:
            if clean_token in self._tokens_map:
                return False

            entry = TokenEntry(
                token=clean_token,
                name=name,
                api_factory=self.api_factory
            )
            self._tokens.append(entry)
            self._tokens_map[clean_token] = entry

        if save_to_file and self.source_file:
            self.save_tokens(self.source_file)

        return True

    def remove_token(self, token: str, save_to_file: bool = False) -> bool:
        """Remove a token from the pool. Returns True if removed."""
        clean_token = token.strip().strip('"').strip("'")
        with self._lock:
            entry = self._tokens_map.pop(clean_token, None)
            if not entry:
                return False
            self._tokens = [e for e in self._tokens if e.token != clean_token]
            self._session_to_token = {
                sess: tok for sess, tok in self._session_to_token.items() if tok != clean_token
            }
            if self.last_used_token == clean_token:
                self.last_used_token = None

        if save_to_file and self.source_file:
            self.save_tokens(self.source_file)

        return True

    def get_tokens(self, only_healthy: bool = False) -> List[str]:
        """Return list of tokens in pool, optionally filtering for healthy only."""
        with self._lock:
            if only_healthy:
                return [e.token for e in self._tokens if e.is_healthy()]
            return [e.token for e in self._tokens]

    def save_tokens(
        self,
        filepath: Optional[Union[str, Path]] = None,
        format: Optional[str] = None
    ) -> None:
        """Save all tokens currently in pool to a file."""
        target_path = Path(filepath) if filepath else self.source_file
        if not target_path:
            target_path = Path("tokens.txt")

        target_format = (format or target_path.suffix.lstrip(".")).lower()

        with self._lock:
            tokens_to_save = list(self._tokens)

        if target_format == "json":
            data = [
                {"token": e.token, "name": e.name}
                for e in tokens_to_save
            ]
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        else:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write("# DeepSeek Tokens Pool (Generated)\n")
                for e in tokens_to_save:
                    f.write(f"{e.token}\n")

        self.source_file = target_path

    def get_healthy_tokens(self) -> List[TokenEntry]:
        """Get all currently healthy tokens, automatically recovering expired cooldowns."""
        with self._lock:
            return [e for e in self._tokens if e.is_healthy()]

    def get_next_token(self, exclude_tokens: Optional[Set[str]] = None) -> TokenEntry:
        """
        Select next healthy token using configured strategy (Round-Robin or LRU).
        Raises NoAvailableTokensError if all tokens are in cooldown or invalid.
        """
        exclude = exclude_tokens or set()

        with self._lock:
            if not self._tokens:
                raise NoAvailableTokensError("No tokens registered in DeepSeekPool.")

            # Filter healthy candidates not in exclude set
            candidates = [
                e for e in self._tokens
                if e.is_healthy() and e.token not in exclude
            ]

            if not candidates:
                # Check cooling down tokens
                cooldown_tokens = [
                    e for e in self._tokens
                    if e.status == TokenStatus.COOLDOWN and e.token not in exclude
                ]
                if cooldown_tokens:
                    min_wait = min(e.cooldown_remaining for e in cooldown_tokens)
                    raise NoAvailableTokensError(
                        f"All tokens are currently cooling down. Next token available in {min_wait:.1f}s.",
                        retry_after=min_wait
                    )
                raise NoAvailableTokensError("No healthy or available tokens in pool.")

            # Apply Strategy
            if self.strategy == PoolStrategy.LEAST_RECENTLY_USED:
                selected = min(candidates, key=lambda e: e.last_used)
            else:
                # Monotonic fair Round-Robin selection
                selected = candidates[self._rr_index % len(candidates)]
                self._rr_index += 1

            selected.last_used = time.time()
            selected.total_requests += 1
            self.last_used_token = selected.token
            return selected

    def create_chat_session(self, token: Optional[str] = None) -> str:
        """
        Create a new chat session. If token is specified, creates on that token;
        otherwise selects the next healthy token.
        Registers the session with the token for session affinity.
        """
        with self._lock:
            if token:
                clean_tok = token.strip().strip('"').strip("'")
                entry = self._tokens_map.get(clean_tok)
                if not entry:
                    raise ValueError(f"Token not found in pool: {TokenEntry.mask_token(clean_tok)}")
                session_id = entry.reset_session()
                self._session_to_token[session_id] = entry.token
                self.last_used_session_id = session_id
                self.last_used_token = entry.token
                return session_id

        entry = self.get_next_token()
        session_id = entry.reset_session()
        with self._lock:
            self._session_to_token[session_id] = entry.token
            self.last_used_session_id = session_id
            self.last_used_token = entry.token
        return session_id

    def get_chat_session(self, token: str) -> str:
        """Get or create active chat session ID for a specific token (session isolation)."""
        with self._lock:
            clean_tok = token.strip().strip('"').strip("'")
            entry = self._tokens_map.get(clean_tok)
            if not entry:
                raise ValueError(f"Token not found in pool: {TokenEntry.mask_token(clean_tok)}")
            session_id = entry.get_or_create_session()
            self._session_to_token[session_id] = entry.token
            return session_id

    def reset_all_sessions(self) -> None:
        """Reset active chat session IDs across all tokens in pool."""
        with self._lock:
            for entry in self._tokens:
                entry.active_session_id = None
            self._session_to_token.clear()
            self.last_used_session_id = None

    def validate_token(
        self,
        token_or_entry: Union[str, TokenEntry],
        update_status: bool = True
    ) -> bool:
        """
        Validate a single token by attempting to create a chat session.
        Measures response latency and updates health status.
        """
        if isinstance(token_or_entry, TokenEntry):
            entry = token_or_entry
        else:
            clean_tok = token_or_entry.strip().strip('"').strip("'")
            with self._lock:
                entry = self._tokens_map.get(clean_tok)
                if not entry:
                    entry = TokenEntry(clean_tok, api_factory=self.api_factory)

        start_time = time.time()
        try:
            api = entry.get_api()
            session_id = api.create_chat_session()
            lat_ms = (time.time() - start_time) * 1000.0
            if session_id:
                entry.active_session_id = session_id
                with self._lock:
                    self._session_to_token[session_id] = entry.token
                if update_status:
                    entry.mark_success(latency_ms=lat_ms)
                return True
            return False

        except AuthenticationError as e:
            if update_status:
                entry.mark_invalid(reason=f"401 Authentication Failed: {str(e)}")
            return False

        except RateLimitError as e:
            if update_status:
                entry.mark_cooldown(self.cooldown_seconds, reason=f"429 Rate Limit: {str(e)}")
            return False

        except Exception as e:
            if update_status:
                entry.mark_cooldown(min(60.0, self.cooldown_seconds), reason=f"Validation Error: {str(e)}")
            return False

    def validate_all_tokens(
        self,
        concurrent: bool = True,
        max_workers: int = 5
    ) -> Dict[str, bool]:
        """Validate all tokens in the pool. Returns dict mapping masked token to validity status."""
        with self._lock:
            tokens_list = list(self._tokens)

        results: Dict[str, bool] = {}

        if not concurrent or len(tokens_list) <= 1:
            for entry in tokens_list:
                valid = self.validate_token(entry)
                results[entry.name] = valid
            return results

        workers = min(max_workers, len(tokens_list))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_entry = {
                executor.submit(self.validate_token, entry): entry
                for entry in tokens_list
            }
            for future in as_completed(future_to_entry):
                entry = future_to_entry[future]
                try:
                    valid = future.result()
                except Exception:
                    valid = False
                results[entry.name] = valid

        return results

    def set_boost(self, enabled: bool = True) -> bool:
        """Toggle /boost acceleration mode for the token pool."""
        self._boost_enabled = bool(enabled)
        return self._boost_enabled

    @property
    def boost_enabled(self) -> bool:
        return self._boost_enabled

    def boost_completion(
        self,
        prompt_or_session: Optional[str] = None,
        prompt: Optional[str] = None,
        chat_session_id: Optional[str] = None,
        hedge_count: int = 2,
        **kwargs: Any
    ) -> Generator[Dict[str, Any], None, None]:
        """
        /boost Mode: Accelerated completion using multi-account hedged racing.
        When 2+ healthy accounts are available, queries top accounts concurrently;
        the fastest account to yield initial output streams the completion, slashing latency.
        """
        with self._lock:
            healthy = [e for e in self._tokens if e.is_healthy()]

        if len(healthy) < 2:
            yield from self.chat_completion(
                prompt_or_session=prompt_or_session,
                prompt=prompt,
                chat_session_id=chat_session_id,
                boost=False,
                **kwargs
            )
            return

        # Select candidate tokens for hedged racing
        race_tokens = healthy[:min(hedge_count, len(healthy))]
        out_queue: queue.Queue = queue.Queue()
        stop_event = threading.Event()
        winner_token: List[Optional[str]] = [None]

        def _runner(entry: TokenEntry):
            try:
                sess_id = entry.get_or_create_session()
                api = entry.get_api()
                actual_p = prompt if prompt is not None else prompt_or_session
                stream = api.chat_completion(chat_session_id=sess_id, prompt=actual_p, **kwargs)
                first = True
                for chunk in stream:
                    if stop_event.is_set() and winner_token[0] != entry.token:
                        break
                    if first:
                        first = False
                        if winner_token[0] is None:
                            winner_token[0] = entry.token
                            stop_event.set()
                        elif winner_token[0] != entry.token:
                            break
                        entry.mark_success()
                    out_queue.put((entry.token, chunk, None))
                out_queue.put((entry.token, None, None))
            except Exception as e:
                out_queue.put((entry.token, None, e))

        threads = [threading.Thread(target=_runner, args=(t,), daemon=True) for t in race_tokens]
        for t in threads:
            t.start()

        active_runners = len(threads)
        winning_id: Optional[str] = None

        while active_runners > 0:
            try:
                tok_id, chunk, err = out_queue.get(timeout=30.0)
            except queue.Empty:
                break

            if err is not None:
                active_runners -= 1
                continue

            if chunk is None:
                if tok_id == winning_id:
                    break
                active_runners -= 1
                continue

            if winning_id is None:
                winning_id = tok_id
                self.last_used_token = winning_id

            if tok_id == winning_id:
                yield chunk

    def boost_batch(
        self,
        prompts: List[str],
        max_concurrency: Optional[int] = None,
        thinking_enabled: bool = False,
        **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """
        /boost Mode: Parallel batch processor across available healthy pool tokens.
        Executes multiple prompts concurrently across separate accounts.
        """
        with self._lock:
            healthy_count = sum(1 for e in self._tokens if e.is_healthy())
        if healthy_count == 0:
            raise NoAvailableTokensError("No healthy tokens available for batch execution.")

        workers = min(max_concurrency or healthy_count, len(prompts), 32)
        results: List[Dict[str, Any]] = [{} for _ in prompts]

        def _worker(idx: int, p: str):
            text_chunks = []
            thinking_chunks = []
            used_tok = None
            err_str = None
            try:
                for chunk in self.chat_completion(prompt=p, thinking_enabled=thinking_enabled, boost=False, **kwargs):
                    used_tok = self.last_used_token
                    if chunk.get("type") == "thinking":
                        thinking_chunks.append(chunk.get("content", ""))
                    elif chunk.get("type") == "text":
                        text_chunks.append(chunk.get("content", ""))
            except Exception as e:
                err_str = str(e)

            results[idx] = {
                "prompt": p,
                "text": "".join(text_chunks),
                "thinking": "".join(thinking_chunks),
                "token": used_tok,
                "error": err_str,
            }

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_worker, i, prompt) for i, prompt in enumerate(prompts)]
            futures_wait(futures)

        return results

    def learn(
        self,
        sources: Optional[List[Union[str, Path]]] = None,
        auto_add: bool = True,
        benchmark: bool = True
    ) -> Dict[str, Any]:
        """
        /learn Mode: Auto-discovery, harvesting, latency benchmarking, and health calibration.
        Discovers tokens from files, .env, and environment; validates and learns response profiles.
        """
        discovered_tokens: Set[str] = set()

        candidate_files: List[Path] = [
            Path("tokens.txt"),
            Path("tokens.json"),
            Path(".env"),
            Path("tokens.txt.example"),
            Path("tokens.json.example"),
            Path(__file__).resolve().parent.parent / "tokens.txt",
            Path(__file__).resolve().parent.parent / "tokens.json",
            Path(__file__).resolve().parent.parent / ".env",
        ]
        if sources:
            for s in sources:
                candidate_files.append(Path(s))

        token_regex = re.compile(r'([A-Za-z0-9_\-\+\/]{20,128})')

        for cpath in candidate_files:
            if cpath.exists() and cpath.is_file():
                try:
                    if cpath.suffix.lower() == ".json":
                        with open(cpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, str) and len(item.strip()) >= 20:
                                    discovered_tokens.add(item.strip())
                                elif isinstance(item, dict) and "token" in item:
                                    discovered_tokens.add(str(item["token"]).strip())
                        elif isinstance(data, dict):
                            for v in data.values():
                                if isinstance(v, str) and len(v.strip()) >= 20:
                                    discovered_tokens.add(v.strip())
                    else:
                        with open(cpath, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if not line or line.startswith("#"):
                                    continue
                                for marker in ("#", "//"):
                                    if marker in line:
                                        line = line.split(marker, 1)[0].strip()
                                matches = token_regex.findall(line)
                                for match in matches:
                                    if len(match) >= 20 and not match.startswith("http"):
                                        discovered_tokens.add(match)
                except Exception:
                    pass

        # Scan environment variables
        for env_key in ("DEEPSEEK_AUTH_TOKEN", "DEEPSEEK_AUTH_TOKENS", "DEEPSEEK_TOKENS"):
            env_val = os.getenv(env_key)
            if env_val:
                for match in token_regex.findall(env_val):
                    if len(match) >= 20:
                        discovered_tokens.add(match)

        added_count = 0
        if auto_add:
            for tok in discovered_tokens:
                if self.add_token(tok):
                    added_count += 1

        if benchmark and self._tokens:
            self.validate_all_tokens(concurrent=True)

        with self._lock:
            healthy_entries = [e for e in self._tokens if e.is_healthy()]
            total_lat = sum(e.latency_ms for e in healthy_entries if e.latency_ms > 0)
            lat_count = sum(1 for e in healthy_entries if e.latency_ms > 0)
            avg_lat = round(total_lat / lat_count, 1) if lat_count > 0 else 0.0

            fastest = min((e for e in healthy_entries if e.latency_ms > 0), key=lambda e: e.latency_ms, default=None)

            report = {
                "discovered_count": len(discovered_tokens),
                "added_to_pool": added_count,
                "pool_total": len(self._tokens),
                "healthy_count": len(healthy_entries),
                "cooldown_count": sum(1 for e in self._tokens if e.status == TokenStatus.COOLDOWN),
                "invalid_count": sum(1 for e in self._tokens if e.status == TokenStatus.INVALID),
                "average_latency_ms": avg_lat,
                "fastest_account": fastest.name if fastest else None,
                "token_profiles": [e.to_dict() for e in self._tokens],
            }

        return report

    def get_performance_profile(self) -> Dict[str, Any]:
        """Return learned performance metrics across the entire token pool."""
        with self._lock:
            healthy = [e for e in self._tokens if e.is_healthy()]
            total_requests = sum(e.total_requests for e in self._tokens)
            total_successes = sum(e.total_successes for e in self._tokens)
            total_errors = sum(e.total_errors for e in self._tokens)
            latencies = [e.latency_ms for e in healthy if e.latency_ms > 0]
            avg_lat = round(sum(latencies) / len(latencies), 1) if latencies else 0.0

            return {
                "total_accounts": len(self._tokens),
                "healthy_accounts": len(healthy),
                "total_requests": total_requests,
                "total_successes": total_successes,
                "total_errors": total_errors,
                "success_rate_percent": round((total_successes / total_requests * 100.0), 1) if total_requests > 0 else 100.0,
                "average_latency_ms": avg_lat,
                "boost_active": self._boost_enabled,
                "strategy": self.strategy.value,
            }

    def chat_completion(
        self,
        prompt_or_session: Optional[str] = None,
        prompt: Optional[str] = None,
        chat_session_id: Optional[str] = None,
        parent_message_id: Optional[str] = None,
        thinking_enabled: bool = True,
        search_enabled: bool = False,
        max_retries: Optional[int] = None,
        new_session: bool = False,
        boost: bool = False,
        **kwargs: Any
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Send a chat message with automatic token rotation, session affinity, smart failover, and streaming.

        Compatible with DeepSeekAPI.chat_completion signatures:
          pool.chat_completion("What is 2+2?")
          pool.chat_completion(session_id, "What is 2+2?")
          pool.chat_completion(prompt="What is 2+2?", thinking_enabled=True)
          pool.chat_completion(prompt="What is 2+2?", boost=True)
        """
        if boost or self._boost_enabled:
            yield from self.boost_completion(
                prompt_or_session=prompt_or_session,
                prompt=prompt,
                chat_session_id=chat_session_id,
                parent_message_id=parent_message_id,
                thinking_enabled=thinking_enabled,
                search_enabled=search_enabled,
                **kwargs
            )
            return

        # Resolve prompt and session arguments
        if prompt is not None:
            actual_prompt = prompt
            actual_session_id = chat_session_id or prompt_or_session
        else:
            actual_prompt = prompt_or_session
            actual_session_id = chat_session_id

        if not actual_prompt or not isinstance(actual_prompt, str):
            raise ValueError("Prompt must be a non-empty string")

        with self._lock:
            pool_size = len(self._tokens)

        if pool_size == 0:
            raise NoAvailableTokensError("No tokens available in DeepSeekPool. Please add tokens or check .env.")

        effective_max_retries = max_retries if max_retries is not None else min(max(self.max_retries, 1), max(pool_size, 1))

        # Check session affinity: does actual_session_id belong to a specific token?
        preferred_entry: Optional[TokenEntry] = None
        if actual_session_id:
            with self._lock:
                owner_token_str = self._session_to_token.get(actual_session_id)
                if owner_token_str and owner_token_str in self._tokens_map:
                    candidate = self._tokens_map[owner_token_str]
                    if candidate.is_healthy():
                        preferred_entry = candidate
                if not preferred_entry:
                    for entry in self._tokens:
                        if entry.active_session_id == actual_session_id and entry.is_healthy():
                            preferred_entry = entry
                            self._session_to_token[actual_session_id] = entry.token
                            break

        attempted_tokens: Set[str] = set()
        chunks_yielded = 0
        last_exception: Optional[Exception] = None

        for attempt in range(effective_max_retries):
            if attempt == 0 and preferred_entry is not None:
                token_entry = preferred_entry
                target_session = actual_session_id
            else:
                try:
                    token_entry = self.get_next_token(exclude_tokens=attempted_tokens)
                except NoAvailableTokensError as e:
                    last_exception = e
                    break

                try:
                    if new_session:
                        target_session = token_entry.reset_session()
                    else:
                        target_session = token_entry.get_or_create_session()
                    with self._lock:
                        self._session_to_token[target_session] = token_entry.token
                except RateLimitError as e:
                    token_entry.mark_cooldown(self.cooldown_seconds, reason=f"429 Session Create: {str(e)}")
                    last_exception = e
                    attempted_tokens.add(token_entry.token)
                    continue
                except AuthenticationError as e:
                    token_entry.mark_invalid(reason=f"401 Session Create: {str(e)}")
                    last_exception = e
                    attempted_tokens.add(token_entry.token)
                    continue
                except Exception as e:
                    token_entry.mark_cooldown(min(60.0, self.cooldown_seconds), reason=f"Session Create Error: {str(e)}")
                    last_exception = e
                    attempted_tokens.add(token_entry.token)
                    continue

            attempted_tokens.add(token_entry.token)
            self.last_used_token = token_entry.token
            self.last_used_session_id = target_session

            # Stream response chunks from selected token
            try:
                api = token_entry.get_api()
                start_req = time.time()
                stream = api.chat_completion(
                    chat_session_id=target_session,
                    prompt=actual_prompt,
                    parent_message_id=parent_message_id,
                    thinking_enabled=thinking_enabled,
                    search_enabled=search_enabled,
                    **kwargs
                )

                first_chunk = True
                for chunk in stream:
                    if first_chunk:
                        first_chunk = False
                        lat = (time.time() - start_req) * 1000.0
                        token_entry.mark_success(latency_ms=lat)
                    chunks_yielded += 1
                    yield chunk

                # Completed full stream successfully
                return

            except RateLimitError as e:
                token_entry.mark_cooldown(self.cooldown_seconds, reason=f"429 RateLimit: {str(e)}")
                last_exception = e
                if chunks_yielded > 0:
                    raise e
                continue

            except AuthenticationError as e:
                token_entry.mark_invalid(reason=f"401 AuthError: {str(e)}")
                last_exception = e
                if chunks_yielded > 0:
                    raise e
                continue

            except (APIError, NetworkError, CloudflareError) as e:
                token_entry.mark_cooldown(min(60.0, self.cooldown_seconds), reason=f"API/Network Error: {str(e)}")
                last_exception = e
                if chunks_yielded > 0:
                    raise e
                continue

            except Exception as e:
                token_entry.mark_cooldown(min(60.0, self.cooldown_seconds), reason=f"Unexpected: {str(e)}")
                last_exception = e
                if chunks_yielded > 0:
                    raise e
                continue

        with self._lock:
            healthy_tokens = [e for e in self._tokens if e.is_healthy()]
            if not healthy_tokens and self._tokens:
                cooldown_tokens = [e for e in self._tokens if e.status == TokenStatus.COOLDOWN]
                if cooldown_tokens:
                    min_wait = min(e.cooldown_remaining for e in cooldown_tokens)
                    raise NoAvailableTokensError(
                        f"All tokens in pool are currently cooling down. Next token available in {min_wait:.1f}s. (Last error: {last_exception})",
                        retry_after=min_wait
                    )
                raise NoAvailableTokensError(
                    f"No healthy tokens available in pool. (Last error: {last_exception})"
                )

        if last_exception:
            raise last_exception
        raise NoAvailableTokensError("All retries exhausted across available tokens in pool.")

    def get_status(self) -> Dict[str, Any]:
        """Return comprehensive status and health report for the token pool."""
        with self._lock:
            healthy_count = sum(1 for e in self._tokens if e.is_healthy())
            cooldown_count = sum(1 for e in self._tokens if e.status == TokenStatus.COOLDOWN and not e.is_healthy())
            invalid_count = sum(1 for e in self._tokens if e.status == TokenStatus.INVALID)
            disabled_count = sum(1 for e in self._tokens if e.status == TokenStatus.DISABLED)

            return {
                "total_tokens": len(self._tokens),
                "healthy": healthy_count,
                "cooldown": cooldown_count,
                "invalid": invalid_count,
                "disabled": disabled_count,
                "strategy": self.strategy.value,
                "boost_enabled": self._boost_enabled,
                "source_file": str(self.source_file) if self.source_file else "environment/manual",
                "tokens": [e.to_dict() for e in self._tokens],
            }

    def print_status(self) -> None:
        """Pretty print the status of the token pool in the terminal."""
        status = self.get_status()
        boost_str = "🚀 BOOST: ON" if status.get("boost_enabled") else "BOOST: OFF"
        print("=" * 75)
        print(f"📊 DeepSeekPool Status | Strategy: {status['strategy']} | {boost_str}")
        print(f"   Source: {status['source_file']}")
        print(f"   Total: {status['total_tokens']} | Healthy: {status['healthy']} | Cooldown: {status['cooldown']} | Invalid: {status['invalid']}")
        print("-" * 75)
        for tok in status["tokens"]:
            icon = "✅" if tok["status"] == "healthy" else ("⏳" if tok["status"] == "cooldown" else "❌")
            cd_info = f" (wait {tok['cooldown_remaining']}s)" if tok["status"] == "cooldown" else ""
            lat_info = f" {tok['latency_ms']}ms" if tok["latency_ms"] > 0 else ""
            req_info = f"reqs: {tok['total_requests']} (ok: {tok['total_successes']}, err: {tok['total_errors']})"
            print(f" {icon} {tok['name']:<18} [{tok['status'].upper():<8}{cd_info:<12}] {req_info:<30} {lat_info}")
            if tok.get("last_error"):
                print(f"    ↳ Error: {tok['last_error']}")
        print("=" * 75)
