#!/usr/bin/env bash
# Build the seestar-alp-indi .deb package (optional INDI support).
#
# Run from anywhere — the script locates the repo root automatically.
#
# Usage:
#   ./linux/deb/build-indi-deb.sh [version]
#   Version must match the seestar-alp package it will be installed alongside.
#
# Prerequisites (on the build host):
#   dpkg-deb, git

set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [VERSION]

Build a seestar-alp-indi .deb package (optional INDI support).
The version must match the seestar-alp package it will be installed alongside.

Arguments:
  VERSION       Package version (e.g. 1.2.3 or v1.2.3).
                Defaults to git describe, falling back to pyproject.toml.

Options:
  -h, --help    Show this help message and exit.

Examples:
  ./linux/deb/build-indi-deb.sh              # auto-version from git
  ./linux/deb/build-indi-deb.sh 1.2.3        # explicit version
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
# Version — same logic as build-deb.sh so both packages share a version.
# ---------------------------------------------------------------------------
if [ "${1:-}" != "" ]; then
    APP_VERSION="${1}"
    DEB_VERSION="${APP_VERSION#v}"
else
    GIT_DESCRIBE=$(git describe --tags --always \
        --exclude '*[0-9]-g*' --match 'v*' 2>/dev/null || true)

    if [ -n "$GIT_DESCRIBE" ]; then
        APP_VERSION="$GIT_DESCRIBE"
        DEB_VERSION=$(echo "$GIT_DESCRIBE" \
            | sed 's/^v//' \
            | sed 's/-\([0-9]*\)-g\(.*\)/+\1.\2/')
    else
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

PKG_NAME="seestar-alp-indi"
DEB_FILE="${REPO_ROOT}/${PKG_NAME}_${DEB_VERSION}_all.deb"

echo "Building ${PKG_NAME} ${DEB_VERSION}..."

# ---------------------------------------------------------------------------
# Read Python dependency specs from pyproject.toml — single source of truth.
# ---------------------------------------------------------------------------
PYINDI_REQ=$(python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    config = tomllib.load(f)
src = config['tool']['uv']['sources']['pyindi']
print(f'pyindi @ git+{src[\"git\"]}@{src[\"rev\"]}')
")
TOML_DEP=$(python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    config = tomllib.load(f)
for dep in config['project']['optional-dependencies']['indi']:
    if dep.startswith('toml'):
        print(dep)
        break
")

# ---------------------------------------------------------------------------
# Staging tree
# ---------------------------------------------------------------------------
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

SYSTEMD="$STAGE/lib/systemd/system"
DEBIAN="$STAGE/DEBIAN"

mkdir -p "$SYSTEMD" "$DEBIAN"

# ---------------------------------------------------------------------------
# INDI systemd service unit
# ---------------------------------------------------------------------------
cp "$SCRIPT_DIR/INDI.service" "$SYSTEMD/INDI.service"

# ---------------------------------------------------------------------------
# DEBIAN maintainer scripts
# ---------------------------------------------------------------------------

# postinst — install Python deps into the existing seestar-alp venv, then
# enable and start the INDI service.
# Note: ${PYINDI_REQ} and ${TOML_DEP} are expanded now (build time) so the
# installed package carries the exact pinned versions with no build tools needed
# on the target beyond git (for the git+ URL).
cat > "$DEBIAN/postinst" <<EOF
#!/bin/bash
set -e
APP_DIR=/opt/seestar_alp
SEESTAR_USER=seestar

if command -v uv >/dev/null 2>&1; then
    UV=uv
elif [ -x "\$APP_DIR/.local/bin/uv" ]; then
    UV="\$APP_DIR/.local/bin/uv"
else
    echo "Error: uv not found. Is seestar-alp installed?" >&2
    exit 1
fi

echo "Installing INDI Python dependencies..."
HOME="\$APP_DIR" su -s /bin/sh "\$SEESTAR_USER" -c "
    '\$UV' pip install --python '\$APP_DIR/.venv/bin/python' \\
        '${PYINDI_REQ}' '${TOML_DEP}'
"

systemctl daemon-reload
systemctl enable INDI.service
systemctl start INDI.service

echo ""
echo "INDI service started."
echo "Check status with: systemctl status INDI"
echo "View logs with:    journalctl -u INDI"
EOF

cat > "$DEBIAN/prerm" <<'EOF'
#!/bin/bash
set -e
if [ "$1" = "remove" ] || [ "$1" = "upgrade" ] || [ "$1" = "purge" ]; then
    systemctl stop INDI.service 2>/dev/null || true
    systemctl disable INDI.service 2>/dev/null || true
fi
EOF

cat > "$DEBIAN/postrm" <<'EOF'
#!/bin/bash
set -e
systemctl daemon-reload 2>/dev/null || true
EOF

for script in postinst prerm postrm; do
    chmod 755 "$DEBIAN/$script"
done

# ---------------------------------------------------------------------------
# DEBIAN/control
# Depends on the exact same version of seestar-alp so they are always
# upgraded together.
# ---------------------------------------------------------------------------
INSTALLED_SIZE=$(du -sk "$STAGE" | cut -f1)

cat > "$DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${DEB_VERSION}
Section: science
Priority: optional
Architecture: all
Installed-Size: ${INSTALLED_SIZE}
Depends: seestar-alp (= ${DEB_VERSION}), git, indi-bin
Maintainer: smart-underworld <https://github.com/smart-underworld/seestar_alp>
Homepage: https://github.com/smart-underworld/seestar_alp
Description: INDI support for seestar-alp
 Adds INDI server integration to the seestar-alp telescope controller.
 Installs the INDI systemd service and required Python dependencies
 into the seestar-alp virtual environment.
EOF

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
dpkg-deb --build --root-owner-group "$STAGE" "$DEB_FILE"
echo "Built: $DEB_FILE ($(du -h "$DEB_FILE" | cut -f1))"
echo ""
echo "Install with:  sudo apt install seestar-alp_*.deb ./$(basename "$DEB_FILE")"
echo "Remove with:   sudo apt remove seestar-alp-indi"
