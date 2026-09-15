# DeepSeek4Free

A Python package for interacting with the DeepSeek AI chat API. This package provides a clean interface to interact with DeepSeek's chat model, with support for streaming responses, thinking process visibility, and web search capabilities.

### Learn how to reverse engineer private api's !!
- and reverse wasm like it was required here
- [whop.com/reverser-academy](https://whop.com/reverser-academy/) (beta)


> ⚠️ **Service Notice**: DeepSeek API is currently experiencing high load. Work is in progress to integrate additional API providers. Please expect intermittent errors.

> 📝 **Note**: If you encounter any errors, please ensure you are using the latest version of this library. The DeepSeek API may change frequently, and updates are released to maintain compatibility.

## ✨ Features

- 🔄 **Streaming Responses**: Real-time interaction with token-by-token output
- 🤔 **Thinking Process**: Optional visibility into the model's reasoning steps
- 🔍 **Web Search**: Optional integration for up-to-date information
- 💬 **Session Management**: Persistent chat sessions with conversation history
- ⚡ **Efficient PoW**: WebAssembly-based proof of work implementation
- 🛡️ **Error Handling**: Comprehensive error handling with specific exceptions
- ⏱️ **No Timeouts**: Designed for long-running conversations without timeouts
- 🧵 **Thread Support**: Parent message tracking for threaded conversations

## 📦 Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/deepseek4free.git
cd deepseek4free
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## 🔑 Authentication

To use this package, you need a DeepSeek auth token. Here's how to obtain it:

If you know how to use chrome devtools, simply run this snipped in the console:

```js
JSON.parse(localStorage.getItem("userToken")).value
```

### Method 1: From LocalStorage (Recommended)

<img width="1150" alt="image" src="https://github.com/user-attachments/assets/b4e11650-3d1b-4638-956a-c67889a9f37e" />

1. Visit [chat.deepseek.com](https://chat.deepseek.com)
2. Log in to your account
3. Open browser developer tools (F12 or right-click > Inspect)
4. Go to Application tab (if not visible, click >> to see more tabs)
5. In the left sidebar, expand "Local Storage"
6. Click on "https://chat.deepseek.com"
7. Find the key named `userToken`
8. Copy `"value"` - this is your authentication token

### Method 2: From Network Tab

Alternatively, you can get the token from network requests:

1. Visit [chat.deepseek.com](https://chat.deepseek.com)
2. Log in to your account
3. Open browser developer tools (F12)
4. Go to Network tab
5. Make any request in the chat
6. Find the request headers
7. Copy the `authorization` token (without 'Bearer ' prefix)

### Handling Cloudflare Challenges

If you encounter Cloudflare challenges ("Just a moment..." page), you'll need to get a `cf_clearance` cookie. Run this command:

```bash
python -m dsk.bypass
```

This will:
1. Open an undetected browser
2. Visit DeepSeek and solve the Cloudflare challenge
3. Capture and save the `cf_clearance` cookie
4. The cookie will be automatically used in future requests

You only need to run this when:
- You get Cloudflare challenges in your requests
- Your existing cf_clearance cookie expires
- You see the error "Please wait a few minutes before trying again"

The captured cookie will be stored in `dsk/cookies.json` and automatically used by the API.

## 📚 Usage

### Basic Example

```python
from dsk.api import DeepSeekAPI

# Initialize with your auth token
api = DeepSeekAPI("YOUR_AUTH_TOKEN")

# Create a new chat session
chat_id = api.create_chat_session()

# Simple chat completion
prompt = "What is Python?"
for chunk in api.chat_completion(chat_id, prompt):
    if chunk['type'] == 'text':
        print(chunk['content'], end='', flush=True)
```

### Advanced Features

#### Thinking Process Visibility

The thinking process shows the model's reasoning steps:

```python
# With thinking process enabled
for chunk in api.chat_completion(
    chat_id,
    "Explain quantum computing",
    thinking_enabled=True
):
    if chunk['type'] == 'thinking':
        print(f"🤔 Thinking: {chunk['content']}")
    elif chunk['type'] == 'text':
        print(chunk['content'], end='', flush=True)
```

#### Web Search Integration

Enable web search for up-to-date information:

```python
# With web search enabled
for chunk in api.chat_completion(
    chat_id,
    "What are the latest developments in AI?",
    thinking_enabled=True,
    search_enabled=True
):
    if chunk['type'] == 'thinking':
        print(f"🔍 Searching: {chunk['content']}")
    elif chunk['type'] == 'text':
        print(chunk['content'], end='', flush=True)
```

#### Threaded Conversations

Create threaded conversations by tracking parent messages:

```python
# Start a conversation
chat_id = api.create_chat_session()

# Send initial message
parent_id = None
for chunk in api.chat_completion(chat_id, "Tell me about neural networks"):
    if chunk['type'] == 'text':
        print(chunk['content'], end='', flush=True)
    elif 'message_id' in chunk:
        parent_id = chunk['message_id']

# Send follow-up question in the thread
for chunk in api.chat_completion(
    chat_id,
    "How do they compare to other ML models?",
    parent_message_id=parent_id
):
    if chunk['type'] == 'text':
        print(chunk['content'], end='', flush=True)
```

### Error Handling

The package provides specific exceptions for different error scenarios:

```python
from dsk.api import (
    DeepSeekAPI, 
    AuthenticationError,
    RateLimitError,
    NetworkError,
    CloudflareError,
    APIError
)

try:
    api = DeepSeekAPI("YOUR_AUTH_TOKEN")
    chat_id = api.create_chat_session()
    
    for chunk in api.chat_completion(chat_id, "Your prompt here"):
        if chunk['type'] == 'text':
            print(chunk['content'], end='', flush=True)
            
except AuthenticationError:
    print("Authentication failed. Please check your token.")
except RateLimitError:
    print("Rate limit exceeded. Please wait before making more requests.")
except CloudflareError as e:
    print(f"Cloudflare protection encountered: {str(e)}")
except NetworkError:
    print("Network error occurred. Check your internet connection.")
except APIError as e:
    print(f"API error occurred: {str(e)}")
```

## 🚀 Multi-Account Token Rotation & Acceleration (`DeepSeekPool`)

For high-throughput applications, scaling across 100+ accounts, and eliminating rate limits (HTTP 429), use `DeepSeekPool`.

### Features:
- 🔄 **Load Balancing**: Round-Robin or Least-Recently-Used (LRU) strategies with fair monotonic distribution.
- 🛡️ **Smart Failover**: Automatically catches `RateLimitError` (HTTP 429), applies temporary cooldown (e.g. 5 minutes), and retries immediately with the next healthy account.
- 💬 **Session Affinity & Isolation**: Each token maintains its own independent session IDs, preserving conversation memory per account without cross-token contamination.
- ⚡ **/boost Acceleration**: Multi-account hedged racing queries top accounts simultaneously and streams whichever responds fastest, cutting latency by 50%+. Also includes `boost_batch` for parallel batch processing across accounts.
- 🧠 **/learn Auto-Discovery**: Automatically discovers and harvests tokens from `.env`, `tokens.txt`, `tokens.json`, and environment variables; benchmarks latency and calibrates pool health.
- 📁 **Flexible Token Loading**: Loads from `tokens.txt` (supports inline `#` comments), `tokens.json`, or `.env` fallback.

### Quickstart Example:

```python
from dsk import DeepSeekPool, PoolStrategy

# Initializes automatically from tokens.txt, tokens.json, or .env
pool = DeepSeekPool(
    strategy=PoolStrategy.ROUND_ROBIN,
    cooldown_seconds=300.0,
    max_retries=3
)

# 1. Print pool health and account statuses
pool.print_status()

# 2. Chat completion with automatic rotation and failover
for chunk in pool.chat_completion("Explain distributed token rotation"):
    if chunk['type'] == 'text':
        print(chunk['content'], end='', flush=True)

# 3. /boost Mode: Multi-account hedged racing for lowest latency
for chunk in pool.boost_completion("Explain quantum computing"):
    if chunk['type'] == 'text':
        print(chunk['content'], end='', flush=True)

# 4. /learn Mode: Auto-discover tokens and benchmark latency
report = pool.learn(auto_add=True, benchmark=True)
print(f"Discovered: {report['discovered_count']} | Average latency: {report['average_latency_ms']}ms")
```

### Interactive CLI & Runner (`example_pool.py`):

Launch the interactive chat shell with built-in slash commands:
```bash
# Start interactive chat REPL
python example_pool.py

# Check pool status and health table
python example_pool.py --status

# Auto-discover and benchmark tokens
python example_pool.py --learn

# Run a boosted prompt directly
python example_pool.py --boost "What is 2+2?"
```

#### Interactive Slash Commands:
| Command | Description |
|---|---|
| `/boost [prompt]` | Toggle boost mode ON/OFF, or execute a single query with multi-account acceleration |
| `/learn` | Auto-discover tokens from files/.env, benchmark latency, and optimize pool |
| `/status` | View live visual health dashboard, request counts, and account response times |
| `/tokens` | List registered accounts with masked identifiers and performance metrics |
| `/add <token>` | Dynamically register a new account token into the active pool |
| `/remove <token>` | Remove an account token from the pool |
| `/strategy <rr\|lru>` | Switch between Round-Robin and Least-Recently-Used balancing |
| `/reset` | Clear chat session and start a fresh conversation |
| `/help` | Display all available commands |
| `exit` | Quit interactive shell |
