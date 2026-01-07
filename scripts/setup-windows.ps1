param(
  [ValidateSet("3.10", "3.11", "3.12", "3.13")]
  [string]$PythonVersion = "3.13"
)

$ErrorActionPreference = "Stop"

function Confirm-Step {
  param(
    [Parameter(Mandatory)]
    [string]$Title,
    [string[]]$Commands = @()
  )

  Write-Host ""
  Write-Host "==> $Title"

  if ($Commands.Count -gt 0) {
    if ($Commands.Count -eq 1) {
      Write-Host "Command to run:"
      Write-Host "  $($Commands[0])"
    } else {
      Write-Host "Commands to run:"
      foreach ($command in $Commands) {
        Write-Host "  $command"
      }
    }
  }

  try {
    $response = Read-Host "Proceed? [Y/n]"
  } catch {
    return $false
  }

  if (-not $response) {
    return $true
  }

  switch -Regex ($response.Trim()) {
    "^(y|yes)$" { return $true }
    "^(n|no)$" { return $false }
    default { return $false }
  }
}

function Confirm-OrAbort {
  param(
    [Parameter(Mandatory)]
    [bool]$Ok
  )

  if (-not $Ok) {
    Write-Host "Aborted."
    exit 1
  }
}

# Run from repo root
if (-not (Test-Path -Path "pyproject.toml")) {
  Write-Error "Run this from the repo root (pyproject.toml not found)."
  exit 1
}

# 1) Install uv (if missing)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  $uvInstallUrl = "https://astral.sh/uv/install.ps1"

  Confirm-OrAbort (Confirm-Step `
    -Title "Step 1: Install uv (required)" `
    -Commands @("irm $uvInstallUrl | iex") `
  )

  irm $uvInstallUrl | iex
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Error "uv is still not on PATH. Close/reopen PowerShell, then re-run this script."
  exit 1
}

# 2) We recommend Python 3.13 but support Python 3.10 to 3.13
Confirm-OrAbort (Confirm-Step `
  -Title "Step 2: Install Python $PythonVersion (uv)" `
  -Commands @("uv python install $PythonVersion") `
)
uv python install $PythonVersion

Confirm-OrAbort (Confirm-Step `
  -Title "Step 2: Pin Python $PythonVersion (uv)" `
  -Commands @("uv python pin $PythonVersion") `
)
uv python pin $PythonVersion

# 3) Install project dependencies with uv
Confirm-OrAbort (Confirm-Step `
  -Title "Step 3: Install project dependencies (uv sync)" `
  -Commands @("uv sync") `
)
uv sync

Write-Host "Setup finished. Run:"
Write-Host "  uv run autoscrapper"
