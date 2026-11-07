#!/usr/bin/env bash
# ==============================================================================
# AVON AI - Automated Raspberry Pi Setup Script
# Supports:
#   - Raspberry Pi 5: Edge Gateway, GPIO Hardware Controls, Serial Dispatcher
#   - Raspberry Pi 3: Operator Kiosk Display (1GB RAM tuned)
# ==============================================================================

set -e

ROLE="gateway"
if [[ "$1" == "--role" && -n "$2" ]]; then
    ROLE="$2"
fi

echo "=========================================================="
echo " Setting up AVON AI Hardware Node"
echo " Detected Architecture: $(uname -m)"
echo " Selected Role: $ROLE"
echo "=========================================================="

# Check for root/sudo
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root or with sudo: sudo bash setup_pi.sh --role $ROLE"
    exit 1
fi

REAL_USER="${SUDO_USER:-pi}"
USER_HOME=$(eval echo "~$REAL_USER")

echo "Updating system packages..."
apt-get update -y

if [[ "$ROLE" == "gateway" ]]; then
    echo "Configuring Raspberry Pi 5 (Edge Gateway & Controls)..."
    apt-get install -y python3 python3-pip python3-venv git

    # Add user to dialout and gpio groups for non-root serial & GPIO access
    usermod -a -G dialout,gpio "$REAL_USER" || true

    echo "Installing Python hardware dependencies..."
    # On Debian Bookworm (Pi 5), pip requires --break-system-packages or venv
    pip3 install -r requirements-hw.txt --break-system-packages || pip3 install -r requirements-hw.txt

    # Install systemd service for gateway
    SERVICE_SRC="gateway/systemd/avon-gateway.service"
    if [ -f "$SERVICE_SRC" ]; then
        cp "$SERVICE_SRC" /etc/systemd/system/avon-gateway.service
        sed -i "s|/home/pi|$USER_HOME|g" /etc/systemd/system/avon-gateway.service
        sed -i "s|User=pi|User=$REAL_USER|g" /etc/systemd/system/avon-gateway.service
        systemctl daemon-reload
        systemctl enable avon-gateway.service
        echo "Systemd service 'avon-gateway.service' installed and enabled."
    fi

    echo ""
    echo "Raspberry Pi 5 Gateway Setup Complete!"
    echo "To start the gateway manually:"
    echo "  python3 gateway/bridge.py --config gateway/config.json"
    echo "To start the GPIO control deck:"
    echo "  python3 gateway/gpio_controller.py --config gateway/config.json"

elif [[ "$ROLE" == "kiosk" ]]; then
    echo "Configuring Raspberry Pi 3 (Operator Kiosk Terminal)..."
    apt-get install -y chromium-browser unclutter xdotool sed curl

    # Install systemd service for kiosk
    SERVICE_SRC="kiosk/systemd/avon-kiosk.service"
    if [ -f "$SERVICE_SRC" ]; then
        cp "$SERVICE_SRC" /etc/systemd/system/avon-kiosk.service
        sed -i "s|/home/pi|$USER_HOME|g" /etc/systemd/system/avon-kiosk.service
        sed -i "s|User=pi|User=$REAL_USER|g" /etc/systemd/system/avon-kiosk.service
        systemctl daemon-reload
        systemctl enable avon-kiosk.service
        echo "Systemd service 'avon-kiosk.service' installed and enabled."
    fi

    chmod +x kiosk/kiosk.sh

    echo ""
    echo "Raspberry Pi 3 Kiosk Setup Complete!"
    echo "To launch the kiosk manually:"
    echo "  bash kiosk/kiosk.sh http://<SERVER_OR_PI5_IP>:5173"

else
    echo "Unknown role '$ROLE'. Valid options are: --role gateway | --role kiosk"
    exit 1
fi
