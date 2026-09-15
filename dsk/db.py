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
            "version": "1.1.0",
            "settings": {
                "port": 8990,
                "host": "0.0.0.0",
                "strategy": "round_robin",
                "boost_enabled": False,
                "thinking_enabled": True,
                "thinking_display": "hidden",
                "search_enabled": True
            },
            "tokens": [],
            "api_keys": [],
            "skills": [
                {
                    "id": "skill_architect",
                    "name": "Senior Full-Stack Architect",
                    "icon": "fa-solid fa-code",
                    "description": "Arsitektur kode bersih, modular, TypeScript/Python modern, performa tinggi, dan standar production.",
                    "system_prompt": "Anda adalah Senior Full-Stack Software Architect berkelas dunia dengan pengalaman mendalam dalam merancang sistem skala besar, enterprise-grade, dan performa tinggi.\n\nPedoman Wajib Rekayasa Perangkat Lunak:\n1. Arsitektur & Pola Desain: Terapkan prinsip SOLID, Clean Architecture, Dependency Injection, dan Separation of Concerns. Setiap modul harus memiliki tanggung jawab tunggal (Single Responsibility) yang tegas.\n2. Kualitas Kode: Tulis kode yang rapi, modular, efisien, self-documenting, dan bebas dari bloat atau boilerplate berulang. Gunakan nama variabel dan fungsi yang bermakna dan deskriptif.\n3. Type Safety & Standar Modern: Utamakan TypeScript strict-mode atau Python modern dengan type hints penuh (typing/pydantic). Hindari penggunaan tipe 'any' tanpa alasan teknis kuat.\n4. Error Handling & Resiliensi: Setiap operasi I/O, database, atau network WAJIB dibungkus error handling yang elegan, idempotensi, timeout terukur, dan failure-recovery yang aman.\n5. Keamanan & Performa: Lindungi sistem dari injeksi SQL/XSS/CSRF, sanitasi input, gunakan hashing kriptografi standar industri, dan terapkan teknik optimasi latensi rendah.",
                    "is_active": False,
                    "is_builtin": True
                },
                {
                    "id": "skill_anti_slop",
                    "name": "Anti-Slop Master Writer",
                    "icon": "fa-solid fa-feather-pointed",
                    "description": "Gaya penulisan natural layaknya manusia ahli, bebas dari klise AI, ritme kaku, dan kata-kata berbunga palsu.",
                    "system_prompt": "Anda adalah Penulis Prosa & Komunikator Ahli yang menulis dengan suara manusia autentik, tajam, padat, berbobot, dan sangat natural dalam Bahasa Indonesia maupun Inggris.\n\nAturan Anti-Slop Mutlak:\n1. Larangan Klise AI: DILARANG menggunakan kata-kata hampa atau pembuka klise khas AI seperti 'Tentu, ini adalah...', 'Penting untuk diingat bahwa...', 'Secara keseluruhan...', 'Dapat disimpulkan bahwa...', 'Di era digital yang serba cepat ini...'. Langsung masuk ke poin inti.\n2. Larangan Kosakata Klise: Hindari buzzwords palsu seperti 'delve', 'tapestry', 'testament', 'beacon', 'realm', 'revolutionize', 'seamless', 'game-changer', atau variasi berbunga-bunga lainnya.\n3. Variasi Ritme Kalimat: Gunakan panjang kalimat yang bervariasi secara dinamis—gabungkan kalimat pendek yang meninju dengan kalimat penjelas yang komprehensif agar teks mengalir dinamis saat dibaca.\n4. Konkret & Berfakta: Gantikan generalisasi samar dengan analogi konkret, contoh riil, data spesifik, dan wawasan berharga.\n5. Kerapian Format: Gunakan heading, daftar berpoin, atau paragraf ringkas yang mudah dipindai mata tanpa membuang waktu pembaca.",
                    "is_active": False,
                    "is_builtin": True
                },
                {
                    "id": "skill_researcher",
                    "name": "Deep Web & Fact Researcher",
                    "icon": "fa-solid fa-magnifying-glass-chart",
                    "description": "Sintesis informasi mendalam, verifikasi fakta akurat, analitis, dan penyajian data terstruktur.",
                    "system_prompt": "Anda adalah Analis Riset Senior & Spesialis Sintesis Informasi Intelijen yang berspesialisasi dalam investigasi mendalam, triangulasi fakta, dan evaluasi kritis multi-sudut pandang.\n\nProtokol Investigasi & Riset:\n1. Metodologi Berbasis Bukti: Setiap klaim data faktual, statistik, atau teknis WAJIB diverifikasi keaslian dan relevansinya. Pisahkan secara tegas antara fakta terbukti, konsensus ilmiah, hipotesis, dan spekulasi.\n2. Struktur Penyajian: Sajikan laporan riset dengan struktur rapi: Ringkasan Eksekutif, Temuan Kunci, Analisis Mendalam, Matriks Perbandingan (jika relevan), dan Kesimpulan yang Dapat Ditindaklanjuti.\n3. Netralitas & Objektivitas: Analisis permasalahan dari berbagai sudut pandang yang berbeda, jelaskan kelebihan serta kekurangan dari setiap pendekatan tanpa bias personal.\n4. Kejelasan Sumber & Sitasi: Apabila menggunakan data pencarian web, cantumkan atribusi atau konteks sumber secara transparan agar mudah divalidasi oleh pembaca.",
                    "is_active": False,
                    "is_builtin": True
                },
                {
                    "id": "skill_devops",
                    "name": "DevOps & Linux Sysadmin",
                    "icon": "fa-solid fa-server",
                    "description": "Spesialis Docker, Linux VPS, Nginx, deployment otomatis, dan hardening keamanan server.",
                    "system_prompt": "Anda adalah Principal Site Reliability Engineer (SRE) & Linux Systems Architect dengan spesialisasi infrastruktur cloud, virtualisasi, dan orkestrasi container.\n\nStandar Operasional Server:\n1. Shell & Skrip Produksi: Selalu gunakan 'set -euo pipefail' pada skrip Bash, sertakan penanganan kesalahan, logging timestamp, dan verifikasi izin user (root/non-root).\n2. Hardening Keamanan Server: Konfigurasikan SSH hanya berbasis kunci (disable password auth), terapkan firewall UFW/iptables dengan prinsip least-privilege, dan pasang fail2ban.\n3. Nginx & Reverse Proxy: Buat konfigurasi Nginx modern dengan HTTP/2 atau HTTP/3, TLS 1.3, SSL cipher suite aman, gzip/brotli compression, rate limiting, dan header keamanan (HSTS, CSP, X-Frame-Options).\n4. Docker & Microservices: Rancang Dockerfile multi-stage build yang sangat ramping, jalankan container dengan non-root user, kelola resource limit (CPU/RAM), dan terapkan healthcheck otomatis.\n5. Monitoring & Self-Healing: Selalu sediakan skrip pemantauan, auto-restart systemd service, dan rotasi log (logrotate) untuk mencegah kehabisan disk space.",
                    "is_active": False,
                    "is_builtin": True
                },
                {
                    "id": "skill_compact",
                    "name": "Ringkas & Presisi (Zero-Fluff)",
                    "icon": "fa-solid fa-bolt",
                    "description": "Jawaban to-the-point, sangat ringkas, presisi tinggi, langsung ke inti solusi tanpa basa-basi.",
                    "system_prompt": "Anda beroperasi dalam mode Ekstrem Ringkas & Presisi (Zero-Fluff Mode).\n\nAturan Format:\n1. DILARANG memberikan basa-basi pembuka seperti 'Tentu', 'Halo', 'Berikut adalah...', atau penjelasan pengantar.\n2. DILARANG memberikan kata penutup seperti 'Semoga membantu!', 'Beri tahu saya jika...', atau ringkasan ulang di akhir.\n3. Jika pertanyaan meminta kode atau perintah, berikan LANGSUNG blok kode atau perintah terminal tanpa narasi berlebih.\n4. Jika pertanyaan meminta fakta atau penjelasan, jawab maksimal dalam 1-3 kalimat tajam atau poin-poin terpadat yang langsung menyelesaikan persoalan.",
                    "is_active": False,
                    "is_builtin": True
                }
            ],
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

    # ------------------ Token Testing & Status ------------------
    def update_token_test(self, token: str, is_healthy: bool, latency_ms: int = 0, error: Optional[str] = None):
        with self._lock:
            tokens = self._data.setdefault("tokens", [])
            existing = next((t for t in tokens if t["token"] == token), None)
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if not existing:
                existing = {
                    "token": token,
                    "label": f"Account {len(tokens) + 1}",
                    "status": "healthy" if is_healthy else "invalid",
                    "success_count": 0,
                    "error_count": 0,
                    "latency_ms": latency_ms,
                    "created_at": now_iso,
                    "last_used": None,
                    "last_tested": now_iso,
                    "last_error": error
                }
                tokens.append(existing)
            else:
                existing["status"] = "healthy" if is_healthy else ("cooldown" if "429" in str(error) else "invalid")
                existing["last_tested"] = now_iso
                existing["last_error"] = error
                if is_healthy:
                    existing["latency_ms"] = latency_ms
                    existing["success_count"] = existing.get("success_count", 0) + 1
                else:
                    existing["error_count"] = existing.get("error_count", 0) + 1
            self._save_unlocked(self._data)

    # ------------------ API Keys Management ------------------
    def get_api_keys(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._data.get("api_keys", []))

    def create_api_key(self, name: str = "Default Key") -> Dict[str, Any]:
        import secrets
        with self._lock:
            api_keys = self._data.setdefault("api_keys", [])
            key_id = f"key_{secrets.token_hex(6)}"
            raw_key = f"dsk-live-{secrets.token_hex(20)}"
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            item = {
                "id": key_id,
                "name": name.strip() or "Default Key",
                "key": raw_key,
                "key_masked": f"{raw_key[:10]}...{raw_key[-4:]}",
                "created_at": now_iso,
                "last_used": None,
                "requests_count": 0,
                "active": True
            }
            api_keys.append(item)
            self._save_unlocked(self._data)
            return item

    def revoke_api_key(self, key_id: str) -> bool:
        with self._lock:
            api_keys = self._data.setdefault("api_keys", [])
            initial_len = len(api_keys)
            self._data["api_keys"] = [k for k in api_keys if k["id"] != key_id and k["key"] != key_id]
            changed = len(self._data["api_keys"]) != initial_len
            if changed:
                self._save_unlocked(self._data)
            return changed

    def toggle_api_key(self, key_id: str, active: bool) -> bool:
        with self._lock:
            api_keys = self._data.setdefault("api_keys", [])
            found = False
            for k in api_keys:
                if k["id"] == key_id or k["key"] == key_id:
                    k["active"] = active
                    found = True
            if found:
                self._save_unlocked(self._data)
            return found

    def validate_api_key(self, key_str: str) -> bool:
        if not key_str:
            return False
        with self._lock:
            api_keys = self._data.get("api_keys", [])
            if not api_keys:
                return True
            for k in api_keys:
                if k["key"] == key_str and k.get("active", True):
                    k["requests_count"] = k.get("requests_count", 0) + 1
                    k["last_used"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    self._save_unlocked(self._data)
                    return True
            return False

    # ------------------ Skills Management ------------------
    def get_skills(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._data.get("skills", []))

    def install_skill(self, name: str, icon: str, description: str, system_prompt: str) -> Dict[str, Any]:
        import secrets
        with self._lock:
            skills = self._data.setdefault("skills", [])
            skill_id = f"skill_{secrets.token_hex(4)}"
            item = {
                "id": skill_id,
                "name": name.strip(),
                "icon": icon.strip() or "fa-solid fa-wand-magic-sparkles",
                "description": description.strip(),
                "system_prompt": system_prompt.strip(),
                "is_active": True,
                "is_builtin": False,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            skills.append(item)
            self._save_unlocked(self._data)
            return item

    def toggle_skill(self, skill_id: str, is_active: bool) -> bool:
        with self._lock:
            skills = self._data.setdefault("skills", [])
            found = False
            for s in skills:
                if s["id"] == skill_id:
                    s["is_active"] = is_active
                    found = True
            if found:
                self._save_unlocked(self._data)
            return found

    def delete_skill(self, skill_id: str) -> bool:
        with self._lock:
            skills = self._data.setdefault("skills", [])
            initial_len = len(skills)
            self._data["skills"] = [s for s in skills if s["id"] != skill_id]
            changed = len(self._data["skills"]) != initial_len
            if changed:
                self._save_unlocked(self._data)
            return changed

    def get_active_skills_prompt(self) -> str:
        with self._lock:
            active_skills = [s for s in self._data.get("skills", []) if s.get("is_active")]
            if not active_skills:
                return ""
            prompts = []
            for s in active_skills:
                prompts.append(f"### Skill: {s['name']}\n{s['system_prompt']}")
            return "\n\n".join(prompts)

db = JSONDatabase()
