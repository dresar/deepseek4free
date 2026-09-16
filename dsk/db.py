import os
import sys
import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional

import re

def slugify(text: str) -> str:
    text = str(text or "").lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[-\s]+', '-', text).strip('-')


class JSONDatabase:
    def __init__(self, db_path: Optional[str] = None):
        self._lock = threading.Lock()
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            base_dir = Path(__file__).parent.parent.resolve()
            self.db_path = base_dir / "data" / "database.json"
        
        self.base_dir = self.db_path.parent.parent.resolve()
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
                    "id": "skill_autonomous_coder",
                    "name": "Autonomous Coder & Aider Specialist (Proaktif Edit & Create)",
                    "icon": "fa-solid fa-wand-magic-sparkles",
                    "description": "Instruksi wajib proaktif membuat file baru (scaffolding), edit SEARCH/REPLACE Aider, zero-excuses, dan anti-penolakan terminal.",
                    "system_prompt": "Anda adalah Autonomous Senior Developer & Pair Programming Specialist yang bekerja berdampingan dengan user via Aider CLI, Cursor, dan Claude Code.\n\nPROTOKOL WAJIB AUTONOMOUS CREATION & EDIT FILE (STRICT):\n\n1. PROAKTIF MEMBUAT FILE BARU (CREATE FROM SCRATCH):\n   - Jika user meminta instalasi project (misal: 'installkan next.js', 'buatkan react app', 'setup express api', 'buatkan script python'), atau meminta fitur baru di folder kosong:\n   - JANGAN PERNAH menolak atau beralasan 'saya hanya AI tidak bisa jalankan terminal' lalu tidak membuat file apa pun.\n   - JANGAN menunggu file ditambahkan ke chat jika file tersebut memang belum ada atau project masih baru!\n   - SEGERA BUATKAN file-file scaffold dasarnya secara nyata dan lengkap:\n     * File konfigurasi/manifest: package.json (lengkap dengan scripts dev/build dan dependencies yang valid), tsconfig.json, next.config.mjs, dll.\n     * File halaman/komponen: app/page.tsx, app/layout.tsx, atau entry point utama.\n     * Berikan perintah terminal 1-3 baris yang siap dieksekusi user (misal: npm install && npm run dev).\n\n2. FORMAT PENULISAN FILE (AIDER SEARCH/REPLACE COMPLIANT):\n   - Untuk MEMBUAT FILE BARU: Tulis nama path file di baris tersendiri, lalu buat blok SEARCH kosong dan REPLACE berisi seluruh isi file:\n     path/to/new_file.ext\n     <<<<<<< SEARCH\n     =======\n     isi file lengkap di sini\n     >>>>>>> REPLACE\n   - Untuk MENGEDIT FILE YANG SUDAH ADA:\n     path/to/existing_file.ext\n     <<<<<<< SEARCH\n     baris kode asli yang mau diganti persis\n     =======\n     baris kode baru penggantinya\n     >>>>>>> REPLACE\n   - DILARANG KERAS membuat blok markdown code triple backtick (```) tanpa nama file jika tujuannya adalah memodifikasi/membuat file, karena akan merusak parser Aider!\n\n3. KODE LENGKAP TANPA KEMALASAN (NO PLACEHOLDERS):\n   - Selalu tuliskan kode secara utuh dan fungsional.\n   - Dilarang keras menggunakan placeholder malas seperti '// ... rest of code ...', '// ... kode sebelumnya tetap sama ...'.\n   - Utamakan performa, clean code, dan zero error.",
                    "is_active": True,
                    "is_builtin": True
                },
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
                    existing_skill_ids = {s.get("id") for s in content.get("skills", [])}
                    for default_skill in schema.get("skills", []):
                        if default_skill.get("id") not in existing_skill_ids:
                            content.setdefault("skills", []).append(default_skill)
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
    def _parse_skill_file(self, skill_md_path: Path) -> Dict[str, Any]:
        try:
            content = skill_md_path.read_text(encoding="utf-8")
        except Exception:
            return {}

        meta = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                body = parts[2].strip()
                for line in frontmatter.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip().strip('"').strip("'")
        meta["system_prompt"] = body
        return meta

    def get_skills(self) -> List[Dict[str, Any]]:
        with self._lock:
            skills = self._data.setdefault("skills", [])
            skills_dir = self.base_dir / "skills"
            skills_dir.mkdir(parents=True, exist_ok=True)

            existing_folders = set()
            for s in skills:
                if not s.get("slug"):
                    if s.get("id") == "skill_anti_slop":
                        s["slug"] = "anti-slop-writing"
                    elif s.get("id") == "skill_architect":
                        s["slug"] = "senior-full-stack-architect"
                    elif s.get("id") == "skill_researcher":
                        s["slug"] = "deep-web-fact-researcher"
                    elif s.get("id") == "skill_devops":
                        s["slug"] = "devops-linux-sysadmin"
                    elif s.get("id") == "skill_compact":
                        s["slug"] = "zero-fluff-concise"
                    else:
                        s["slug"] = slugify(s.get("name", ""))

                slug = s["slug"]
                folder_path = skills_dir / slug
                if folder_path.exists() and folder_path.is_dir():
                    s["folder"] = slug
                    existing_folders.add(slug)
                    files_list = []
                    for f in folder_path.rglob("*"):
                        if f.is_file():
                            files_list.append(str(f.relative_to(folder_path)).replace("\\", "/"))
                    s["files"] = sorted(files_list)
                    s["file_count"] = len(files_list)
                else:
                    s["files"] = []
                    s["file_count"] = 0

            # Auto-discover any folder in skills/ not yet in DB
            import secrets
            for sub in skills_dir.iterdir():
                if sub.is_dir() and sub.name not in existing_folders:
                    skill_md = sub / "SKILL.md"
                    if not skill_md.exists():
                        skill_md = sub / "README.md"

                    parsed = self._parse_skill_file(skill_md) if skill_md.exists() else {}
                    name = parsed.get("name") or sub.name.replace("-", " ").title()
                    icon = parsed.get("icon") or "fa-solid fa-wand-magic-sparkles"
                    desc = parsed.get("description") or f"Skill dari folder {sub.name}"
                    prompt = parsed.get("system_prompt") or f"Instruksi skill {name}"

                    files_list = []
                    for f in sub.rglob("*"):
                        if f.is_file():
                            files_list.append(str(f.relative_to(sub)).replace("\\", "/"))

                    new_item = {
                        "id": f"skill_{secrets.token_hex(4)}",
                        "name": name,
                        "slug": sub.name,
                        "folder": sub.name,
                        "icon": icon,
                        "description": desc,
                        "system_prompt": prompt,
                        "is_active": False,
                        "is_builtin": False,
                        "files": sorted(files_list),
                        "file_count": len(files_list),
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    }
                    skills.append(new_item)
                    existing_folders.add(sub.name)

            self._save_unlocked(self._data)
            return list(skills)

    def install_skill(self, name: str, icon: str, description: str, system_prompt: str) -> Dict[str, Any]:
        import secrets
        with self._lock:
            skills = self._data.setdefault("skills", [])
            skill_id = f"skill_{secrets.token_hex(4)}"
            slug = slugify(name) or f"skill-{secrets.token_hex(3)}"

            skills_dir = self.base_dir / "skills" / slug
            skills_dir.mkdir(parents=True, exist_ok=True)
            skill_md = skills_dir / "SKILL.md"
            content = f"---\nname: {name.strip()}\nicon: {icon.strip()}\ndescription: {description.strip()}\n---\n\n{system_prompt.strip()}\n"
            try:
                skill_md.write_text(content, encoding="utf-8")
            except Exception:
                pass

            item = {
                "id": skill_id,
                "name": name.strip(),
                "slug": slug,
                "folder": slug,
                "icon": icon.strip() or "fa-solid fa-wand-magic-sparkles",
                "description": description.strip(),
                "system_prompt": system_prompt.strip(),
                "is_active": True,
                "is_builtin": False,
                "files": ["SKILL.md"],
                "file_count": 1,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            skills.append(item)
            self._save_unlocked(self._data)
            return item

    def update_skill(
        self,
        skill_id: str,
        name: str,
        icon: str,
        description: str,
        system_prompt: str
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            skills = self._data.setdefault("skills", [])
            skill = next((s for s in skills if s["id"] == skill_id), None)
            if not skill:
                return None

            skill["name"] = name.strip()
            skill["icon"] = icon.strip() or "fa-solid fa-wand-magic-sparkles"
            skill["description"] = description.strip()
            skill["system_prompt"] = system_prompt.strip()

            slug = skill.get("slug") or slugify(skill["name"])
            skill["slug"] = slug
            skills_dir = self.base_dir / "skills" / slug
            skills_dir.mkdir(parents=True, exist_ok=True)
            skill_md = skills_dir / "SKILL.md"
            content = f"---\nname: {skill['name']}\nicon: {skill['icon']}\ndescription: {skill['description']}\n---\n\n{skill['system_prompt']}\n"
            try:
                skill_md.write_text(content, encoding="utf-8")
            except Exception:
                pass

            files_list = []
            for f in skills_dir.rglob("*"):
                if f.is_file():
                    files_list.append(str(f.relative_to(skills_dir)).replace("\\", "/"))
            skill["files"] = sorted(files_list)
            skill["file_count"] = len(files_list)
            skill["folder"] = slug

            self._save_unlocked(self._data)
            return skill

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

    def delete_skill(self, skill_id: str, remove_files: bool = True) -> bool:
        with self._lock:
            skills = self._data.setdefault("skills", [])
            skill = next((s for s in skills if s["id"] == skill_id), None)
            if not skill:
                return False

            slug = skill.get("slug") or skill.get("folder")
            if remove_files and slug:
                import shutil
                skill_dir = self.base_dir / "skills" / slug
                if skill_dir.exists() and skill_dir.is_dir():
                    try:
                        shutil.rmtree(skill_dir)
                    except Exception:
                        pass

            self._data["skills"] = [s for s in skills if s["id"] != skill_id]
            self._save_unlocked(self._data)
            return True

    def get_skill_file(self, skill_id: str, rel_path: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            skills = self._data.setdefault("skills", [])
            skill = next((s for s in skills if s["id"] == skill_id), None)
            if not skill:
                return None
            slug = skill.get("slug") or skill.get("folder")
            if not slug:
                return None
            target = (self.base_dir / "skills" / slug / rel_path).resolve()
            base = (self.base_dir / "skills" / slug).resolve()
            if not str(target).startswith(str(base)) or not target.exists() or not target.is_file():
                return None
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
                return {
                    "path": rel_path,
                    "content": content,
                    "size": target.stat().st_size
                }
            except Exception as e:
                return {"error": str(e)}

    def save_skill_file(self, skill_id: str, rel_path: str, content: str) -> Dict[str, Any]:
        with self._lock:
            skills = self._data.setdefault("skills", [])
            skill = next((s for s in skills if s["id"] == skill_id), None)
            if not skill:
                return {"error": "Skill tidak ditemukan"}
            slug = skill.get("slug") or skill.get("folder")
            if not slug:
                return {"error": "Folder skill tidak valid"}

            clean_rel = rel_path.strip().replace("\\", "/").lstrip("/")
            base = (self.base_dir / "skills" / slug).resolve()
            target = (base / clean_rel).resolve()
            if not str(target).startswith(str(base)):
                return {"error": "Akses path dilarang"}

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

            if clean_rel.lower() in ("skill.md", "readme.md"):
                parsed = self._parse_skill_file(target)
                if parsed.get("name"):
                    skill["name"] = parsed["name"]
                if parsed.get("icon"):
                    skill["icon"] = parsed["icon"]
                if parsed.get("description"):
                    skill["description"] = parsed["description"]
                if parsed.get("system_prompt"):
                    skill["system_prompt"] = parsed["system_prompt"]

            files_list = []
            for f in base.rglob("*"):
                if f.is_file():
                    files_list.append(str(f.relative_to(base)).replace("\\", "/"))
            skill["files"] = sorted(files_list)
            skill["file_count"] = len(files_list)
            self._save_unlocked(self._data)

            return {
                "status": "ok",
                "path": clean_rel,
                "size": target.stat().st_size,
                "skill": skill
            }

    def create_skill_file(self, skill_id: str, rel_path: str, content: str = "") -> Dict[str, Any]:
        return self.save_skill_file(skill_id, rel_path, content)

    def delete_skill_file(self, skill_id: str, rel_path: str) -> Dict[str, Any]:
        with self._lock:
            skills = self._data.setdefault("skills", [])
            skill = next((s for s in skills if s["id"] == skill_id), None)
            if not skill:
                return {"error": "Skill tidak ditemukan"}
            slug = skill.get("slug") or skill.get("folder")
            if not slug:
                return {"error": "Folder skill tidak valid"}

            clean_rel = rel_path.strip().replace("\\", "/").lstrip("/")
            if clean_rel.lower() == "skill.md":
                return {"error": "File SKILL.md adalah file utama dan tidak boleh dihapus"}

            base = (self.base_dir / "skills" / slug).resolve()
            target = (base / clean_rel).resolve()
            if not str(target).startswith(str(base)) or not target.exists() or not target.is_file():
                return {"error": "File tidak ditemukan"}

            try:
                target.unlink()
            except Exception as e:
                return {"error": str(e)}

            files_list = []
            for f in base.rglob("*"):
                if f.is_file():
                    files_list.append(str(f.relative_to(base)).replace("\\", "/"))
            skill["files"] = sorted(files_list)
            skill["file_count"] = len(files_list)
            self._save_unlocked(self._data)

            return {"status": "ok", "deleted": clean_rel, "remaining_files": skill["files"]}

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
