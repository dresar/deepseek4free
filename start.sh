#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "[start] Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "[start] Installing dependencies..."
pip install -r requirements.txt -q

export PORT="${PORT:-8990}"
export HOST="${HOST:-0.0.0.0}"
export AUTO_UPDATE_ENABLED="${AUTO_UPDATE_ENABLED:-false}"
export AUTO_UPDATE_INTERVAL="${AUTO_UPDATE_INTERVAL:-30}"
export AUTO_UPDATE_BRANCH="${AUTO_UPDATE_BRANCH:-main}"

echo "[start] Server running at http://$HOST:$PORT"
python web_server.py
