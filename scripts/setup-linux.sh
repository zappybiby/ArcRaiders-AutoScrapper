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

uv_is_supported() {
  local version
  version="$(uv --version)" || return 1
  [[ "$version" =~ ^uv[[:space:]]+([0-9]+)\.([0-9]+)\.([0-9]+)([[:space:]]|$) ]] &&
    (( BASH_REMATCH[1] > 0 || BASH_REMATCH[2] > 9 || (BASH_REMATCH[2] == 9 && BASH_REMATCH[3] >= 8) ))
}

# Run from repo root
if [[ ! -f pyproject.toml || ! scripts/setup-linux.sh -ef "${BASH_SOURCE[0]}" ]]; then
  echo "ERROR: Run this script from its AutoScrapper repo root."
  exit 1
fi

if [[ -n "${WSL_INTEROP-}" || -n "${WSL_DISTRO_NAME-}" ]] || grep -qi microsoft /proc/version 2>/dev/null; then
  echo "ERROR: WSL is not supported. Run this on a native Linux install."
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

# evdev uses Linux input headers. PyMonCtl calls xrandr during startup.
print_step "Step 1: Install system prerequisites"
if command -v apt-get >/dev/null 2>&1; then
  echo "Command to run:"
  echo "  $SUDO apt-get update"
  confirm_or_abort "Run apt-get update?"
  $SUDO apt-get update

  # build-essential pulls in linux-libc-dev. Requesting it directly can upgrade the Pop!_OS kernel.
  install_cmd=(apt-get install -y build-essential pkg-config
    libtesseract-dev libleptonica-dev curl ca-certificates procps x11-xserver-utils
    libxcb-randr0 libxcb-render0 libxcb-shm0 libxcb-xfixes0)
elif command -v pacman >/dev/null 2>&1; then
  install_cmd=(pacman -S --needed base-devel linux-api-headers tesseract
    xorg-xrandr xorg-xset)
else
  echo "ERROR: This installer requires apt-get or pacman."
  exit 1
fi

echo "Command to run:"
echo "  $SUDO ${install_cmd[*]}"
confirm_or_abort "Install these packages?"
$SUDO "${install_cmd[@]}"

# 2) Install uv (if missing)
if ! command -v uv >/dev/null 2>&1 || ! uv_is_supported; then
  export PATH="$HOME/.local/bin:$PATH"
fi
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

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is still not on PATH. Add ~/.local/bin to PATH and re-run."
  exit 1
fi

if ! uv_is_supported; then
  echo "ERROR: uv 0.9.8 or newer is required. Run uv self update (or update through your package manager), then re-run setup."
  exit 1
fi

# 3) Install the supported Python version
PYTHON_VERSION="3.14"
PYTHON_REQUEST="cpython-${PYTHON_VERSION}"

print_step "Step 3: Install and pin Python ${PYTHON_VERSION} (uv)"
echo "Command to run:"
echo "  uv python install ${PYTHON_REQUEST}"
confirm_or_abort "Run: uv python install ${PYTHON_REQUEST}?"
uv python install "$PYTHON_REQUEST"

echo "Command to run:"
echo "  uv python pin \"${PYTHON_VERSION}\""
confirm_or_abort "Run: uv python pin \"${PYTHON_VERSION}\"?"
uv python pin "$PYTHON_VERSION"

# 4) Install project dependencies with uv
print_step "Step 4: Install project dependencies (uv sync)"
echo "Command to run:"
echo "  uv sync --python \"${PYTHON_REQUEST}+gil\""
confirm_or_abort "Proceed with Step 4?"
uv sync --python "${PYTHON_REQUEST}+gil"

if [[ "${XDG_SESSION_TYPE:-}" == "wayland" ]]; then
  echo "For reliable game window detection, sign in to an X11 (Xorg) session before scanning."
fi

echo "Setup finished. Run:"
printf '  %q run autoscrapper\n' "$(command -v uv)"
