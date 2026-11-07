#!/bin/bash
# AVON AI - Raspberry Pi 3 Kiosk Launcher
# Optimized for 1GB RAM BCM2837 architecture

TARGET_URL="${1:-http://raspberrypi.local:5173}"

echo "=========================================================="
echo " Starting AVON AI Operator Kiosk Terminal"
echo " Target HMI: $TARGET_URL"
echo "=========================================================="

# 1. Disable screensaver, screen blanking, and energy-saving modes
xset s noblank || true
xset s off || true
xset -dpms || true

# 2. Hide mouse pointer when inactive
if command -v unclutter &> /dev/null; then
    unclutter -idle 1.0 -root &
fi

# 3. Clean up any previous Chromium crashed session flags
PREFS_FILE="$HOME/.config/chromium/Default/Preferences"
if [ -f "$PREFS_FILE" ]; then
    sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' "$PREFS_FILE" || true
    sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' "$PREFS_FILE" || true
fi

# 4. Wait for network / host availability
echo "Checking connection to $TARGET_URL..."
for i in {1..15}; do
    if curl -s --head --request GET "$TARGET_URL" | grep "200 OK\|304 Not Modified" > /dev/null; then
        echo "AVON AI HMI is online."
        break
    fi
    echo "Waiting for HMI server ($i/15)..."
    sleep 2
done

# 5. Launch Chromium in hardware-optimized kiosk mode
# Flags tuned specifically for Raspberry Pi 3 (1GB RAM):
# - Disable dev-shm-usage prevents shared memory exhaustion
# - Disk cache in /tmp reduces SD card wear and latency
# - Disabled background features keep RAM usage under 350MB
exec chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --check-for-update-interval=31536000 \
    --disable-features=Translate,OptimizationHints \
    --no-first-run \
    --fast \
    --fast-start \
    --disable-dev-shm-usage \
    --disk-cache-dir=/tmp/chromium-cache \
    --disk-cache-size=33554432 \
    --autoplay-policy=no-user-gesture-required \
    "$TARGET_URL"
