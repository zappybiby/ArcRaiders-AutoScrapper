---
applyTo: "**/*.{bat,cmd}"
---

# CMD/Batch Scripting Standards

<Goals>

- Fail fast: check errorlevel after commands
- Performance: minimize overhead, batch operations
- Clarity: descriptive names, consistent style

</Goals>

## Template

```batch
@echo off
setlocal enabledelayedexpansion
setlocal enableextensions
```

<Standards>

**Variables**: `set "name=value"` for assignment. `%var%` immediate, `!var!` delayed (in code blocks)
**Control Flow**: `if exist`, `if "%errorlevel%"=="0"`, `for %%i in (...) do`
**Subroutines**: `call :label`, `exit /b 0` to return
**Errors**: `if errorlevel 1` or `command && echo Success || echo Failure`

</Standards>

```batch
:: Subroutine with parameters
call :process_file "input.txt"
goto :eof

:process_file
set "filename=%~1"
set "fullpath=%~f1"
echo Processing: %fullpath%
exit /b 0
```

<Limitations>

- No unquoted paths with spaces
- No `%var%` inside code blocks (use `!var!` with delayed expansion)
- No missing errorlevel checks
- No environment modification without `setlocal`

</Limitations>

<Security>

- No hardcoded credentials
- Input validation before use
- Use `setlocal` to avoid polluting environment
- Temporary files created securely

</Security>
