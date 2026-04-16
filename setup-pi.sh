#!/bin/bash
# PlanePortal Pi — Raspberry Pi setup script
# Run this once on a fresh Raspberry Pi OS installation.
#
# Usage:  chmod +x setup-pi.sh && ./setup-pi.sh

set -e

echo "╔══════════════════════════════════════╗"
echo "║     PlanePortal Pi Setup Script      ║"
echo "╚══════════════════════════════════════╝"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── 1. System packages ──────────────────────────────────
echo "▶ Installing system dependencies..."
sudo apt-get update -qq

# Bookworm+ ships "chromium"; older Pi OS uses "chromium-browser"
if apt-cache show chromium >/dev/null 2>&1; then
    CHROMIUM_PKG=chromium
else
    CHROMIUM_PKG=chromium-browser
fi
sudo apt-get install -y -qq python3 python3-pip python3-venv "$CHROMIUM_PKG" unclutter

# ── 2. Python virtual environment ────────────────────────
echo "▶ Creating Python virtual environment..."
cd "$SCRIPT_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# ── 3. .env file ─────────────────────────────────────────
if [ ! -f .env ]; then
    echo "▶ Creating .env from template..."
    cat > .env <<'ENVEOF'
# PlanePortal Pi Configuration

# Required: your watch-point coordinates (decimal degrees)
PLANEPORTAL_HOME_LATITUDE=0.0
PLANEPORTAL_HOME_LONGITUDE=0.0

# OpenSky Network API credentials (optional — works without, but rate-limited)
OPENSKY_CLIENT_ID=
OPENSKY_CLIENT_SECRET=

# Optional settings with sensible defaults
PLANEPORTAL_RADIUS_MILES=10
PLANEPORTAL_REFRESH_SECONDS=120
PLANEPORTAL_RECENT_WINDOW_MINUTES=10
PLANEPORTAL_ENRICHMENT_LIMIT=4
PLANEPORTAL_ADSB_CACHE_SECONDS=1800
PLANEPORTAL_DEBUG=0

# Server port (default 5000)
PORT=5000
ENVEOF
    echo ""
    echo "  ⚠  IMPORTANT: Edit .env with your coordinates and OpenSky credentials."
    echo "     nano $SCRIPT_DIR/.env"
    echo ""
fi

# ── 4. systemd service for the Flask server ──────────────
echo "▶ Installing systemd service..."
sudo tee /etc/systemd/system/planeportal.service > /dev/null <<EOF
[Unit]
Description=PlanePortal Pi Flight Tracker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/venv/bin/python run.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable planeportal.service

# ── 5. Kiosk mode autostart (Chromium fullscreen) ────────
echo "▶ Setting up kiosk autostart..."
mkdir -p "$HOME/.config/autostart"

# Use whichever chromium binary is available
CHROMIUM_BIN="$(command -v chromium 2>/dev/null || command -v chromium-browser 2>/dev/null)"
cat > "$HOME/.config/autostart/planeportal-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PlanePortal Kiosk
Comment=Open PlanePortal dashboard in fullscreen Chromium
Exec=bash -c 'sleep 8 && unclutter -idle 0.5 -root & $CHROMIUM_BIN --noerrdialogs --disable-infobars --kiosk --incognito http://localhost:5000'
X-GNOME-Autostart-enabled=true
EOF

echo ""
echo "╔══════════════════════════════════════╗"
echo "║          Setup complete!             ║"
echo "╠══════════════════════════════════════╣"
echo "║                                      ║"
echo "║  1. Edit your .env file:             ║"
echo "║     nano $SCRIPT_DIR/.env            ║"
echo "║                                      ║"
echo "║  2. Start the server:                ║"
echo "║     sudo systemctl start planeportal ║"
echo "║                                      ║"
echo "║  3. Open the dashboard:              ║"
echo "║     http://localhost:5000            ║"
echo "║                                      ║"
echo "║  On next reboot, the dashboard will  ║"
echo "║  launch automatically in fullscreen. ║"
echo "║                                      ║"
echo "╚══════════════════════════════════════╝"
