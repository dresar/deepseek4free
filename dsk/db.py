import os
import sys
import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional

class JSONDatabase:
    def __init__(self, db_path: Optional[str] = None):
        self._lock = threading.Lock()
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            base_dir = Path(__file__).parent.parent.resolve()
            self.db_path = base_dir / "data" / "database.json"
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = self._load()

    def _default_schema(self) -> Dict[str, Any]:
        return {
            "version": "1.0.0",
            "settings": {
                "port": 8990,
                "host": "0.0.0.0",
                "strategy": "round_robin",
                "boost_enabled": False,
                "thinking_enabled": True,
                "search_enabled": True
            },
            "tokens": [],
            "sessions": {},
            "stats": {
                "total_requests": 0,
                "total_tokens_sent": 0,
                "total_tokens_received": 0,
                "last_started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
        }

    def _load(self) -> Dict[str, Any]:
        with self._lock:
            if not self.db_path.exists():
                data = self._default_schema()
                self._save_unlocked(data)
                return data
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    schema = self._default_schema()
                    for key, val in schema.items():
                        if key not in content:
                            content[key] = val
                    return content
            except Exception:
                data = self._default_schema()
                self._save_unlocked(data)
                return data

    def _save_unlocked(self, data: Dict[str, Any]):
        temp_file = self.db_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_file.replace(self.db_path)

    def save(self):
        with self._lock:
            self._save_unlocked(self._data)

    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def get_settings(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data.get("settings", {}))

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._data.setdefault("settings", {}).update(updates)
            self._save_unlocked(self._data)
            return dict(self._data["settings"])

    def get_tokens(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._data.get("tokens", []))

    def set_tokens(self, tokens_list: List[Dict[str, Any]]):
        with self._lock:
            self._data["tokens"] = tokens_list
            self._save_unlocked(self._data)

    def upsert_token(self, token: str, label: Optional[str] = None, status: str = "healthy") -> Dict[str, Any]:
        with self._lock:
            tokens = self._data.setdefault("tokens", [])
            existing = next((t for t in tokens if t["token"] == token), None)
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if existing:
                existing["status"] = status
                if label:
                    existing["label"] = label
                existing["last_updated"] = now_iso
                item = existing
            else:
                item = {
                    "token": token,
                    "label": label or f"Account {len(tokens) + 1}",
                    "status": status,
                    "success_count": 0,
                    "error_count": 0,
                    "latency_ms": 0,
                    "created_at": now_iso,
                    "last_used": None
                }
                tokens.append(item)
            self._save_unlocked(self._data)
            return item

    def remove_token(self, token: str) -> bool:
        with self._lock:
            tokens = self._data.setdefault("tokens", [])
            initial_len = len(tokens)
            self._data["tokens"] = [t for t in tokens if t["token"] != token]
            changed = len(self._data["tokens"]) != initial_len
            if changed:
                self._save_unlocked(self._data)
            return changed

    def record_token_metrics(self, token: str, success: bool, latency_ms: int = 0):
        with self._lock:
            tokens = self._data.setdefault("tokens", [])
            existing = next((t for t in tokens if t["token"] == token), None)
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if existing:
                if success:
                    existing["success_count"] = existing.get("success_count", 0) + 1
                    existing["status"] = "healthy"
                else:
                    existing["error_count"] = existing.get("error_count", 0) + 1
                if latency_ms > 0:
                    existing["latency_ms"] = latency_ms
                existing["last_used"] = now_iso
            stats = self._data.setdefault("stats", {})
            stats["total_requests"] = stats.get("total_requests", 0) + 1
            self._save_unlocked(self._data)

    def save_chat_message(self, session_id: str, role: str, content: str, model: str = "deepseek-reasoner"):
        with self._lock:
            sessions = self._data.setdefault("sessions", {})
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if session_id not in sessions:
                sessions[session_id] = {
                    "session_id": session_id,
                    "title": content[:40] if role == "user" else "Chat Session",
                    "model": model,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "messages": []
                }
            session = sessions[session_id]
            session["updated_at"] = now_iso
            session["messages"].append({
                "role": role,
                "content": content,
                "timestamp": now_iso
            })
            if len(session["messages"]) > 100:
                session["messages"] = session["messages"][-100:]
            self._save_unlocked(self._data)

    def get_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            sessions = self._data.get("sessions", {})
            result = []
            for s in sessions.values():
                result.append({
                    "session_id": s.get("session_id"),
                    "title": s.get("title", "Chat Session"),
                    "model": s.get("model", "deepseek-reasoner"),
                    "created_at": s.get("created_at"),
                    "updated_at": s.get("updated_at"),
                    "message_count": len(s.get("messages", []))
                })
            result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return result

    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            session = self._data.get("sessions", {}).get(session_id)
            if not session:
                return []
            return list(session.get("messages", []))

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            sessions = self._data.setdefault("sessions", {})
            if session_id in sessions:
                del sessions[session_id]
                self._save_unlocked(self._data)
                return True
            return False

db = JSONDatabase()
