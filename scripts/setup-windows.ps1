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
$uvInstallUrl = "https://astral.sh/uv/install.ps1"
$uvHome = if ($HOME) { $HOME } elseif ($env:USERPROFILE) { $env:USERPROFILE } else { "." }
$uvInstallDir = Join-Path $uvHome ".local/bin"
$uvExe = $null

function Prepend-Path {
  param(
    [Parameter(Mandatory)]
    [string]$Dir
  )

  $dirNormalized = $Dir.Trim().TrimEnd('\\')
  if (-not $dirNormalized) {
    return
  }

  $parts = @()
  if ($env:Path) {
    $parts = $env:Path -split ';'
  }

  foreach ($part in $parts) {
    if ($part.Trim().TrimEnd('\\') -ieq $dirNormalized) {
      return
    }
  }

  if ($env:Path) {
    $env:Path = "$dirNormalized;$env:Path"
  } else {
    $env:Path = $dirNormalized
  }
}

$existingUv = Get-Command uv -ErrorAction SilentlyContinue
if ($existingUv -and ($existingUv.CommandType -eq "Application") -and $existingUv.Path) {
  $uvExe = $existingUv.Path
}

if (-not $uvExe) {
  Confirm-OrAbort (Confirm-Step `
    -Title "Step 1: Install uv (required)" `
    -Commands @(
      ('$env:UV_INSTALL_DIR = "' + $uvInstallDir + '"'),
      "irm $uvInstallUrl | iex"
    ) `
  )

  $previousUvInstallDir = $env:UV_INSTALL_DIR
  $env:UV_INSTALL_DIR = $uvInstallDir
  irm $uvInstallUrl | iex

  if ($null -ne $previousUvInstallDir) {
    $env:UV_INSTALL_DIR = $previousUvInstallDir
  } else {
    Remove-Item Env:UV_INSTALL_DIR -ErrorAction SilentlyContinue
  }

  $candidateDirs = @(
    $uvInstallDir,
    $env:XDG_BIN_HOME,
    $(if ($env:XDG_DATA_HOME) { Join-Path $env:XDG_DATA_HOME "../bin" } else { $null }),
    $(if ($env:CARGO_HOME) { Join-Path $env:CARGO_HOME "bin" } else { Join-Path $uvHome ".cargo/bin" })
  ) | Where-Object { $_ } | Select-Object -Unique

  $searched = @()
  foreach ($dir in $candidateDirs) {
    $candidate = Join-Path $dir "uv.exe"
    $searched += $candidate
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
      $uvExe = $candidate
      break
    }
  }

  if (-not $uvExe) {
    Write-Error ("Couldn't find uv.exe after installing it. Looked in:`n  " + ($searched -join "`n  "))
    Write-Error "Install folder used: $uvInstallDir"
    Write-Error "Close and reopen PowerShell, then run this script again."
    exit 1
  }

  Prepend-Path (Split-Path -Parent $uvExe)

  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv still isn't working in this PowerShell window."
    Write-Error "Install folder used: $uvInstallDir"
    Write-Error ("Looked in:`n  " + ($searched -join "`n  "))
    exit 1
  }
}

$uvVersionOutput = & $uvExe --version
if ($LASTEXITCODE -ne 0) {
  throw "Couldn't check the uv version."
}
if ($uvVersionOutput -notmatch '^uv (\d+\.\d+\.\d+)(?:\s|$)' -or [version]$Matches[1] -lt [version]"0.9.8") {
  throw "uv 0.9.8 or newer is required. Run uv self update (or update through your package manager), then re-run setup."
}

# 2) Install the supported Python version and architecture
$PythonVersion = "3.14"
$PythonRequest = "cpython-3.14-windows-x86_64-none"
Confirm-OrAbort (Confirm-Step `
  -Title "Step 2: Install Python $PythonVersion (64-bit)" `
  -Commands @('& "' + $uvExe + '" python install ' + $PythonRequest) `
)
& $uvExe python install $PythonRequest
if ($LASTEXITCODE -ne 0) {
  throw "Python installation failed."
}

Confirm-OrAbort (Confirm-Step `
  -Title "Step 3: Pin Python $PythonVersion" `
  -Commands @('& "' + $uvExe + '" python pin ' + $PythonVersion) `
)
& $uvExe python pin $PythonVersion
if ($LASTEXITCODE -ne 0) {
  throw "Python version pinning failed."
}

# 3) Install project dependencies with uv
Confirm-OrAbort (Confirm-Step `
  -Title "Step 4: Install project dependencies" `
  -Commands @('& "' + $uvExe + '" sync --python ' + $PythonRequest) `
)
& $uvExe sync --python $PythonRequest
if ($LASTEXITCODE -ne 0) {
  throw "Dependency installation failed."
}

Write-Host "Setup finished. Run:"
Write-Host "  uv run autoscrapper"
