import os
import sys
import time
import subprocess
import threading
import logging
import hmac
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("auto_updater")
BASE_DIR = Path(__file__).resolve().parent

UPDATE_ENABLED = os.environ.get("AUTO_UPDATE_ENABLED", "true").lower() == "true"
UPDATE_INTERVAL = int(os.environ.get("AUTO_UPDATE_INTERVAL", "2")) * 60
UPDATE_BRANCH = os.environ.get("AUTO_UPDATE_BRANCH", "main")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "").strip()

_update_lock = threading.Lock()
_is_updating = False
_last_check_time = 0
_last_check_result: Dict[str, Any] = {}


def get_current_commit() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(BASE_DIR),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.debug(f"get_current_commit error: {e}")
    return None


def get_current_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(BASE_DIR),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return UPDATE_BRANCH


def fetch_remote_commit(branch: Optional[str] = None) -> Optional[str]:
    target_branch = branch or UPDATE_BRANCH
    try:
        subprocess.run(
            ["git", "fetch", "origin", target_branch],
            cwd=str(BASE_DIR),
            capture_output=True, timeout=30
        )
        result = subprocess.run(
            ["git", "rev-parse", f"origin/{target_branch}"],
            cwd=str(BASE_DIR),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.debug(f"fetch_remote_commit error: {e}")
    return None


def check_for_update() -> Dict[str, Any]:
    global _last_check_time, _last_check_result
    local = get_current_commit()
    remote = fetch_remote_commit()
    branch = get_current_branch()
    has_update = bool(local and remote and local != remote)

    _last_check_time = int(time.time())
    _last_check_result = {
        "current_commit": local[:8] if local else "unknown",
        "full_current_commit": local or "unknown",
        "remote_commit": remote[:8] if remote else "unknown",
        "full_remote_commit": remote or "unknown",
        "branch": branch,
        "has_update": has_update,
        "last_check_time": _last_check_time,
        "is_updating": _is_updating,
        "auto_update_enabled": UPDATE_ENABLED,
        "interval_seconds": UPDATE_INTERVAL
    }
    return _last_check_result


def execute_update_pipeline(target_branch: Optional[str] = None) -> Dict[str, Any]:
    global _is_updating
    branch = target_branch or UPDATE_BRANCH

    if not _update_lock.acquire(blocking=False):
        return {"status": "error", "message": "Proses pembaruan sedang berjalan"}

    _is_updating = True
    logger.info(f"Memulai pipeline update DeepSeek4Free (branch: {branch})...")
    output_log = []

    try:
        # 1. Fetch latest commits
        f_res = subprocess.run(
            ["git", "fetch", "origin", branch],
            cwd=str(BASE_DIR),
            capture_output=True, text=True, timeout=45
        )
        output_log.append(f"git fetch: {f_res.stdout.strip() or f_res.stderr.strip() or 'OK'}")

        # 2. Reset hard to origin to ensure a clean sync without merge conflicts
        # Note: gitignored files (.env, data/database.json, tokens.txt) are preserved!
        r_res = subprocess.run(
            ["git", "reset", "--hard", f"origin/{branch}"],
            cwd=str(BASE_DIR),
            capture_output=True, text=True, timeout=30
        )
        output_log.append(f"git reset: {r_res.stdout.strip() or r_res.stderr.strip() or 'OK'}")

        if r_res.returncode != 0:
            logger.error(f"Git reset failed: {r_res.stderr}")
            return {"status": "error", "message": f"Git reset gagal: {r_res.stderr}", "log": output_log}

        # 3. Update pip dependencies if requirements.txt exists
        req_file = BASE_DIR / "requirements.txt"
        if req_file.exists():
            pip_executable = sys.executable.replace("python.exe", "pip.exe").replace("python", "pip")
            p_res = subprocess.run(
                [pip_executable, "install", "-r", str(req_file), "--quiet"],
                cwd=str(BASE_DIR),
                capture_output=True, text=True, timeout=180
            )
            output_log.append(f"pip install: {p_res.stdout.strip() or 'OK'}")

        new_commit = get_current_commit() or "unknown"
        logger.info(f"Update berhasil! Versi terbaru: {new_commit[:8]}. Mempersiapkan restart...")

        # Schedule restart in a separate thread so this function returns cleanly
        threading.Thread(target=_delayed_restart, daemon=True).start()

        return {
            "status": "ok",
            "message": f"Berhasil memperbarui ke commit {new_commit[:8]}! Server sedang me-restart...",
            "commit": new_commit[:8],
            "log": output_log
        }

    except Exception as e:
        logger.error(f"Error during update pipeline: {e}")
        return {"status": "error", "message": str(e), "log": output_log}
    finally:
        _is_updating = False
        _update_lock.release()


def _delayed_restart():
    time.sleep(1.5)
    logger.info("Restarting server process...")

    # Check if managed by systemd
    try:
        c_res = subprocess.run(
            ["systemctl", "is-active", "deepseek4free"],
            capture_output=True, text=True, timeout=5
        )
        if c_res.returncode == 0 and c_res.stdout.strip() == "active":
            logger.info("Running under systemd service 'deepseek4free', issuing systemctl restart...")
            subprocess.run(["systemctl", "restart", "deepseek4free"], timeout=10)
            return
    except Exception:
        pass

    # Fallback to direct process replacement
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        logger.error(f"Direct execv restart failed: {e}. Exiting with 0 for supervisor restart...")
        sys.exit(0)


def verify_github_signature(payload_bytes: bytes, signature_header: Optional[str]) -> bool:
    if not GITHUB_WEBHOOK_SECRET:
        # If no secret configured, allow (open mode)
        return True
    if not signature_header:
        return False
    try:
        parts = signature_header.split("=", 1)
        if len(parts) != 2:
            return False
        algo, sig = parts
        if algo != "sha256":
            return False
        mac = hmac.new(GITHUB_WEBHOOK_SECRET.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256)
        expected = mac.hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


def update_loop():
    logger.info(f"Auto-updater background worker aktif — interval: {UPDATE_INTERVAL // 60} menit, branch: {UPDATE_BRANCH}")
    # Initial pause before first check
    time.sleep(30)
    while True:
        try:
            status = check_for_update()
            if status.get("has_update"):
                logger.info(f"Pembaruan terdeteksi di GitHub ({status.get('current_commit')} -> {status.get('remote_commit')})! Memulai auto-update...")
                execute_update_pipeline(UPDATE_BRANCH)
        except Exception as e:
            logger.error(f"Kesalahan pada auto-updater loop: {e}")
        time.sleep(UPDATE_INTERVAL)


def start_auto_updater():
    if not UPDATE_ENABLED:
        logger.info("Auto-updater dinonaktifkan (AUTO_UPDATE_ENABLED=false)")
        return
    # Auto-updater runs on Linux (VPS) or when explicitly configured
    if sys.platform != "linux" and os.environ.get("AUTO_UPDATE_FORCE", "").lower() != "true":
        logger.info("Auto-updater: dilewati di environment Windows lokal (aktif di Linux VPS)")
        return
    t = threading.Thread(target=update_loop, daemon=True, name="auto-updater-worker")
    t.start()
    logger.info("Thread Auto-Updater berhasil dijalankan")
