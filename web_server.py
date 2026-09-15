import os
import sys
import time
import json
import asyncio
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dsk.pool import DeepSeekPool, PoolError, NoAvailableTokensError

# Initialize FastAPI App
app = FastAPI(
    title="DeepSeek4Free - Web Playground & Multi-Account Router",
    description="Lightweight VPS Web Server, Multi-Account Token Pool & OpenAI-Compatible API",
    version="1.0.0"
)

# Enable CORS for universal integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global pool instance
pool = DeepSeekPool()

HTML_FILE_PATH = BASE_DIR / "web" / "index.html"


# ==============================================================================
# Pydantic Request Models
# ==============================================================================

class PlaygroundChatRequest(BaseModel):
    prompt: str
    model: str = "deepseek-reasoner"
    thinking_enabled: bool = True
    boost_enabled: bool = False
    search_enabled: bool = True
    session_id: Optional[str] = None


class AddTokensRequest(BaseModel):
    tokens_raw: str
    save_disk: bool = True


class RemoveTokenRequest(BaseModel):
    token: str


class SettingsRequest(BaseModel):
    strategy: Optional[str] = None
    boost_enabled: Optional[bool] = None


class OpenAIMessage(BaseModel):
    role: str
    content: str


class OpenAIChatRequest(BaseModel):
    model: str = "deepseek-chat"
    messages: List[OpenAIMessage]
    stream: bool = False
    temperature: Optional[float] = 1.0


# ==============================================================================
# Web UI & Static Routes
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the single-page web UI playground"""
    if HTML_FILE_PATH.exists():
        with open(HTML_FILE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>web/index.html not found</h1>"


@app.get("/health")
async def health_check():
    """Health check endpoint for VPS monitors and Docker"""
    status = pool.get_status()
    return {
        "status": "ok",
        "healthy_tokens": status.get("healthy", 0),
        "total_tokens": status.get("total_tokens", 0)
    }


# ==============================================================================
# Pool Management API
# ==============================================================================

@app.get("/api/status")
async def get_pool_status():
    """Return live metrics and status of all accounts in the pool"""
    return pool.get_status()


@app.post("/api/settings")
async def update_settings(req: SettingsRequest):
    """Update load balancing strategy and default boost mode"""
    if req.strategy in ("round_robin", "lru"):
        pool.strategy = req.strategy
    if req.boost_enabled is not None:
        pool.set_boost(req.boost_enabled)
    return {"status": "ok", "strategy": pool.strategy, "boost_enabled": pool.boost_enabled}


@app.post("/api/tokens/add")
async def add_tokens(req: AddTokensRequest):
    """Add one or bulk tokens to the pool"""
    lines = [line.strip() for line in req.tokens_raw.replace(",", "\n").split("\n") if line.strip()]
    added = 0
    for tok in lines:
        if tok.startswith("#") or tok.startswith("//"):
            continue
        clean_tok = tok.split("#")[0].split("//")[0].strip()
        if clean_tok:
            try:
                pool.add_token(clean_tok)
                added += 1
            except Exception:
                pass

    if req.save_disk:
        tokens_file = BASE_DIR / "tokens.txt"
        with open(tokens_file, "w", encoding="utf-8") as f:
            for t in pool.get_tokens():
                f.write(t + "\n")

    return {"status": "ok", "added": added, "total": len(pool.get_tokens())}


@app.post("/api/tokens/remove")
async def remove_token(req: RemoveTokenRequest):
    """Remove a token from the pool"""
    pool.remove_token(req.token)
    return {"status": "ok", "remaining": len(pool.get_tokens())}


@app.post("/api/learn")
async def run_learn():
    """Trigger /learn auto-discovery and live latency benchmark"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: pool.learn(benchmark=True, auto_add=True))
    return result


@app.get("/api/export")
async def export_tokens():
    """Download current pool tokens as tokens.txt"""
    content = "\n".join(pool.get_tokens()) + "\n"
    return PlainTextResponse(
        content,
        headers={"Content-Disposition": "attachment; filename=tokens.txt"}
    )


# ==============================================================================
# Playground Chat Streaming API (SSE)
# ==============================================================================

@app.post("/api/chat")
async def playground_chat(req: PlaygroundChatRequest):
    """Stream chat responses for the web playground UI with Thinking and Boost support"""
    # Determine thinking mode: deepseek-reasoner forces thinking_enabled
    thinking_enabled = req.thinking_enabled or (req.model == "deepseek-reasoner")

    def event_generator():
        try:
            # Use boost_completion if requested or pool default
            if req.boost_enabled:
                stream = pool.boost_completion(
                    prompt=req.prompt,
                    chat_session_id=req.session_id,
                    thinking_enabled=thinking_enabled,
                    search_enabled=req.search_enabled
                )
            else:
                stream = pool.chat_completion(
                    prompt=req.prompt,
                    chat_session_id=req.session_id,
                    thinking_enabled=thinking_enabled,
                    search_enabled=req.search_enabled
                )

            token_used = pool.last_used_token or "pool"
            session_id = pool.last_used_session_id or req.session_id

            for chunk in stream:
                c_type = chunk.get("type", "text")
                content = chunk.get("content", "")
                if content:
                    payload = {
                        "type": c_type,
                        "content": content,
                        "session_id": session_id,
                        "token_used": token_used
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

            yield "data: [DONE]\n\n"

        except NoAvailableTokensError as e:
            err = {"type": "error", "content": f"⚠️ Semua akun sedang cooldown. Coba lagi dalam beberapa saat: {str(e)}"}
            yield f"data: {json.dumps(err)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            err = {"type": "error", "content": f"❌ Error: {str(e)}"}
            yield f"data: {json.dumps(err)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ==============================================================================
# OpenAI-Compatible Endpoints (/v1/models, /v1/chat/completions)
# ==============================================================================

@app.get("/v1/models")
async def list_models():
    """Return OpenAI-compatible models list"""
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": "deepseek-chat",
                "object": "model",
                "created": now,
                "owned_by": "deepseek4free",
                "permission": [],
                "root": "deepseek-chat",
                "parent": None
            },
            {
                "id": "deepseek-reasoner",
                "object": "model",
                "created": now,
                "owned_by": "deepseek4free",
                "permission": [],
                "root": "deepseek-reasoner",
                "parent": None
            }
        ]
    }


@app.post("/v1/chat/completions")
async def openai_chat_completions(req: OpenAIChatRequest):
    """OpenAI-compatible chat completion endpoint supporting streaming and non-streaming"""
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages list cannot be empty")

    # Format user prompt: join system & conversation messages cleanly
    prompt_parts = []
    for msg in req.messages:
        if msg.role == "system":
            prompt_parts.append(f"[System instruction: {msg.content}]")
        elif msg.role == "user":
            prompt_parts.append(msg.content)
        elif msg.role == "assistant":
            prompt_parts.append(f"[Assistant previously: {msg.content}]")

    full_prompt = "\n\n".join(prompt_parts)
    thinking_enabled = req.model == "deepseek-reasoner"
    req_id = f"chatcmpl-{int(time.time() * 1000)}"
    created_time = int(time.time())

    # --- Case 1: Streaming Response ---
    if req.stream:
        def stream_openai_generator():
            try:
                stream = pool.chat_completion(
                    prompt=full_prompt,
                    thinking_enabled=thinking_enabled
                )
                for chunk in stream:
                    c_type = chunk.get("type", "text")
                    content = chunk.get("content", "")
                    if not content:
                        continue

                    # In OpenAI format for reasoning models (DeepSeek-R1), thinking is in delta.reasoning_content
                    delta = {}
                    if c_type == "thinking":
                        delta["reasoning_content"] = content
                    else:
                        delta["content"] = content

                    chunk_data = {
                        "id": req_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": req.model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": delta,
                                "finish_reason": None
                            }
                        ]
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"

                # Final stop chunk
                stop_chunk = {
                    "id": req_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": req.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }
                    ]
                }
                yield f"data: {json.dumps(stop_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            except Exception as e:
                err_chunk = {
                    "error": {
                        "message": str(e),
                        "type": "server_error",
                        "code": 500
                    }
                }
                yield f"data: {json.dumps(err_chunk)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(stream_openai_generator(), media_type="text/event-stream")

    # --- Case 2: Non-Streaming Response ---
    try:
        stream = pool.chat_completion(
            prompt=full_prompt,
            thinking_enabled=thinking_enabled
        )
        full_content = []
        reasoning_content = []
        for chunk in stream:
            c_type = chunk.get("type", "text")
            content = chunk.get("content", "")
            if c_type == "thinking":
                reasoning_content.append(content)
            else:
                full_content.append(content)

        text_response = "".join(full_content)
        msg_obj = {
            "role": "assistant",
            "content": text_response
        }
        if reasoning_content:
            msg_obj["reasoning_content"] = "".join(reasoning_content)

        return {
            "id": req_id,
            "object": "chat.completion",
            "created": created_time,
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": msg_obj,
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(full_prompt) // 4,
                "completion_tokens": len(text_response) // 4,
                "total_tokens": (len(full_prompt) + len(text_response)) // 4
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# Server Entrypoint
# ==============================================================================

def run_server():
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")

    print("\n" + "=" * 70)
    print("🚀 DeepSeek4Free Web Server Running!")
    print(f"👉 Local Web Playground: http://localhost:{port}")
    print(f"👉 OpenAI Base URL:      http://localhost:{port}/v1")
    print(f"👉 Pool Status API:      http://localhost:{port}/api/status")
    print("=" * 70 + "\n")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
