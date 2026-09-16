#!/usr/bin/env bash
# ==============================================================================
# DeepSeek4Free VPS Automated Deploy & Auto-Update Setup Script
# Works on Ubuntu 20.04 / 22.04 / 24.04 LTS & Debian 11/12
# ==============================================================================

set -e

GREEN="\033[0;32m"
SKY="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

echo -e "${SKY}"
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║          🚀 DEEPSEEK4FREE — VPS AUTO-DEPLOY & AUTO-UPDATE           ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check root privileges
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Skrip ini harus dijalankan sebagai root atau dengan sudo!${NC}"
    exit 1
fi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo -e "${SKY}[1/6] Menginstal dependensi sistem (Python3, Git, Curl)...${NC}"
if command -v apt-get &> /dev/null; then
    apt-get update -qq
    apt-get install -y -qq python3 python3-venv python3-pip git curl
elif command -v dnf &> /dev/null; then
    dnf install -y python3 python3-pip git curl
fi

echo -e "${SKY}[2/6] Menyiapkan Virtual Environment Python (.venv)...${NC}"
if [ ! -d "$APP_DIR/.venv" ]; then
    python3 -m venv "$APP_DIR/.venv"
fi
VENV_PYTHON="$APP_DIR/.venv/bin/python"
VENV_PIP="$APP_DIR/.venv/bin/pip"

echo -e "${SKY}[3/6] Menginstal library Python (requirements.txt)...${NC}"
"$VENV_PIP" install --upgrade pip --quiet
if [ -f "$APP_DIR/requirements.txt" ]; then
    "$VENV_PIP" install -r "$APP_DIR/requirements.txt" --quiet
fi
# Ensure curl-cffi is installed
"$VENV_PIP" install "curl-cffi>=0.8.1" --quiet

echo -e "${SKY}[4/6] Menyiapkan file konfigurasi environment (.env)...${NC}"
if [ ! -f "$APP_DIR/.env" ]; then
    AUTH_SECRET=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32)
    WEBHOOK_SECRET=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 24)
    cat <<EOF > "$APP_DIR/.env"
# DeepSeek4Free VPS Production Environment
PORT=8990
HOST=0.0.0.0
ADMIN_PASSWORD=admin
AUTH_SECRET_KEY=${AUTH_SECRET}

# Auto-Updater Settings
AUTO_UPDATE_ENABLED=true
AUTO_UPDATE_INTERVAL=2
AUTO_UPDATE_BRANCH=main
GITHUB_WEBHOOK_SECRET=${WEBHOOK_SECRET}
EOF
    chmod 600 "$APP_DIR/.env"
    echo -e "${GREEN}✓ File .env berhasil dibuat dengan kunci rahasia acak.${NC}"
else
    # Ensure auto updater variables exist
    if ! grep -q "AUTO_UPDATE_ENABLED" "$APP_DIR/.env"; then
        echo "AUTO_UPDATE_ENABLED=true" >> "$APP_DIR/.env"
        echo "AUTO_UPDATE_INTERVAL=2" >> "$APP_DIR/.env"
        echo "AUTO_UPDATE_BRANCH=main" >> "$APP_DIR/.env"
    fi
    echo -e "${GREEN}✓ File .env sudah ada, mempertahankan konfigurasi saat ini.${NC}"
fi

echo -e "${SKY}[5/6] Mendaftarkan Systemd Service (deepseek4free.service)...${NC}"
SERVICE_PATH="/etc/systemd/system/deepseek4free.service"
cat <<EOF > "$SERVICE_PATH"
[Unit]
Description=DeepSeek4Free Multi-Account Token Pool & OpenAI API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
EnvironmentFile=-$APP_DIR/.env
ExecStart=$VENV_PYTHON $APP_DIR/web_server.py
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable deepseek4free
systemctl restart deepseek4free

echo -e "${SKY}[6/6] Memverifikasi status layanan...${NC}"
sleep 2

if systemctl is-active --quiet deepseek4free; then
    SERVER_IP=$(curl -s -4 ifconfig.me || hostname -I | awk '{print $1}')
    WEBHOOK_SECRET_VAL=$(grep GITHUB_WEBHOOK_SECRET "$APP_DIR/.env" | cut -d '=' -f2)
    
    echo -e "${GREEN}======================================================================${NC}"
    echo -e "${GREEN}🎉 DEEPSEEK4FREE BERHASIL DIPASANG & BERJALAN AKTIF DI VPS!${NC}"
    echo -e "${GREEN}======================================================================${NC}"
    echo -e "👉 Dashboard URL:      ${SKY}http://${SERVER_IP}:8990${NC}"
    echo -e "👉 OpenAI Endpoint:     ${SKY}http://${SERVER_IP}:8990/v1${NC}"
    echo -e "👉 GitHub Webhook URL:  ${SKY}http://${SERVER_IP}:8990/api/webhook/github${NC}"
    if [ -n "$WEBHOOK_SECRET_VAL" ]; then
        echo -e "👉 Webhook Secret:      ${YELLOW}${WEBHOOK_SECRET_VAL}${NC}"
    fi
    echo ""
    echo -e "${YELLOW}⚡ CARA AKTIFKAN AUTO-UPDATE DI GITHUB:${NC}"
    echo -e "1. Buka Repository Anda di GitHub -> Masuk ke ${SKY}Settings${NC} -> ${SKY}Webhooks${NC} -> ${SKY}Add webhook${NC}"
    echo -e "2. Masukkan Payload URL: ${SKY}http://${SERVER_IP}:8990/api/webhook/github${NC}"
    echo -e "3. Content type:         ${SKY}application/json${NC}"
    if [ -n "$WEBHOOK_SECRET_VAL" ]; then
        echo -e "4. Secret:               ${YELLOW}${WEBHOOK_SECRET_VAL}${NC}"
    fi
    echo -e "5. Events:               Pilih ${SKY}Just the push event${NC}"
    echo -e "6. Klik ${GREEN}Add webhook${NC}. Selesai!"
    echo -e "   -> Setiap kali Anda commit & push ke GitHub, VPS akan OTOMATIS terupdate & restart!"
    echo ""
    echo -e "${SKY}Perintah Bermanfaat di VPS:${NC}"
    echo -e "- Cek Status:  ${YELLOW}systemctl status deepseek4free${NC}"
    echo -e "- Cek Logs:    ${YELLOW}journalctl -u deepseek4free -f${NC}"
    echo -e "- Restart:     ${YELLOW}systemctl restart deepseek4free${NC}"
    echo -e "- Update Manual: ${YELLOW}./update.sh${NC}"
    echo -e "${GREEN}======================================================================${NC}"
else
    echo -e "${RED}❌ Layanan gagal dijalankan! Periksa log dengan:${NC}"
    echo "journalctl -u deepseek4free -n 50 --no-pager"
fi
