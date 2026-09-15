#!/usr/bin/env bash
set -e

BRANCH="${AUTO_UPDATE_BRANCH:-main}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

echo "[update] Fetching from origin/$BRANCH..."
git fetch origin "$BRANCH"

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[update] Already up to date ($LOCAL)"
    exit 0
fi

echo "[update] Update found: $LOCAL -> $REMOTE"
git pull origin "$BRANCH"

if [ -f ".venv/bin/pip" ]; then
    echo "[update] Installing dependencies..."
    .venv/bin/pip install -r requirements.txt -q
fi

echo "[update] Done. Restart server to apply changes."
