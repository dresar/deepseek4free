#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "🚀 Memulai DeepSeek4Free Web Server di VPS..."
echo "=========================================================="

if [ ! -d ".venv" ]; then
    echo "📦 Membuat virtual environment .venv..."
    python3 -m venv .venv
fi

source .venv/bin/activate
echo "📦 Memeriksa dependencies..."
pip install -r requirements.txt -q

export PORT=${PORT:-8000}
export HOST=${HOST:-0.0.0.0}

echo "🌐 Server berjalan di http://$HOST:$PORT"
python web_server.py
