import os
import sys
import time
import json
import hmac
import hashlib
import secrets
import asyncio
import base64
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from typing import Optional, List
from auto_updater import start_auto_updater
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent.resolve()

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dsk.pool import DeepSeekPool, NoAvailableTokensError
from dsk.db import db

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "")

if not AUTH_SECRET_KEY:
    AUTH_SECRET_KEY = secrets.token_hex(32)
    env_path = BASE_DIR / ".env"
    try:
        content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        if "AUTH_SECRET_KEY=" in content:
            lines = content.splitlines()
            new_lines = []
            for line in lines:
                if line.startswith("AUTH_SECRET_KEY="):
                    new_lines.append(f"AUTH_SECRET_KEY={AUTH_SECRET_KEY}")
                else:
                    new_lines.append(line)
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        else:
            with open(env_path, "a", encoding="utf-8") as f:
                f.write(f"\nAUTH_SECRET_KEY={AUTH_SECRET_KEY}\n")
    except Exception:
        pass

SESSION_STORE: dict[str, dict] = {}
SESSION_TTL = 86400 * 7

WEB_DIR = BASE_DIR / "web"
HTML_FILE_PATH = WEB_DIR / "index.html"
LOGIN_FILE_PATH = WEB_DIR / "login.html"


def create_session_token(username: str) -> str:
    payload = f"{username}:{int(time.time())}:{secrets.token_hex(16)}"
    sig = hmac.new(AUTH_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{payload}|{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_session_token(token: str) -> Optional[str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = raw.rsplit("|", 1)
        expected_sig = hmac.new(AUTH_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        parts = payload.split(":")
        username = parts[0]
        created_at = int(parts[1])
        if time.time() - created_at > SESSION_TTL:
            return None
        return username
    except Exception:
        return None


def extract_bearer_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get("session_token")


def require_auth(request: Request) -> str:
    token = extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    username = verify_session_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Session expired")
    return username


app = FastAPI(
    title="DeepSeek4Free",
    description="Multi-Account Token Pool & OpenAI-Compatible API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pool = DeepSeekPool()


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


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    token = extract_bearer_token(request)
    if token and verify_session_token(token):
        if HTML_FILE_PATH.exists():
            return HTML_FILE_PATH.read_text(encoding="utf-8")
        return "<h1>web/index.html not found</h1>"
    if LOGIN_FILE_PATH.exists():
        return LOGIN_FILE_PATH.read_text(encoding="utf-8")
    return "<h1>web/login.html not found</h1>"


@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    if LOGIN_FILE_PATH.exists():
        return LOGIN_FILE_PATH.read_text(encoding="utf-8")
    return "<h1>login.html not found</h1>"


@app.get("/web/{filename}")
async def serve_static(filename: str):
    allowed = {"style.css", "app.js", "auth.js", "login.html", "index.html"}
    if filename not in allowed:
        raise HTTPException(status_code=404)
    file_path = WEB_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404)
    media_types = {
        ".css": "text/css",
        ".js": "application/javascript",
        ".html": "text/html",
    }
    media_type = media_types.get(file_path.suffix, "text/plain")
    return PlainTextResponse(file_path.read_text(encoding="utf-8"), media_type=media_type)


@app.get("/health")
async def health_check():
    status = pool.get_status()
    return {
        "status": "ok",
        "healthy_tokens": status.get("healthy", 0),
        "total_tokens": status.get("total_tokens", 0)
    }


@app.post("/api/auth/login")
async def auth_login(req: LoginRequest):
    if req.username != ADMIN_USERNAME or req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Kredensial tidak valid")
    token = create_session_token(req.username)
    return {"token": token, "username": req.username}


@app.post("/api/auth/logout")
async def auth_logout(_: str = Depends(require_auth)):
    return {"status": "ok"}


@app.get("/api/auth/me")
async def auth_me(username: str = Depends(require_auth)):
    return {"username": username}


@app.post("/api/auth/change-password")
async def auth_change_password(req: ChangePasswordRequest, username: str = Depends(require_auth)):
    global ADMIN_PASSWORD
    if req.current_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=400, detail="Password saat ini salah")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password min. 6 karakter")
    ADMIN_PASSWORD = req.new_password
    env_path = BASE_DIR / ".env"
    try:
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            new_lines = []
            for line in lines:
                if line.startswith("ADMIN_PASSWORD="):
                    new_lines.append(f"ADMIN_PASSWORD={req.new_password}")
                else:
                    new_lines.append(line)
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception:
        pass
    return {"status": "ok"}


@app.get("/api/status")
async def get_pool_status(_: str = Depends(require_auth)):
    return pool.get_status()


@app.post("/api/settings")
async def update_settings(req: SettingsRequest, _: str = Depends(require_auth)):
    if req.strategy in ("round_robin", "lru"):
        pool.strategy = req.strategy
    if req.boost_enabled is not None:
        pool.set_boost(req.boost_enabled)
    return {"status": "ok", "strategy": pool.strategy, "boost_enabled": pool.boost_enabled}


@app.post("/api/tokens/add")
async def add_tokens(req: AddTokensRequest, _: str = Depends(require_auth)):
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
async def remove_token(req: RemoveTokenRequest, _: str = Depends(require_auth)):
    pool.remove_token(req.token)
    return {"status": "ok", "remaining": len(pool.get_tokens())}


@app.post("/api/learn")
async def run_learn(_: str = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: pool.learn(benchmark=True, auto_add=True))
    return result


@app.get("/api/export")
async def export_tokens(_: str = Depends(require_auth)):
    content = "\n".join(pool.get_tokens()) + "\n"
    return PlainTextResponse(
        content,
        headers={"Content-Disposition": "attachment; filename=tokens.txt"}
    )


@app.post("/api/chat")
async def playground_chat(req: PlaygroundChatRequest, _: str = Depends(require_auth)):
    thinking_enabled = req.thinking_enabled or (req.model == "deepseek-reasoner")

    def event_generator():
        try:
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
            err = {"type": "error", "content": f"Semua akun cooldown. Coba lagi: {str(e)}"}
            yield f"data: {json.dumps(err)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            err = {"type": "error", "content": f"Error: {str(e)}"}
            yield f"data: {json.dumps(err)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/v1/models")
@app.get("/models")
async def list_models():
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
@app.post("/chat/completions")
async def openai_chat_completions(req: OpenAIChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages list cannot be empty")

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
                        "choices": [{"index": 0, "delta": delta, "finish_reason": None}]
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"

                stop_chunk = {
                    "id": req_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": req.model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(stop_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            except Exception as e:
                err_chunk = {"error": {"message": str(e), "type": "server_error", "code": 500}}
                yield f"data: {json.dumps(err_chunk)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(stream_openai_generator(), media_type="text/event-stream")

    try:
        stream = pool.chat_completion(prompt=full_prompt, thinking_enabled=thinking_enabled)
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
        msg_obj = {"role": "assistant", "content": text_response}
        if reasoning_content:
            msg_obj["reasoning_content"] = "".join(reasoning_content)

        return {
            "id": req_id,
            "object": "chat.completion",
            "created": created_time,
            "model": req.model,
            "choices": [{"index": 0, "message": msg_obj, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": len(full_prompt) // 4,
                "completion_tokens": len(text_response) // 4,
                "total_tokens": (len(full_prompt) + len(text_response)) // 4
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/anthropic/v1/messages")
@app.post("/v1/messages")
async def anthropic_messages(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages list cannot be empty")

    system_prompt = body.get("system", "")
    stream = body.get("stream", False)
    model = body.get("model", "deepseek-chat")
    thinking_enabled = "reasoner" in model or "r1" in model.lower()

    prompt_parts = []
    if system_prompt:
        prompt_parts.append(f"[System instruction: {system_prompt}]")
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            text_blocks = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
            content = " ".join(text_blocks)
        if role == "user":
            prompt_parts.append(str(content))
        elif role == "assistant":
            prompt_parts.append(f"[Assistant previously: {content}]")

    full_prompt = "\n\n".join(prompt_parts)
    msg_id = f"msg_{int(time.time() * 1000)}"

    if stream:
        def stream_anthropic():
            try:
                yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'content': [], 'model': model, 'stop_reason': None, 'usage': {'input_tokens': len(full_prompt) // 4, 'output_tokens': 1}}})}\n\n"
                yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"

                stream_res = pool.chat_completion(prompt=full_prompt, thinking_enabled=thinking_enabled)
                accumulated = []
                for chunk in stream_res:
                    text = chunk.get("content", "")
                    if text:
                        accumulated.append(text)
                        yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': text}})}\n\n"

                db.save_chat_message(msg_id, "user", full_prompt, model=model)
                db.save_chat_message(msg_id, "assistant", "".join(accumulated), model=model)
                yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
                yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}, 'usage': {'output_tokens': len(''.join(accumulated)) // 4}})}\n\n"
                yield 'event: message_stop\ndata: {"type": "message_stop"}\n\n'
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': {'type': 'api_error', 'message': str(e)}})}\n\n"

        return StreamingResponse(stream_anthropic(), media_type="text/event-stream")

    try:
        stream_res = pool.chat_completion(prompt=full_prompt, thinking_enabled=thinking_enabled)
        collected = []
        for chunk in stream_res:
            c = chunk.get("content", "")
            if c:
                collected.append(c)
        resp_text = "".join(collected)
        db.save_chat_message(msg_id, "user", full_prompt, model=model)
        db.save_chat_message(msg_id, "assistant", resp_text, model=model)
        return {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": resp_text}],
            "model": model,
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": len(full_prompt) // 4,
                "output_tokens": len(resp_text) // 4
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db")
async def get_database_status(_: str = Depends(require_auth)):
    return db.get_all()


@app.get("/api/sessions")
async def list_chat_sessions(_: str = Depends(require_auth)):
    return db.get_sessions()


@app.get("/api/sessions/{session_id}")
async def get_chat_session(session_id: str, _: str = Depends(require_auth)):
    return db.get_session_messages(session_id)


@app.delete("/api/sessions/{session_id}")
async def delete_chat_session(session_id: str, _: str = Depends(require_auth)):
    deleted = db.delete_session(session_id)
    return {"deleted": deleted}


def run_server():
    import uvicorn
    port = int(os.environ.get("PORT", 8990))
    host = os.environ.get("HOST", "0.0.0.0")

    print("\n" + "=" * 70)
    print("🚀 DeepSeek4Free Web Server Running!")
    print(f"👉 Dashboard:      http://localhost:{port}")
    print(f"👉 OpenAI API:     http://localhost:{port}/v1")
    print(f"👉 Anthropic API:  http://localhost:{port}/anthropic/v1")
    print(f"👉 Pool Status:    http://localhost:{port}/api/status")
    print(f"👉 Auth:           admin / {ADMIN_PASSWORD}")
    print("=" * 70 + "\n")

    start_auto_updater()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
