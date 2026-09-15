import sys
import os
import argparse
from typing import Generator, Dict, Any, Optional
from dotenv import load_dotenv

from dsk import (
    DeepSeekPool,
    PoolStrategy,
    NoAvailableTokensError,
    AuthenticationError,
    RateLimitError,
    NetworkError,
    APIError,
)

load_dotenv()


def print_response(chunks: Generator[Dict[str, Any], None, None]) -> None:
    """Print streaming response chunks with thinking and final text separated."""
    thinking_chunks = []
    text_chunks = []

    try:
        for chunk in chunks:
            chunk_type = chunk.get("type", "text")
            content = chunk.get("content", "")

            if chunk_type == "thinking":
                if content:
                    thinking_chunks.append(content)
            elif chunk_type == "text":
                if content:
                    text_chunks.append(content)

    except KeyError as e:
        print(f"❌ Error: Malformed response chunk - missing key {str(e)}")
        return

    if thinking_chunks:
        print("\n🤔 Thinking:")
        print("".join(thinking_chunks))
        print()

    print("💬 Response:")
    print("".join(text_chunks))
    print()


def run_pool_chat(
    pool: DeepSeekPool,
    title: str,
    prompt: str,
    chat_session_id: Optional[str] = None,
    thinking_enabled: bool = True,
    search_enabled: bool = False,
    boost: bool = False,
) -> Optional[str]:
    """Run a chat request through the pool with load balancing and failover."""
    print(f"\n{title}")
    print("=" * 80)
    print(f"📥 Prompt: {prompt}")

    try:
        chunks = pool.chat_completion(
            prompt=prompt,
            chat_session_id=chat_session_id,
            thinking_enabled=thinking_enabled,
            search_enabled=search_enabled,
            boost=boost,
        )
        print_response(chunks)

        if pool.last_used_token:
            masked = f"{pool.last_used_token[:4]}...{pool.last_used_token[-4:]}"
            boost_tag = " [⚡ BOOSTED]" if boost or pool.boost_enabled else ""
            print(f"🎯 Handled by account token: {masked}{boost_tag}")

        return pool.last_used_session_id

    except NoAvailableTokensError as e:
        print(f"❌ Pool Exhaustion: {str(e)}")
        if e.retry_after:
            print(f"⏳ Please wait {e.retry_after:.1f} seconds before retrying.")
    except AuthenticationError as e:
        print(f"❌ Authentication Error: {str(e)}")
        print("Please check your tokens in tokens.txt, tokens.json, or .env.")
    except RateLimitError as e:
        print(f"❌ Rate Limit Error: {str(e)}")
        print("All candidate tokens encountered rate limits.")
    except NetworkError as e:
        print(f"❌ Network Error: {str(e)}")
        print("Please check your internet connection.")
    except APIError as e:
        print(f"❌ API Error: {str(e)}")
        if e.status_code:
            print(f"Status code: {e.status_code}")
    except Exception as e:
        print(f"❌ Unexpected Error: {str(e)}")

    return None


def run_interactive_repl(pool: DeepSeekPool):
    """Interactive chat REPL with slash command system: /boost, /learn, /status, etc."""
    print("\n" + "=" * 80)
    print("💬 DeepSeekPool Interactive Terminal | Type /help for command list")
    print("=" * 80)
    print("Commands:")
    print("  /boost [query]  - Run boosted accelerated query, or toggle boost mode")
    print("  /learn          - Auto-discover, validate, benchmark & learn token pool")
    print("  /status         - Show live pool health, accounts & latencies")
    print("  /tokens         - Detailed list of tokens")
    print("  /add <token>    - Add a new account token to the pool")
    print("  /remove <token> - Remove a token from the pool")
    print("  /strategy <rr|lru> - Switch load balancing strategy")
    print("  /reset          - Clear active conversation session")
    print("  /help           - Display this command menu")
    print("  exit / quit     - Exit interactive mode")
    print("-" * 80)

    current_session: Optional[str] = None

    while True:
        try:
            prompt_indicator = "[BOOST ⚡]" if pool.boost_enabled else "[NORMAL]"
            user_input = input(f"\n{prompt_indicator} You > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Goodbye!")
            break

        if not user_input:
            continue

        # Command handling
        cmd_lower = user_input.lower()
        if cmd_lower in ("exit", "quit", "/exit", "/quit"):
            print("👋 Goodbye!")
            break

        if cmd_lower == "/help":
            print("\nAvailable Slash Commands:")
            print("  /boost            Toggle boost mode ON / OFF")
            print("  /boost <prompt>   Send prompt using multi-account accelerated boost")
            print("  /learn            Auto-discover tokens from files/.env, benchmark latency & optimize")
            print("  /status           Print visual dashboard of all pool tokens and health")
            print("  /tokens           List tokens, masked identifiers, and request statistics")
            print("  /add <token>      Add a new account token to the active pool")
            print("  /remove <token>   Remove an account token from the pool")
            print("  /strategy rr|lru  Switch load balancing between Round-Robin and LRU")
            print("  /reset            Reset chat session to start fresh conversation")
            print("  /exit, quit       Quit interactive shell")
            continue

        if cmd_lower == "/status":
            pool.print_status()
            continue

        if cmd_lower == "/tokens":
            status = pool.get_status()
            print("\nRegistered Accounts:")
            for idx, tok in enumerate(status["tokens"], 1):
                icon = "✅" if tok["status"] == "healthy" else ("⏳" if tok["status"] == "cooldown" else "❌")
                print(f"  {idx:2d}. {icon} {tok['name']} | reqs: {tok['total_requests']} (ok: {tok['total_successes']}) | {tok['latency_ms']}ms")
            continue

        if cmd_lower == "/reset":
            pool.reset_all_sessions()
            current_session = None
            print("🔄 Session reset. Starting fresh conversation context.")
            continue

        if cmd_lower.startswith("/strategy"):
            parts = user_input.split(maxsplit=1)
            if len(parts) > 1 and parts[1].strip().lower() in ("lru", "least_recently_used"):
                pool.strategy = PoolStrategy.LEAST_RECENTLY_USED
                print("⚙️ Strategy switched to: LEAST_RECENTLY_USED (LRU)")
            else:
                pool.strategy = PoolStrategy.ROUND_ROBIN
                print("⚙️ Strategy switched to: ROUND_ROBIN")
            continue

        if cmd_lower.startswith("/add "):
            new_tok = user_input[5:].strip()
            if pool.add_token(new_tok, save_to_file=True):
                print(f"✅ Token added successfully: {new_tok[:4]}...{new_tok[-4:]}")
            else:
                print("⚠️ Failed to add token (empty or already exists).")
            continue

        if cmd_lower.startswith("/remove "):
            rem_tok = user_input[8:].strip()
            if pool.remove_token(rem_tok, save_to_file=True):
                print(f"🗑️ Token removed: {rem_tok[:4]}...{rem_tok[-4:]}")
            else:
                print("⚠️ Token not found in pool.")
            continue

        if cmd_lower == "/learn":
            print("\n🔍 Running /learn: Auto-discovering tokens and benchmarking latencies...")
            report = pool.learn(auto_add=True, benchmark=True)
            print("=" * 65)
            print("🧠 /learn System Report:")
            print(f"   • Discovered tokens: {report['discovered_count']} | Added to pool: {report['added_to_pool']}")
            print(f"   • Total in pool: {report['pool_total']} (Healthy: {report['healthy_count']}, Cooldown: {report['cooldown_count']}, Invalid: {report['invalid_count']})")
            print(f"   • Average Latency: {report['average_latency_ms']}ms")
            if report.get("fastest_account"):
                print(f"   • Fastest Account: {report['fastest_account']}")
            print("=" * 65)
            continue

        if cmd_lower == "/boost":
            new_state = not pool.boost_enabled
            pool.set_boost(new_state)
            state_text = "ENABLED (Multi-account hedged racing)" if new_state else "DISABLED"
            print(f"⚡ /boost mode is now: {state_text}")
            continue

        boost_this_prompt = False
        actual_prompt = user_input
        if user_input.startswith("/boost "):
            boost_this_prompt = True
            actual_prompt = user_input[7:].strip()

        # Send chat completion
        try:
            print("\n🤖 DeepSeek: ", end="", flush=True)
            chunks = pool.chat_completion(
                prompt=actual_prompt,
                chat_session_id=current_session,
                thinking_enabled=True,
                boost=boost_this_prompt,
            )
            print_response(chunks)
            current_session = pool.last_used_session_id

            if pool.last_used_token:
                masked = f"{pool.last_used_token[:4]}...{pool.last_used_token[-4:]}"
                tag = " [⚡ BOOSTED]" if boost_this_prompt or pool.boost_enabled else ""
                print(f"🎯 Handled by account token: {masked}{tag}")

        except NoAvailableTokensError as e:
            print(f"\n❌ Pool Exhaustion: {str(e)}")
        except AuthenticationError as e:
            print(f"\n❌ Authentication Error: {str(e)}")
        except RateLimitError as e:
            print(f"\n❌ Rate Limit: {str(e)}")
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")


def main():
    parser = argparse.ArgumentParser(description="DeepSeekPool multi-account token rotation runner and CLI.")
    parser.add_argument("--interactive", "-i", action="store_true", help="Start interactive chat shell with slash commands (/boost, /learn, etc).")
    parser.add_argument("--status", "-s", action="store_true", help="Print pool status and token health summary.")
    parser.add_argument("--validate", "-v", action="store_true", help="Validate all tokens against DeepSeek API.")
    parser.add_argument("--learn", "-l", action="store_true", help="Run /learn auto-discovery, harvesting, and latency benchmarking.")
    parser.add_argument("--boost", "-b", type=str, default=None, help="Execute a boosted prompt with multi-account acceleration.")
    parser.add_argument("--demo", action="store_true", help="Run automated demonstration examples.")
    parser.add_argument("--strategy", choices=["round_robin", "lru"], default="round_robin", help="Selection strategy.")
    parser.add_argument("--tokens-file", type=str, default=None, help="Custom path to tokens.txt or tokens.json.")
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("🚀 DeepSeek Multi-Account Token Rotation & Acceleration System (DeepSeekPool)")
    print("=" * 80)

    pool = DeepSeekPool(
        tokens_file=args.tokens_file,
        strategy=PoolStrategy(args.strategy),
        cooldown_seconds=300.0,
        max_retries=3,
    )

    status = pool.get_status()
    if status["total_tokens"] == 0:
        print("\n⚠️ No tokens found!")
        print("Please add your tokens to 'tokens.txt' or set DEEPSEEK_AUTH_TOKEN in '.env'.")
        print("See 'tokens.txt.example' for format guidance.")
        sys.exit(1)

    # 1. Print status
    if args.status:
        pool.print_status()
        return

    # 2. Validate tokens if requested
    if args.validate:
        print("\n🔍 Validating all tokens in pool...")
        results = pool.validate_all_tokens()
        for name, valid in results.items():
            print(f"   {name}: {'✅ Valid' if valid else '❌ Invalid'}")
        print("\n[Updated Status after Validation]")
        pool.print_status()
        return

    # 3. Learn system
    if args.learn:
        print("\n🧠 Executing /learn system: scanning, harvesting, and latency profiling...")
        report = pool.learn(auto_add=True, benchmark=True)
        print("=" * 70)
        print(f"Discovered: {report['discovered_count']} | Valid: {report['healthy_count']} | Cooldown: {report['cooldown_count']} | Invalid: {report['invalid_count']}")
        print(f"Average Latency: {report['average_latency_ms']}ms | Fastest: {report.get('fastest_account')}")
        print("=" * 70)
        pool.print_status()
        return

    # 4. Boost prompt from CLI
    if args.boost:
        run_pool_chat(
            pool,
            "⚡ Boosted Completion (Multi-Account Acceleration)",
            args.boost,
            thinking_enabled=True,
            boost=True,
        )
        return

    # 5. Demo mode
    if args.demo:
        run_pool_chat(
            pool,
            "Example 1: Short question (with thinking, Round-Robin rotation)",
            "Explain in 2 sentences why distributed load balancing is essential for high-throughput AI systems.",
            thinking_enabled=True,
            search_enabled=False,
        )

        run_pool_chat(
            pool,
            "Example 2: Fast calculation (without thinking)",
            "What is 17 * 23? Give only the final number.",
            thinking_enabled=False,
            search_enabled=False,
        )

        print("\n[Updated Pool Status after requests]")
        pool.print_status()
        return

    # Default: Start interactive chat REPL
    run_interactive_repl(pool)


if __name__ == "__main__":
    main()
