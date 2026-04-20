---

applyTo: "**/*.{ps1,psm1,psd1}"

# PowerShell Scripting Standards

<Goals>

- Fail fast: `Set-StrictMode -Version Latest`, `$ErrorActionPreference = "Stop"`
- Pipeline-first: object manipulation over string parsing
- Cmdlet design: Verb-Noun naming with approved verbs

</Goals>

## Template

```powershell
param(
 [Parameter(Mandatory=$true)]
 [string]$Path,
 [int]$Timeout = 30
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
```

<Standards>

**Naming**: Verb-Noun (`Get-UserById`), approved verbs via `Get-Verb`
**Error Handling**: Try-catch with specific exception types, `-ErrorAction Stop`
**Pipeline**: Object-based, `Where-Object`, `ForEach-Object`, `[PSCustomObject]@{}`
**Output**: `Write-Host` (user), `Write-Error` (errors), `Write-Verbose` (detail), `Write-Debug` (debug)

</Standards>

try {
 $result = Get-Item $Path -ErrorAction Stop
} catch [ItemNotFoundException] {
 Write-Error "Item not found: $Path"
 exit 1
} catch {
 Write-Error "Unexpected error: $_"
 exit 2
}

**Linting**: `Invoke-ScriptAnalyzer -Path script.ps1`
**Testing**: `Invoke-Pester -Path tests/`

<Limitations>

- No hardcoded credentials (use SecureString)
- No `Invoke-Expression` with untrusted input
- No `$ErrorActionPreference = "SilentlyContinue"`
- No unquoted paths with spaces

</Limitations>
