import os
import sys
import time
import subprocess
import threading
import logging

logger = logging.getLogger("auto_updater")

UPDATE_ENABLED = os.environ.get("AUTO_UPDATE_ENABLED", "false").lower() == "true"
UPDATE_INTERVAL = int(os.environ.get("AUTO_UPDATE_INTERVAL", "30")) * 60
UPDATE_BRANCH = os.environ.get("AUTO_UPDATE_BRANCH", "main")


def get_current_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return None


def fetch_remote_commit():
    try:
        subprocess.run(
            ["git", "fetch", "origin", UPDATE_BRANCH],
            capture_output=True, timeout=30
        )
        result = subprocess.run(
            ["git", "rev-parse", f"origin/{UPDATE_BRANCH}"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return None


def pull_latest():
    try:
        result = subprocess.run(
            ["git", "pull", "origin", UPDATE_BRANCH],
            capture_output=True, text=True, timeout=60
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def install_requirements():
    try:
        pip = sys.executable.replace("python", "pip").replace("python3", "pip3")
        subprocess.run(
            [pip, "install", "-r", "requirements.txt", "-q"],
            timeout=120
        )
    except Exception:
        pass


def restart_server():
    logger.info("Restarting server after update...")
    os.execv(sys.executable, [sys.executable] + sys.argv)


def update_loop():
    logger.info(f"Auto-updater started — interval: {UPDATE_INTERVAL // 60}m, branch: {UPDATE_BRANCH}")
    while True:
        time.sleep(UPDATE_INTERVAL)
        try:
            local = get_current_commit()
            remote = fetch_remote_commit()
            if not local or not remote:
                continue
            if local == remote:
                continue
            logger.info(f"Update available: {local[:8]} → {remote[:8]}")
            success, output = pull_latest()
            if success:
                logger.info(f"Pull OK: {output}")
                install_requirements()
                restart_server()
            else:
                logger.warning(f"Pull failed: {output}")
        except Exception as e:
            logger.error(f"Update check failed: {e}")


def start_auto_updater():
    if not UPDATE_ENABLED:
        return
    if sys.platform != "linux":
        logger.info("Auto-updater: Linux only, skipping")
        return
    t = threading.Thread(target=update_loop, daemon=True, name="auto-updater")
    t.start()
    logger.info("Auto-updater thread started")
