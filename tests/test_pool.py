import unittest
import os
import sys
import tempfile
import json
import time
import threading
from pathlib import Path
from typing import Generator, Dict, Any

from dsk.pool import (
    DeepSeekPool,
    TokenEntry,
    TokenStatus,
    PoolStrategy,
    NoAvailableTokensError,
)
from dsk.api import (
    AuthenticationError,
    RateLimitError,
    APIError,
)


class MockAPI:
    """Mock DeepSeekAPI for deterministic unit tests."""

    def __init__(self, token: str, behavior: str = "success"):
        self.token = token
        self.behavior = behavior
        self.session_counter = 0

    def create_chat_session(self) -> str:
        if self.behavior == "auth_error":
            raise AuthenticationError("Invalid authentication token")
        if self.behavior == "rate_limit":
            raise RateLimitError("Rate limit exceeded on session create")
        self.session_counter += 1
        return f"session_{self.token}_{self.session_counter}"

    def chat_completion(
        self,
        chat_session_id: str,
        prompt: str,
        parent_message_id=None,
        thinking_enabled=True,
        search_enabled=False,
        **kwargs
    ) -> Generator[Dict[str, Any], None, None]:
        if self.behavior == "rate_limit":
            raise RateLimitError("HTTP 429: Too Many Requests")
        if self.behavior == "auth_error":
            raise AuthenticationError("HTTP 401: Unauthorized")
        if self.behavior == "server_error":
            raise APIError("HTTP 500: Server Error", 500)
        if self.behavior == "fail_midway":
            yield {"content": "First chunk", "type": "text", "finish_reason": None}
            raise APIError("Stream dropped", 500)
        if self.behavior == "check_session_affinity":
            if not chat_session_id.startswith(f"session_{self.token}"):
                raise APIError(f"Session {chat_session_id} does not belong to token {self.token}", 400)

        # Normal successful generator
        if thinking_enabled:
            yield {"content": "Thinking process...", "type": "thinking", "finish_reason": None}
        yield {"content": f"Answer to '{prompt}' from {self.token}", "type": "text", "finish_reason": None}
        yield {"content": "", "type": "text", "finish_reason": "stop"}


class TestTokenEntry(unittest.TestCase):
    """Test suite for single TokenEntry state and behavior."""

    def test_entry_initialization(self):
        entry = TokenEntry(token="  my_secret_token_12345  ")
        self.assertEqual(entry.token, "my_secret_token_12345")
        self.assertEqual(entry.name, "my_s...2345")
        self.assertEqual(entry.status, TokenStatus.HEALTHY)
        self.assertTrue(entry.is_healthy())
        self.assertEqual(entry.cooldown_remaining, 0.0)

    def test_empty_token_raises(self):
        with self.assertRaises(ValueError):
            TokenEntry(token="   ")

    def test_cooldown_marking_and_expiration(self):
        entry = TokenEntry(token="test_token_abcdefg")
        entry.mark_cooldown(duration=0.2, reason="429 Rate Limit")
        self.assertEqual(entry.status, TokenStatus.COOLDOWN)
        self.assertFalse(entry.is_healthy())
        self.assertGreater(entry.cooldown_remaining, 0.0)
        self.assertEqual(entry.consecutive_failures, 1)

        # Wait for cooldown to expire
        time.sleep(0.25)
        # is_healthy should automatically recover it to HEALTHY
        self.assertTrue(entry.is_healthy())
        self.assertEqual(entry.status, TokenStatus.HEALTHY)
        self.assertEqual(entry.cooldown_remaining, 0.0)

    def test_invalid_marking(self):
        entry = TokenEntry(token="test_token_xyz")
        entry.mark_invalid(reason="401 Unauthorized")
        self.assertEqual(entry.status, TokenStatus.INVALID)
        self.assertFalse(entry.is_healthy())

    def test_mark_success(self):
        entry = TokenEntry(token="test_token_xyz")
        entry.mark_cooldown(duration=100.0)
        entry.mark_success()
        self.assertEqual(entry.status, TokenStatus.HEALTHY)
        self.assertEqual(entry.consecutive_failures, 0)
        self.assertEqual(entry.total_successes, 1)


class TestDeepSeekPoolManagement(unittest.TestCase):
    """Test token loading, management, files, and fallback."""

    def test_init_with_direct_token_list(self):
        pool = DeepSeekPool(tokens=["tok_1", "tok_2", "tok_3"])
        self.assertEqual(len(pool.get_tokens()), 3)
        self.assertIn("tok_1", pool.get_tokens())
        self.assertIn("tok_2", pool.get_tokens())
        self.assertIn("tok_3", pool.get_tokens())

    def test_init_with_comma_separated_tokens(self):
        pool = DeepSeekPool(tokens="tok_a, tok_b; tok_c")
        self.assertEqual(len(pool.get_tokens()), 3)

    def test_load_from_txt_file(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".txt") as f:
            f.write("# Sample deepseek tokens\n")
            f.write("tok_txt_1\n")
            f.write("\n")
            f.write("  tok_txt_2  \n")
            f.write("// Comment line\n")
            f.write('"tok_txt_3"\n')
            temp_path = f.name

        try:
            pool = DeepSeekPool(tokens_file=temp_path)
            tokens = pool.get_tokens()
            self.assertEqual(tokens, ["tok_txt_1", "tok_txt_2", "tok_txt_3"])
        finally:
            os.remove(temp_path)

    def test_load_from_json_file(self):
        # Format 1: List of objects with token & name
        data1 = [
            {"token": "json_tok_1", "name": "Acc 1"},
            {"token": "json_tok_2", "name": "Acc 2"},
        ]
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as f:
            json.dump(data1, f)
            temp_path1 = f.name

        try:
            pool1 = DeepSeekPool(tokens_file=temp_path1)
            self.assertEqual(pool1.get_tokens(), ["json_tok_1", "json_tok_2"])
            status = pool1.get_status()
            self.assertEqual(status["tokens"][0]["name"], "Acc 1")
        finally:
            os.remove(temp_path1)

        # Format 2: Dict with "tokens" key
        data2 = {"tokens": ["tok_j3", "tok_j4"]}
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as f:
            json.dump(data2, f)
            temp_path2 = f.name

        try:
            pool2 = DeepSeekPool(tokens_file=temp_path2)
            self.assertEqual(pool2.get_tokens(), ["tok_j3", "tok_j4"])
        finally:
            os.remove(temp_path2)

    def test_add_and_remove_token(self):
        pool = DeepSeekPool(tokens=["base_tok"])
        # Add new token
        self.assertTrue(pool.add_token("new_tok", name="CustomName"))
        self.assertEqual(len(pool.get_tokens()), 2)
        # Duplicate addition returns False
        self.assertFalse(pool.add_token("new_tok"))
        self.assertEqual(len(pool.get_tokens()), 2)
        # Remove token
        self.assertTrue(pool.remove_token("new_tok"))
        self.assertEqual(len(pool.get_tokens()), 1)
        # Remove non-existent token
        self.assertFalse(pool.remove_token("unknown_tok"))

    def test_save_tokens_txt_and_json(self):
        pool = DeepSeekPool(tokens=["save_tok_1", "save_tok_2"])

        # Save as TXT
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".txt") as f:
            txt_path = f.name
        # Save as JSON
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as f:
            json_path = f.name

        try:
            pool.save_tokens(txt_path)
            with open(txt_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("save_tok_1", content)
            self.assertIn("save_tok_2", content)

            pool.save_tokens(json_path)
            with open(json_path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            self.assertEqual(len(parsed), 2)
            self.assertEqual(parsed[0]["token"], "save_tok_1")
        finally:
            if os.path.exists(txt_path):
                os.remove(txt_path)
            if os.path.exists(json_path):
                os.remove(json_path)


class TestLoadBalancingStrategies(unittest.TestCase):
    """Test Round-Robin and LRU rotation logic."""

    def test_round_robin_selection(self):
        tokens = ["tok_rr_1", "tok_rr_2", "tok_rr_3"]
        pool = DeepSeekPool(tokens=tokens, strategy=PoolStrategy.ROUND_ROBIN)

        # 6 consecutive calls should rotate 1 -> 2 -> 3 -> 1 -> 2 -> 3
        expected = ["tok_rr_1", "tok_rr_2", "tok_rr_3", "tok_rr_1", "tok_rr_2", "tok_rr_3"]
        actual = [pool.get_next_token().token for _ in range(6)]
        self.assertEqual(actual, expected)

    def test_least_recently_used_selection(self):
        tokens = ["tok_lru_1", "tok_lru_2", "tok_lru_3"]
        pool = DeepSeekPool(tokens=tokens, strategy=PoolStrategy.LEAST_RECENTLY_USED)

        # All start with last_used = 0.0
        # Getting tok_lru_1 sets its timestamp
        t1 = pool.get_next_token()
        # Next should be tok_lru_2 (still 0.0)
        t2 = pool.get_next_token()
        # Next should be tok_lru_3 (still 0.0)
        t3 = pool.get_next_token()
        self.assertEqual([t1.token, t2.token, t3.token], ["tok_lru_1", "tok_lru_2", "tok_lru_3"])

        # Now all have been used once. t1 has the oldest timestamp among the 3
        t4 = pool.get_next_token()
        self.assertEqual(t4.token, "tok_lru_1")


class TestSessionIsolationAndFailover(unittest.TestCase):
    """Test per-token session isolation and smart failover."""

    def test_per_token_session_isolation(self):
        # Create pool with mock API
        apis = {}

        def mock_api_factory(tok: str):
            api = MockAPI(tok)
            apis[tok] = api
            return api

        pool = DeepSeekPool(
            tokens=["token_alpha", "token_beta"],
            api_factory=mock_api_factory,
        )

        sess_alpha = pool.get_chat_session("token_alpha")
        sess_beta = pool.get_chat_session("token_beta")

        self.assertNotEqual(sess_alpha, sess_beta)
        self.assertTrue(sess_alpha.startswith("session_token_alpha"))
        self.assertTrue(sess_beta.startswith("session_token_beta"))

        # Subsequent call returns same cached session ID (session persistence)
        self.assertEqual(pool.get_chat_session("token_alpha"), sess_alpha)

        # Resetting sessions clears them
        pool.reset_all_sessions()
        sess_alpha_new = pool.get_chat_session("token_alpha")
        self.assertNotEqual(sess_alpha_new, sess_alpha)

    def test_smart_failover_on_429_rate_limit(self):
        # Token 1 fails with 429, Token 2 succeeds
        def mock_api_factory(tok: str):
            if tok == "tok_fail_429":
                return MockAPI(tok, behavior="rate_limit")
            return MockAPI(tok, behavior="success")

        pool = DeepSeekPool(
            tokens=["tok_fail_429", "tok_success"],
            strategy=PoolStrategy.ROUND_ROBIN,
            cooldown_seconds=120.0,
            max_retries=2,
            api_factory=mock_api_factory,
        )

        # Running chat_completion should failover seamlessly to tok_success
        chunks = list(pool.chat_completion("Hello World"))
        content = "".join(c["content"] for c in chunks if c["type"] == "text")

        self.assertIn("Answer to 'Hello World' from tok_success", content)
        self.assertEqual(pool.last_used_token, "tok_success")

        # Verify tok_fail_429 was put into COOLDOWN
        tok1_entry = pool._tokens_map["tok_fail_429"]
        self.assertEqual(tok1_entry.status, TokenStatus.COOLDOWN)
        self.assertGreater(tok1_entry.cooldown_remaining, 0.0)

    def test_smart_failover_on_401_authentication_error(self):
        # Token 1 fails with 401, Token 2 succeeds
        def mock_api_factory(tok: str):
            if tok == "tok_invalid_401":
                return MockAPI(tok, behavior="auth_error")
            return MockAPI(tok, behavior="success")

        pool = DeepSeekPool(
            tokens=["tok_invalid_401", "tok_valid"],
            strategy=PoolStrategy.ROUND_ROBIN,
            max_retries=2,
            api_factory=mock_api_factory,
        )

        chunks = list(pool.chat_completion("Test prompt"))
        content = "".join(c["content"] for c in chunks if c["type"] == "text")

        self.assertIn("Answer to 'Test prompt' from tok_valid", content)

        # Verify tok_invalid_401 was marked INVALID
        tok1_entry = pool._tokens_map["tok_invalid_401"]
        self.assertEqual(tok1_entry.status, TokenStatus.INVALID)
        self.assertFalse(tok1_entry.is_healthy())

    def test_all_tokens_exhausted_raises_no_available_tokens(self):
        def mock_api_factory(tok: str):
            return MockAPI(tok, behavior="rate_limit")

        pool = DeepSeekPool(
            tokens=["tok_1", "tok_2"],
            cooldown_seconds=60.0,
            api_factory=mock_api_factory,
        )

        with self.assertRaises(NoAvailableTokensError) as ctx:
            list(pool.chat_completion("Prompt"))

        self.assertTrue("cooling down" in str(ctx.exception).lower() or "retries exhausted" in str(ctx.exception).lower())

    def test_midway_stream_error_does_not_retry_from_scratch(self):
        # If chunks have already begun yielding to user, it re-raises to avoid duplicate outputs
        def mock_api_factory(tok: str):
            return MockAPI(tok, behavior="fail_midway")

        pool = DeepSeekPool(
            tokens=["tok_midway_fail", "tok_backup"],
            api_factory=mock_api_factory,
        )

        gen = pool.chat_completion("Test")
        # First chunk succeeds
        first_chunk = next(gen)
        self.assertEqual(first_chunk["content"], "First chunk")
        # Next chunk raises APIError
        with self.assertRaises(APIError):
            next(gen)

    def test_thread_safety_concurrent_access(self):
        pool = DeepSeekPool(tokens=[f"tok_thread_{i}" for i in range(10)])
        results = []
        errors = []

        def worker():
            try:
                for _ in range(50):
                    tok = pool.get_next_token()
                    results.append(tok.token)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 250)

    def test_token_validation(self):
        def mock_api_factory(tok: str):
            if tok == "valid_token_1234":
                return MockAPI(tok, behavior="success")
            elif tok == "bad_token_5678":
                return MockAPI(tok, behavior="auth_error")
            return MockAPI(tok, behavior="rate_limit")

        pool = DeepSeekPool(
            tokens=["valid_token_1234", "bad_token_5678"],
            api_factory=mock_api_factory,
        )

        validation_results = pool.validate_all_tokens(concurrent=False)
        self.assertTrue(validation_results["vali...1234"])
        self.assertFalse(validation_results["bad_...5678"])

        # Status updated
        self.assertTrue(pool._tokens_map["valid_token_1234"].is_healthy())
        self.assertEqual(pool._tokens_map["bad_token_5678"].status, TokenStatus.INVALID)


class TestEdgeCasesAndScaling(unittest.TestCase):
    """Test edge cases, API parameter flexibility, and high-capacity (100 tokens) scaling."""

    def test_empty_pool_completion_raises(self):
        # Empty pool with no tokens
        pool = DeepSeekPool(tokens=[])
        # Clear any env-discovered tokens
        pool._tokens.clear()
        pool._tokens_map.clear()

        with self.assertRaises(NoAvailableTokensError):
            list(pool.chat_completion("Hello"))

    def test_parameter_polymorphism_and_signatures(self):
        def mock_api_factory(tok: str):
            return MockAPI(tok)

        pool = DeepSeekPool(tokens=["token_poly"], api_factory=mock_api_factory)

        # 1. Single prompt positional argument
        c1 = list(pool.chat_completion("Positional prompt"))
        txt1 = "".join(c["content"] for c in c1 if c["type"] == "text")
        self.assertIn("Positional prompt", txt1)

        # 2. session_id, prompt positional arguments (identical to DeepSeekAPI)
        c2 = list(pool.chat_completion("my_sess_id", "Prompt with session"))
        txt2 = "".join(c["content"] for c in c2 if c["type"] == "text")
        self.assertIn("Prompt with session", txt2)

        # 3. Keyword prompt
        c3 = list(pool.chat_completion(prompt="Kwarg prompt", thinking_enabled=False))
        txt3 = "".join(c["content"] for c in c3 if c["type"] == "text")
        self.assertIn("Kwarg prompt", txt3)
        # Verify no thinking chunk
        types3 = [c["type"] for c in c3]
        self.assertNotIn("thinking", types3)

        # 4. Keyword chat_session_id and prompt
        c4 = list(pool.chat_completion(chat_session_id="custom_sess", prompt="Custom sess prompt"))
        txt4 = "".join(c["content"] for c in c4 if c["type"] == "text")
        self.assertIn("Custom sess prompt", txt4)

    def test_high_capacity_100_tokens_rotation(self):
        """Simulate a 100-account pool and verify rotation, performance, and health tracking."""
        tokens_100 = [f"deepseek_account_token_{i:03d}_secret" for i in range(100)]

        def mock_api_factory(tok: str):
            return MockAPI(tok)

        pool = DeepSeekPool(
            tokens=tokens_100,
            strategy=PoolStrategy.ROUND_ROBIN,
            api_factory=mock_api_factory,
        )

        self.assertEqual(len(pool.get_tokens()), 100)
        status = pool.get_status()
        self.assertEqual(status["total_tokens"], 100)
        self.assertEqual(status["healthy"], 100)

        # Run 300 requests through the pool
        used_tokens = []
        for i in range(300):
            chunks = list(pool.chat_completion(f"Query #{i}"))
            used_tokens.append(pool.last_used_token)

        # Every token of the 100 tokens should have been used exactly 3 times in round robin
        from collections import Counter
        counts = Counter(used_tokens)
        self.assertEqual(len(counts), 100)
        for tok, cnt in counts.items():
            self.assertEqual(cnt, 3)

        # Simulate 10 tokens encountering rate limits
        for i in range(10):
            tok_entry = pool._tokens[i]
            tok_entry.mark_cooldown(duration=300.0, reason="HTTP 429")

        # Now only 90 tokens are healthy
        healthy = pool.get_healthy_tokens()
        self.assertEqual(len(healthy), 90)

        # Next 90 requests should cleanly distribute among the 90 healthy tokens
        used_healthy = []
        for i in range(90):
            chunks = list(pool.chat_completion(f"Query after fail #{i}"))
            used_healthy.append(pool.last_used_token)

        counts_healthy = Counter(used_healthy)
        self.assertEqual(len(counts_healthy), 90)
        for i in range(10):
            self.assertNotIn(pool._tokens[i].token, counts_healthy)


class TestSessionAffinityAndFairLoadBalancing(unittest.TestCase):
    """Test suite verifying session affinity, fair round robin under cooldowns, and metric integrity."""

    def test_session_affinity_routes_to_owning_token(self):
        """Verify that requests with chat_session_id route to the owning token, not rotating away."""
        def mock_api_factory(tok: str):
            return MockAPI(tok, behavior="check_session_affinity")

        pool = DeepSeekPool(
            tokens=["token_alpha", "token_beta"],
            api_factory=mock_api_factory,
        )

        # Create session specifically on token_alpha
        sess_alpha = pool.create_chat_session(token="token_alpha")
        self.assertTrue(sess_alpha.startswith("session_token_alpha"))

        # Send multiple queries with sess_alpha
        for i in range(5):
            chunks = list(pool.chat_completion(chat_session_id=sess_alpha, prompt=f"Msg {i}"))
            # Must succeed and stay on token_alpha without throwing session mismatch 400 error!
            self.assertEqual(pool.last_used_token, "token_alpha")

        # Create session on token_beta
        sess_beta = pool.create_chat_session(token="token_beta")
        chunks = list(pool.chat_completion(chat_session_id=sess_beta, prompt="Msg beta"))
        self.assertEqual(pool.last_used_token, "token_beta")

    def test_session_failover_when_owner_cooling_down(self):
        """Verify that when session owner goes into cooldown, failover safely acquires a new token."""
        alpha_api = MockAPI("token_alpha", behavior="check_session_affinity")
        beta_api = MockAPI("token_beta", behavior="check_session_affinity")

        def mock_api_factory(tok: str):
            return alpha_api if tok == "token_alpha" else beta_api

        pool = DeepSeekPool(
            tokens=["token_alpha", "token_beta"],
            api_factory=mock_api_factory,
        )

        sess_alpha = pool.create_chat_session(token="token_alpha")
        # Put token_alpha in cooldown
        pool._tokens_map["token_alpha"].mark_cooldown(300.0, "Rate limited")

        # Sending prompt should failover seamlessly to token_beta
        chunks = list(pool.chat_completion(chat_session_id=sess_alpha, prompt="Failover message"))
        content = "".join(c["content"] for c in chunks if c["type"] == "text")
        self.assertIn("token_beta", content)
        self.assertEqual(pool.last_used_token, "token_beta")

    def test_mark_success_called_once_per_request(self):
        """Verify that total_successes increments once per chat completion, not per streaming chunk."""
        def mock_api_factory(tok: str):
            return MockAPI(tok)

        pool = DeepSeekPool(tokens=["token_single"], api_factory=mock_api_factory)
        entry = pool._tokens[0]

        # Execute completion yielding 3 chunks (thinking, text, stop)
        chunks = list(pool.chat_completion("Test prompt"))
        self.assertEqual(len(chunks), 3)

        # total_successes must be exactly 1, not 3!
        self.assertEqual(entry.total_requests, 1)
        self.assertEqual(entry.total_successes, 1)

    def test_round_robin_fair_distribution_under_cooldowns(self):
        """Verify monotonic round-robin fairly rotates among available healthy candidates without phase skipping."""
        tokens = [f"tok_rr_{i}" for i in range(10)]
        pool = DeepSeekPool(tokens=tokens, strategy=PoolStrategy.ROUND_ROBIN)

        # Mark 3 tokens in cooldown: 0, 1, 2
        for i in range(3):
            pool._tokens[i].mark_cooldown(300.0)

        # 7 healthy tokens remain: 3, 4, 5, 6, 7, 8, 9
        # Run 70 selections
        selected = [pool.get_next_token().token for _ in range(70)]
        from collections import Counter
        counts = Counter(selected)

        # Every healthy token must receive EXACTLY 10 requests!
        self.assertEqual(len(counts), 7)
        for tok, cnt in counts.items():
            self.assertEqual(cnt, 10, f"Token {tok} received {cnt} requests, expected exactly 10")

    def test_inline_comment_stripping_in_tokens_txt(self):
        """Verify inline comments (# and //) are stripped cleanly when loading tokens.txt."""
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".txt") as f:
            f.write("token_clean_1 # Primary account\n")
            f.write("token_clean_2 // Secondary backup\n")
            f.write('"token_clean_3"   # Quoted token\n')
            f.write("   token_clean_4   \n")
            temp_path = f.name

        try:
            pool = DeepSeekPool(tokens_file=temp_path)
            tokens = pool.get_tokens()
            self.assertEqual(tokens, ["token_clean_1", "token_clean_2", "token_clean_3", "token_clean_4"])
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestBoostAndLearnSystems(unittest.TestCase):
    """Test suite for /boost accelerated execution and /learn auto-discovery system."""

    def test_boost_completion_hedged_racing(self):
        def mock_api_factory(tok: str):
            return MockAPI(tok)

        pool = DeepSeekPool(
            tokens=["boost_tok_1", "boost_tok_2"],
            api_factory=mock_api_factory,
        )

        # Boost completion
        chunks = list(pool.boost_completion("Boost prompt"))
        content = "".join(c["content"] for c in chunks if c["type"] == "text")
        self.assertIn("Answer to 'Boost prompt'", content)
        self.assertIn(pool.last_used_token, ["boost_tok_1", "boost_tok_2"])

    def test_boost_toggle_and_chat_integration(self):
        def mock_api_factory(tok: str):
            return MockAPI(tok)

        pool = DeepSeekPool(
            tokens=["boost_a", "boost_b"],
            api_factory=mock_api_factory,
        )

        self.assertFalse(pool.boost_enabled)
        pool.set_boost(True)
        self.assertTrue(pool.boost_enabled)

        # Calling chat_completion with boost_enabled delegates to boost_completion
        chunks = list(pool.chat_completion("Hedged query"))
        content = "".join(c["content"] for c in chunks if c["type"] == "text")
        self.assertIn("Hedged query", content)

    def test_boost_batch_execution(self):
        def mock_api_factory(tok: str):
            return MockAPI(tok)

        pool = DeepSeekPool(
            tokens=[f"batch_tok_{i}" for i in range(5)],
            api_factory=mock_api_factory,
        )

        prompts = [f"Batch query {i}" for i in range(10)]
        results = pool.boost_batch(prompts, max_concurrency=4)

        self.assertEqual(len(results), 10)
        for i, res in enumerate(results):
            self.assertEqual(res["prompt"], f"Batch query {i}")
            self.assertIn(f"Batch query {i}", res["text"])
            self.assertIsNone(res["error"])

    def test_learn_auto_discovery_and_profiling(self):
        def mock_api_factory(tok: str):
            return MockAPI(tok)

        # Create temporary token file to discover
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".txt") as f:
            f.write("learned_account_token_1234567890abcdef\n")
            f.write("discovered_account_token_9876543210fedcba\n")
            temp_path = f.name

        try:
            pool = DeepSeekPool(tokens=["initial_token_12345678901234"], api_factory=mock_api_factory)
            report = pool.learn(sources=[temp_path], auto_add=True, benchmark=True)

            self.assertGreaterEqual(report["discovered_count"], 2)
            self.assertGreaterEqual(report["pool_total"], 3)
            self.assertGreaterEqual(report["healthy_count"], 3)
            self.assertIn("token_profiles", report)

            # Profile metrics
            profile = pool.get_performance_profile()
            self.assertEqual(profile["total_accounts"], pool.get_status()["total_tokens"])
            self.assertEqual(profile["healthy_accounts"], pool.get_status()["healthy"])
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()

