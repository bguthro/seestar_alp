# Building seestar-alp .deb packages

## Overview

`build-deb.sh` builds a `.deb` for any of the three supported Debian
architectures: `amd64`, `arm64` (Raspberry Pi 64-bit), and `armhf`
(Raspberry Pi 32-bit).

When Docker Buildx is available the Python venv is **pre-built** for the
target architecture inside a container.  This makes cross-compilation
possible (e.g. building an `arm64` or `armhf` package on an `x86_64`
machine) and removes the need to download and install Python dependencies
on the target at install time.

If Docker Buildx is not available the build falls back to bundling the
`uv` binary; the venv is then created the first time the package is
installed on the target.

---

## Installing Docker Buildx

### Linux

Docker Buildx is included with **Docker Engine ≥ 23** and
**Docker Desktop ≥ 4**.

#### Raspberry Pi OS / Debian

Use Docker's official Debian repository (Raspberry Pi OS is based on Debian bookworm):

```bash
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/debian bookworm stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
sudo usermod -aG docker "$USER"   # re-login after this
```

Buildx is bundled with `docker.io` on trixie and newer.  If `docker buildx version`
returns "command not found" after re-login, install the plugin binary manually:

```bash
# Pick the right suffix for your CPU:
#   aarch64  →  linux-arm64
#   armv7l   →  linux-arm-v7
#   x86_64   →  linux-amd64
uname -m   # check your CPU

BUILDX_ARCH=linux-arm64   # adjust as above
BUILDX_VER=$(curl -fsSL https://api.github.com/repos/docker/buildx/releases/latest \
    | grep '"tag_name"' | cut -d'"' -f4)
mkdir -p ~/.docker/cli-plugins
curl -fsSL "https://github.com/docker/buildx/releases/download/${BUILDX_VER}/buildx-${BUILDX_VER}.${BUILDX_ARCH}" \
    -o ~/.docker/cli-plugins/docker-buildx
chmod +x ~/.docker/cli-plugins/docker-buildx
docker buildx version
```

#### Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin
sudo usermod -aG docker "$USER"
```

**Verify:**

```bash
docker buildx version
# buildx v0.x.y  linux/amd64
```

---

### macOS

Install **Docker Desktop for Mac** from <https://www.docker.com/products/docker-desktop>.
Buildx is included and enabled by default.

**Verify:**

```bash
docker buildx version
```

---

### Windows

Install **Docker Desktop for Windows** from <https://www.docker.com/products/docker-desktop>.
Buildx is included and enabled by default.

```powershell
docker buildx version
```

---

## Enabling QEMU for cross-architecture builds

To build `arm64` or `armhf` packages on an `x86_64` host you need QEMU
user-space emulation registered with the kernel.

### Linux (one-time setup)

```bash
sudo apt-get install -y qemu-user-static
```

This installs QEMU and registers the binfmt handlers persistently across reboots.

**Verify:**

```bash
ls /proc/sys/fs/binfmt_misc/ | grep -E 'arm|aarch'
```

> **Raspberry Pi 5 note:** the Pi 5 kernel uses 16 KB memory pages, but standard
> Docker arm64 images are compiled for 4 KB pages.  Any binary inside a standard
> Docker container will crash with a `libc.so.6` page-alignment error.  `build-deb.sh`
> detects this automatically and falls back to bundling the `uv` binary instead.
> Docker buildx cross-compilation works fine on x86_64 CI runners.

### macOS / Windows (Docker Desktop)

QEMU emulation is built into Docker Desktop — no extra steps needed.

---

## Building packages

```bash
# amd64 (native on a standard Linux PC)
./linux/deb/build-deb.sh

# arm64 (Raspberry Pi 64-bit) — cross-compiled on x86_64 via Docker+QEMU
ARCH=arm64 ./linux/deb/build-deb.sh

# armhf (Raspberry Pi 32-bit)
ARCH=armhf ./linux/deb/build-deb.sh

# Explicit version
ARCH=arm64 ./linux/deb/build-deb.sh 1.2.3
```

The resulting `.deb` files appear in the repo root.

---

## Optional INDI package

```bash
# Build the companion INDI package (architecture-independent)
./linux/deb/build-indi-deb.sh
```

Install order:

```bash
sudo apt install ./seestar-alp_<version>_arm64.deb
sudo apt install ./seestar-alp-indi_<version>_all.deb
```
