# Arc Raiders Inventory Auto Scrapper

Automates Arc Raiders inventory actions (Sell/Recycle) using screen capture + OCR + simulated mouse input.
It never hooks the game process, memory, or network.

## Support
- Windows 10/11: supported
- Linux: experimental/untested (native X11/XWayland only)
- WSL is not supported

Python 3.10–3.13 is supported (3.13 recommended). Python 3.14 is not supported.

## Setup
This repo uses `uv` to manage Python + dependencies.

Key dependencies:
- OCR: `tesserocr` (required)
  - Windows: installed automatically via the matching prebuilt wheel (handled by `uv`)
  - Linux: builds against system `tesseract`/`leptonica` (installed by the Linux setup script)
- Input injection:
  - Windows: `pydirectinput-rgx`
  - Linux: `pynput`

### Clone the repo
From a terminal (PowerShell/CMD on Windows, bash on Linux):
- `git clone https://github.com/zappybiby/ArcRaiders-AutoScrapper.git`
- `cd ArcRaiders-AutoScrapper`

### Windows 10/11 (64-bit)
From the repo root (PowerShell or CMD):
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup-windows.ps1`
- Optional (use a different supported Python): `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup-windows.ps1 -PythonVersion 3.12`

### Linux (experimental/untested)
Ubuntu/Debian (apt-get) on a native X11/XWayland desktop only. WSL is not supported.

From the repo root:
- `bash scripts/setup-linux.sh`
- Optional (use a different supported Python): `AUTOSCRAPPER_PYTHON_VERSION=3.12 bash scripts/setup-linux.sh`

## Usage

Common commands:
- `uv run autoscrapper` (interactive menu)
- `uv run autoscrapper scan`
- `uv run autoscrapper rules`
- `uv run autoscrapper config`
- `uv run autoscrapper scan --help`

Before you scan:
- Open your inventory (ideally “Crafting Materials”), scroll to the top, and keep the game window fully on one monitor.
- Press Escape to abort (may need multiple presses).

Linux notes (experimental):
- Requires a native desktop session under X11/XWayland (Proton is fine). Pure Wayland sessions may not support window detection/input injection.
- Default target window title is `Arc Raiders`. Override with `AUTOSCRAPPER_TARGET_APP` if needed.

## CLI options (scan)
Run `uv run autoscrapper scan --help` for the full list.
- `--pages INT` override auto-detected 6x4 page count to scan.
- `--scroll-clicks INT` initial scroll clicks between grids (alternates with +1 on the next page).
- `--dry-run` log planned actions without clicking Sell/Recycle.
- `--profile` enable per-item timing logs (capture, OCR, total).
- `--no-profile` disable per-item timing logs (overrides saved scan configuration).
- `--debug` / `--debug-ocr` save OCR debug images to `./ocr_debug`.
- `--no-debug` disable OCR debug images (overrides saved scan configuration).
