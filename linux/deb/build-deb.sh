#!/usr/bin/env bash
# Build a seestar-alp .deb package.
#
# Run from anywhere — the script locates the repo root automatically.
#
# Usage:
#   ./linux/deb/build-deb.sh [version]
#   Version defaults to the value in pyproject.toml.
#
# Prerequisites (on the build host):
#   dpkg-deb, git
#
# The resulting .deb installs the application to /opt/seestar_alp and manages
# it via a systemd service (seestar).  Python dependencies are resolved at
# install time using uv.  Optional INDI support can be enabled post-install
# by running linux/deb/enable-indi.sh.

set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [VERSION]

Build a seestar-alp .deb package.

Arguments:
  VERSION       Package version (e.g. 1.2.3 or v1.2.3).
                Defaults to the output of git describe, falling back to
                the version in pyproject.toml.

Options:
  -h, --help    Show this help message and exit.

Environment:
  ARCH          Target Debian architecture (amd64, arm64, armhf).
                Defaults to the host architecture.

Examples:
  ./linux/deb/build-deb.sh                  # auto-version from git
  ./linux/deb/build-deb.sh 1.2.3            # explicit version
  ARCH=armhf ./linux/deb/build-deb.sh       # cross-build for Raspberry Pi (32 bit)
EOF
}

for arg in "$@"; do
    case "$arg" in
        -h|--help) usage; exit 0 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Version
#
# APP_VERSION  — written to device/version.txt; what the UI displays.
#                Matches git describe output exactly (e.g. v1.2.3 or v1.2.3-4-gabcdef).
# DEB_VERSION  — used in the .deb control file; must satisfy dpkg version rules.
#                Leading 'v' stripped; git distance/hash encoded with '+' separator
#                (e.g. 1.2.3 or 1.2.3+4.gabcdef).
# ---------------------------------------------------------------------------
if [ "${1:-}" != "" ]; then
    # Explicit version supplied — use it for both
    APP_VERSION="${1}"
    DEB_VERSION="${APP_VERSION#v}"   # strip leading 'v' if present
else
    # Use the same git describe flags as device/version.py so the deb version
    # and the in-app version are always identical.
    GIT_DESCRIBE=$(git describe --tags --always \
        --exclude '*[0-9]-g*' --match 'v*' 2>/dev/null || true)

    if [ -n "$GIT_DESCRIBE" ]; then
        APP_VERSION="$GIT_DESCRIBE"
        # Convert v1.2.3-4-gabcdef  →  1.2.3+4.gabcdef  (dpkg-safe)
        DEB_VERSION=$(echo "$GIT_DESCRIBE" \
            | sed 's/^v//' \
            | sed 's/-\([0-9]*\)-g\(.*\)/+\1.\2/')
    else
        # No git tags — fall back to pyproject.toml
        DEB_VERSION=$(python3 -c "
import re
with open('pyproject.toml') as f:
    content = f.read()
m = re.search(r'^version\s*=\s*\"([^\"]+)\"', content, re.MULTILINE)
print(m.group(1) if m else '0.0.0')
")
        APP_VERSION="$DEB_VERSION"
    fi
fi

PKG_NAME="seestar-alp"

# Map the host kernel architecture to the Debian architecture name.
# Pass ARCH=<value> on the command line to cross-build (e.g. ARCH=armhf).
case "${ARCH:-$(uname -m)}" in
    aarch64|arm64) ARCH="arm64"  ;;
    armv7l|armhf)  ARCH="armhf"  ;;
    x86_64)        ARCH="amd64"  ;;
    *)             ARCH=$(uname -m) ;;
esac
DEB_FILE="${REPO_ROOT}/${PKG_NAME}_${DEB_VERSION}_${ARCH}.deb"

echo "Building ${PKG_NAME} ${DEB_VERSION} (${ARCH})  [app version: ${APP_VERSION}]..."

# ---------------------------------------------------------------------------
# Staging tree
# ---------------------------------------------------------------------------
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

APP="$STAGE/opt/seestar_alp"
SYSTEMD="$STAGE/lib/systemd/system"
SYSCTL="$STAGE/etc/sysctl.d"
ETCSEESTAR="$STAGE/etc/seestar"
DEBIAN="$STAGE/DEBIAN"

mkdir -p "$APP" "$SYSTEMD" "$SYSCTL" "$ETCSEESTAR" "$DEBIAN"

# ---------------------------------------------------------------------------
# Copy application source
# Use git archive so only tracked, committed files are included — no local
# artifacts, untracked files, or developer debris can sneak into the package.
# Warn if there are uncommitted changes to tracked files that would be missed.
# ---------------------------------------------------------------------------
if ! git diff --quiet HEAD; then
    echo "WARNING: uncommitted changes to tracked files will NOT be included in the package." >&2
fi
git archive HEAD | tar -x -C "$APP"

# Remove any config.toml that may be present — the postinst generates it
# from config.toml.example so that upgrades don't overwrite user edits.
rm -f "$APP/device/config.toml"

# Replace the pyenv virtualenv name in .python-version with a plain version
# number that uv understands (e.g. "ssc-3.13.5" -> "3.13").
if [ -f "$APP/.python-version" ]; then
    sed 's/^[^0-9]*//' "$APP/.python-version" \
        | grep -oE '^[0-9]+\.[0-9]+' > "$APP/.python-version.tmp"
    mv "$APP/.python-version.tmp" "$APP/.python-version"
fi

# Write version.txt so the app displays the correct version without needing
# git at runtime (device/version.py checks for this file first).
echo "$APP_VERSION" > "$APP/device/version.txt"

# ---------------------------------------------------------------------------
# Bundle uv binary for the target architecture
# Downloading at install time requires working SSL and network access.
# Bundling it avoids both problems and makes offline installs possible.
# ---------------------------------------------------------------------------
echo "Bundling uv..."
case "$ARCH" in
    amd64) UV_ARCH="x86_64-unknown-linux-gnu" ;;
    arm64) UV_ARCH="aarch64-unknown-linux-gnu" ;;
    armhf) UV_ARCH="armv7-unknown-linux-gnueabihf" ;;
    *)     echo "No uv binary known for arch: $ARCH"; exit 1 ;;
esac
mkdir -p "$APP/.local/bin"
curl -LsSf "https://github.com/astral-sh/uv/releases/latest/download/uv-${UV_ARCH}.tar.gz" \
    | tar -xz --strip-components=1 -C "$APP/.local/bin" \
        "uv-${UV_ARCH}/uv" "uv-${UV_ARCH}/uvx"

chmod +x "$APP/linux/deb/enable-indi.sh"

# ---------------------------------------------------------------------------
# Systemd service units
# ---------------------------------------------------------------------------
cp "$SCRIPT_DIR/seestar.service" "$SYSTEMD/seestar.service"
cp "$SCRIPT_DIR/INDI.service"    "$SYSTEMD/INDI.service"

# ---------------------------------------------------------------------------
# /etc/seestar/seestar.env — ship as a conffile so dpkg preserves local edits
# ---------------------------------------------------------------------------
cp "$SCRIPT_DIR/seestar.env" "$ETCSEESTAR/seestar.env"

# Register conffiles so dpkg handles upgrade conflicts gracefully
cat > "$DEBIAN/conffiles" <<EOF
/etc/seestar/seestar.env
EOF

# ---------------------------------------------------------------------------
# sysctl: disable IPv6 (mirrors what setup.sh does)
# ---------------------------------------------------------------------------
echo "net.ipv6.conf.all.disable_ipv6 = 1" > "$SYSCTL/98-ssc.conf"

# ---------------------------------------------------------------------------
# DEBIAN maintainer scripts
# ---------------------------------------------------------------------------
for script in postinst prerm postrm; do
    cp "$SCRIPT_DIR/$script" "$DEBIAN/$script"
    chmod 755 "$DEBIAN/$script"
done

# ---------------------------------------------------------------------------
# DEBIAN/control
# ---------------------------------------------------------------------------
INSTALLED_SIZE=$(du -sk "$STAGE" | cut -f1)

cat > "$DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${DEB_VERSION}
Section: science
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${INSTALLED_SIZE}
Depends: libxml2-dev, libxslt1-dev
Recommends: avahi-daemon
Maintainer: smart-underworld <https://github.com/smart-underworld/seestar_alp>
Homepage: https://github.com/smart-underworld/seestar_alp
Description: Seestar ALP telescope controller
 ALPACA bridge and web interface for ZWO Seestar smart telescopes.
 Runs as a systemd service accessible from any device on the local network.
 Python dependencies are managed with uv and installed into an isolated
 virtual environment at install time.
 .
 Optional INDI support can be enabled after install by running:
   sudo /opt/seestar_alp/linux/deb/enable-indi.sh
EOF

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
dpkg-deb --build --root-owner-group "$STAGE" "$DEB_FILE"
echo "Built: $DEB_FILE ($(du -h "$DEB_FILE" | cut -f1))"
echo ""
echo "Install with:  sudo apt install ./$(basename "$DEB_FILE")"
echo "Remove with:   sudo apt remove seestar-alp"
echo "Purge with:    sudo apt purge seestar-alp   (removes config + venv)"
