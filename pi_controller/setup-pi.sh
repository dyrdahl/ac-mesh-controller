#!/bin/bash
# AC Control System - Pi Setup Script
# Sets up all dependencies for the mesh controller and web dashboard

set -e

PROJECT_DIR="$HOME/ac-mesh-controller/pi_controller"

echo "=== Updating system ==="
sudo apt update && sudo apt upgrade -y

echo "=== Installing system packages ==="
sudo apt install -y \
  pigpio \
  pigpiod \
  python3-pigpio \
  python3-spidev \
  python3-smbus \
  python3-smbus2 \
  python3-lgpio \
  python3-rpi.gpio \
  python3-gpiozero \
  python3-serial \
  python3-libgpiod \
  i2c-tools \
  gpiod \
  python3-pip \
  python3-venv \
  python3-dev \
  python3-full \
  libffi-dev \
  libpq-dev \
  postgresql \
  postgresql-contrib \
  nginx \
  curl

echo "=== Installing Node.js (for frontend build) ==="
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

echo "=== Enabling hardware interfaces ==="
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_serial_hw 0

echo "=== Setting up PostgreSQL database ==="
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Prompt for database password
read -sp "Enter PostgreSQL password for user 'pi': " DB_PASSWORD
echo

# Create database user and tables
sudo -u postgres psql -c "CREATE USER pi WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || \
  sudo -u postgres psql -c "ALTER USER pi WITH PASSWORD '$DB_PASSWORD';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE postgres TO pi;"

# Run table.SQL if it exists
if [ -f "$PROJECT_DIR/table.SQL" ]; then
  sudo -u postgres psql -d postgres -f "$PROJECT_DIR/table.SQL"
  echo "Tables created from table.SQL"
else
  echo "Warning: table.SQL not found at $PROJECT_DIR/table.SQL"
fi

# Grant privileges on all tables
sudo -u postgres psql -d postgres -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO pi;"
sudo -u postgres psql -d postgres -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO pi;"

echo "=== Enabling pigpiod service ==="
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

echo "=== Setting up Python virtual environment ==="
cd "$PROJECT_DIR"
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install \
  pyrf24 \
  psycopg2-binary \
  colorama \
  termcolor \
  fastapi \
  uvicorn \
  httpx \
  python-dotenv

deactivate

echo "=== Building web frontend ==="
cd "$PROJECT_DIR/web"
npm install
npm run build

echo "=== Setting up nginx ==="
sudo tee /etc/nginx/sites-available/ac-dashboard > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    root $PROJECT_DIR/web/dist;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /ac/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /analytics/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /weather/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/ac-dashboard /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

echo "=== Setting up systemd services ==="

# API server service
sudo tee /etc/systemd/system/ac-api.service > /dev/null <<EOF
[Unit]
Description=AC Dashboard API Server
After=network.target postgresql.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PYTHONPATH=."
ExecStart=$PROJECT_DIR/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Mesh controller service
sudo tee /etc/systemd/system/ac-controller.service > /dev/null <<EOF
[Unit]
Description=AC Mesh Controller
After=network.target postgresql.service pigpiod.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python controller.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ac-api ac-controller
sudo systemctl enable nginx

echo "=== Creating API .env file ==="
if [ ! -f "$PROJECT_DIR/api/.env" ]; then
  cp "$PROJECT_DIR/api/.env.example" "$PROJECT_DIR/api/.env"
  echo "Created api/.env from .env.example"
  echo "IMPORTANT: Edit $PROJECT_DIR/api/.env with your settings!"
fi

echo "=== Setting permissions ==="
chmod 755 "$HOME"
chmod -R 755 "$PROJECT_DIR"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit $PROJECT_DIR/api/.env with your configuration"
echo "  2. Reboot: sudo reboot"
echo ""
echo "After reboot, services will start automatically:"
echo "  - ac-controller: Mesh network controller"
echo "  - ac-api: Web dashboard API"
echo "  - nginx: Web server"
echo ""
echo "View logs:"
echo "  journalctl -u ac-controller -f"
echo "  journalctl -u ac-api -f"
echo ""
echo "Manual control:"
echo "  sudo systemctl start|stop|restart ac-controller"
echo "  sudo systemctl start|stop|restart ac-api"
echo ""
echo "Web dashboard: http://$(hostname)/"
