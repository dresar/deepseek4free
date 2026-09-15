@echo off
echo ==========================================================
echo 🚀 Memulai DeepSeek4Free Web Server di Windows...
echo ==========================================================

if not exist ".venv" (
    echo 📦 Virtual environment .venv tidak ditemukan.
    echo Silakan buat venv terlebih dahulu.
    pause
    exit /b 1
)

set PORT=8990
set HOST=0.0.0.0

echo 🌐 Server berjalan di http://localhost:8990
.venv\Scripts\python.exe web_server.py
