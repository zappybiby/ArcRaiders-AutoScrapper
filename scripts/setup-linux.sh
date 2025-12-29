#!/usr/bin/env bash
set -euo pipefail

# Run from repo root
if [[ ! -f "pyproject.toml" ]]; then
  echo "ERROR: Run this from the repo root (pyproject.toml not found)."
  exit 1
fi

if [[ -n "${WSL_INTEROP-}" || -n "${WSL_DISTRO_NAME-}" ]] || grep -qi microsoft /proc/version 2>/dev/null; then
  echo "ERROR: WSL is not supported. Run this on a native Linux install (X11/XWayland)."
  exit 1
fi

SUDO=""
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    echo "ERROR: This script needs root privileges (sudo not found)."
    exit 1
  fi
fi

# 1) System prerequisites
# - build-essential/linux-headers: commonly needed when a dependency must compile (e.g., evdev via pynput)
# - tesseract/leptonica/pkg-config: required to build/link tesserocr on Linux
$SUDO apt-get update
$SUDO apt-get install -y \
  build-essential \
  linux-headers-$(uname -r) \
  pkg-config \
  tesseract-ocr \
  libtesseract-dev \
  libleptonica-dev

# 2) Install uv (if missing)
if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | sh
  else
    echo "ERROR: Need curl or wget to install uv."
    exit 1
  fi
fi

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is still not on PATH. Add ~/.local/bin to PATH and re-run."
  exit 1
fi

# 3) We recommend Python 3.13 but support Python 3.10 to 3.13
PYTHON_VERSION="${AUTOSCRAPPER_PYTHON_VERSION:-3.13}"
case "$PYTHON_VERSION" in
  3.10|3.11|3.12|3.13) ;;
  *)
    echo "ERROR: Unsupported Python version: ${PYTHON_VERSION} (supported: 3.10–3.13; 3.14 is not supported)."
    exit 1
    ;;
esac

uv python install "$PYTHON_VERSION"
uv python pin "$PYTHON_VERSION"

# 4) Install project dependencies with uv
uv sync

echo "Setup finished. Run:"
echo "  uv run autoscrapper"
