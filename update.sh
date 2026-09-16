#!/usr/bin/env bash
# ==============================================================================
# DeepSeek4Free Standalone Auto-Update Script (Manual or Cron)
# ==============================================================================

set -e
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

BRANCH="main"
if [ -f "$APP_DIR/.env" ]; then
    ENV_BRANCH=$(grep -E "^AUTO_UPDATE_BRANCH=" "$APP_DIR/.env" | cut -d '=' -f2)
    if [ -n "$ENV_BRANCH" ]; then
        BRANCH="$ENV_BRANCH"
    fi
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Memeriksa pembaruan dari origin/$BRANCH..."

# Check current and remote commit
git fetch origin "$BRANCH" --quiet
LOCAL_COMMIT=$(git rev-parse HEAD)
REMOTE_COMMIT=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL_COMMIT" = "$REMOTE_COMMIT" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Codebase sudah pada versi terbaru ($LOCAL_COMMIT)."
    exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pembaruan ditemukan: $LOCAL_COMMIT -> $REMOTE_COMMIT. Memulai update..."

# Reset hard to origin branch to preserve clean tree while keeping ignored files (.env, data/)
git reset --hard "origin/$BRANCH"

# Reinstall python requirements if venv exists
if [ -d "$APP_DIR/.venv" ]; then
    "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet
fi

# Restart systemd service if running
if command -v systemctl &> /dev/null && systemctl is-active --quiet deepseek4free; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Me-restart layanan systemd deepseek4free..."
    systemctl restart deepseek4free
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sukses! DeepSeek4Free telah diperbarui ke $REMOTE_COMMIT."
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Kode berhasil diperbarui ke $REMOTE_COMMIT."
fi
