#!/usr/bin/env bash
set -euo pipefail

abort() {
  echo "Aborted."
  exit 1
}

confirm() {
  local prompt="$1"
  local reply=""

  if ! read -r -p "${prompt} [Y/n] " reply; then
    echo
    return 1
  fi

  case "${reply,,}" in
    "") return 0 ;;
    y|yes) return 0 ;;
    *) return 1 ;;
  esac
}

confirm_or_abort() {
  local prompt="$1"
  if ! confirm "$prompt"; then
    abort
  fi
}

print_step() {
  local title="$1"
  echo
  echo "==> ${title}"
}

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
KERNEL_HEADERS_PKG="linux-headers-$(uname -r)"
print_step "Step 1: Install system prerequisites (apt)"
echo "Command to run:"
echo "  $SUDO apt-get update"
confirm_or_abort "Run apt-get update?"
$SUDO apt-get update

echo "Command to run:"
echo "  $SUDO apt-get install -y build-essential ${KERNEL_HEADERS_PKG} pkg-config tesseract-ocr libtesseract-dev libleptonica-dev"
confirm_or_abort "Run apt-get install?"
$SUDO apt-get install -y \
  build-essential \
  "$KERNEL_HEADERS_PKG" \
  pkg-config \
  tesseract-ocr \
  libtesseract-dev \
  libleptonica-dev

# 2) Install uv (if missing)
if ! command -v uv >/dev/null 2>&1; then
  print_step "Step 2: Install uv (required)"
  UV_INSTALL_URL="https://astral.sh/uv/install.sh"

  if command -v curl >/dev/null 2>&1; then
    echo "This will download and run the uv installer from:"
    echo "  ${UV_INSTALL_URL}"
    echo "Command to run:"
    echo "  curl -LsSf \"${UV_INSTALL_URL}\" | sh"
    confirm_or_abort "Proceed with Step 2?"
    curl -LsSf "$UV_INSTALL_URL" | sh
  elif command -v wget >/dev/null 2>&1; then
    echo "This will download and run the uv installer from:"
    echo "  ${UV_INSTALL_URL}"
    echo "Command to run:"
    echo "  wget -qO- \"${UV_INSTALL_URL}\" | sh"
    confirm_or_abort "Proceed with Step 2?"
    wget -qO- "$UV_INSTALL_URL" | sh
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

print_step "Step 3: Install and pin Python ${PYTHON_VERSION} (uv)"
echo "Command to run:"
echo "  uv python install \"${PYTHON_VERSION}\""
confirm_or_abort "Run: uv python install \"${PYTHON_VERSION}\"?"
uv python install "$PYTHON_VERSION"

echo "Command to run:"
echo "  uv python pin \"${PYTHON_VERSION}\""
confirm_or_abort "Run: uv python pin \"${PYTHON_VERSION}\"?"
uv python pin "$PYTHON_VERSION"

# 4) Install project dependencies with uv
print_step "Step 4: Install project dependencies (uv sync)"
echo "Command to run:"
echo "  uv sync"
confirm_or_abort "Proceed with Step 4?"
uv sync

echo "Setup finished. Run:"
echo "  uv run autoscrapper"
