#!/usr/bin/env bash
# enable-indi.sh — install INDI support for seestar-alp and enable the service.
# Run as root after installing the seestar-alp package.
#
# Usage: sudo /opt/seestar_alp/linux/deb/enable-indi.sh

set -euo pipefail

APP_DIR=/opt/seestar_alp
SEESTAR_USER=seestar

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: this script must be run as root." >&2
    exit 1
fi

# Resolve uv binary
if command -v uv >/dev/null 2>&1; then
    UV=uv
elif [ -x "$APP_DIR/.local/bin/uv" ]; then
    UV="$APP_DIR/.local/bin/uv"
else
    echo "Error: uv not found. Please re-install the seestar-alp package." >&2
    exit 1
fi

echo "Installing system packages..."
apt-get install -y git indi-bin

echo "Installing INDI Python dependencies..."
HOME="$APP_DIR" su -s /bin/sh "$SEESTAR_USER" -c "
    '$UV' pip install --python '$APP_DIR/.venv/bin/python' \
        -r '$APP_DIR/requirements-indi.txt'
"

echo "Enabling INDI service..."
systemctl enable INDI.service
systemctl start INDI.service

echo ""
echo "INDI support enabled."
echo "Check status with: systemctl status INDI"
echo "View logs with:    journalctl -u INDI"
