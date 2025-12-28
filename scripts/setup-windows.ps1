param(
  [ValidateSet("3.10", "3.11", "3.12", "3.13")]
  [string]$PythonVersion = "3.13"
)

$ErrorActionPreference = "Stop"

# Run from repo root
if (-not (Test-Path -Path "pyproject.toml")) {
  Write-Error "Run this from the repo root (pyproject.toml not found)."
  exit 1
}

# 1) Install uv (if missing)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "Installing uv..."
  irm https://astral.sh/uv/install.ps1 | iex
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Error "uv is still not on PATH. Close/reopen PowerShell, then re-run this script."
  exit 1
}

# 2) We recommend Python 3.13 but support Python 3.10 to 3.13
uv python install $PythonVersion
uv python pin $PythonVersion

# 3) Install project dependencies with uv
uv sync

Write-Host "Setup finished. Run:"
Write-Host "  uv run autoscrapper"
