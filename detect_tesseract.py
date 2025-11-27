from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable, Optional

import pytesseract

try:
    import winreg  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - should only happen off Windows
    winreg = None


def _iter_registry_candidates() -> Iterable[Path]:
    """
    Try to find Tesseract via common Windows registry locations.

    This is best-effort: many installers write one of these keys, but not all do.
    """
    if winreg is None:
        return []

    reg_paths = [
        r"SOFTWARE\Tesseract-OCR",
        r"SOFTWARE\WOW6432Node\Tesseract-OCR",
    ]

    candidates: list[Path] = []
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for subkey in reg_paths:
            try:
                key = winreg.OpenKey(root, subkey)
            except OSError:
                continue

            # Common value names in various installers
            for value_name in ("Path", "InstallDir", "InstallPath"):
                try:
                    value, _ = winreg.QueryValueEx(key, value_name)
                except OSError:
                    continue

                if isinstance(value, str):
                    p = Path(value)
                    # If registry already points at tesseract.exe, use it as-is;
                    # otherwise assume it's a directory containing the exe.
                    if p.is_file() and p.name.lower() == "tesseract.exe":
                        candidates.append(p)
                    else:
                        candidates.append(p / "tesseract.exe")

            winreg.CloseKey(key)

    # Deduplicate while preserving order
    seen: set[Path] = set()
    uniq: list[Path] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _iter_common_paths() -> Iterable[Path]:
    """
    Common Windows install locations for Tesseract.

    These are fallbacks used only if PATH/env/registry didn't work.
    """
    candidates: list[Path] = []

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA")

    # Typical global installs
    candidates.append(Path(program_files) / "Tesseract-OCR" / "tesseract.exe")
    candidates.append(Path(program_files_x86) / "Tesseract-OCR" / "tesseract.exe")

    # Some installers use a per-user location under LocalAppData
    if local_appdata:
        candidates.append(Path(local_appdata) / "Tesseract-OCR" / "tesseract.exe")

    # Registry-based locations
    candidates.extend(_iter_registry_candidates())

    # Deduplicate
    seen: set[Path] = set()
    uniq: list[Path] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def find_tesseract_cmd(
    explicit_cmd: Optional[str] = None,
    env_var: str = "TESSERACT_CMD",
) -> str:
    """
    Discover a usable Tesseract executable on Windows.

    Search order:
      1. explicit_cmd argument (if given)
      2. environment variable TESSERACT_CMD (or custom name)
      3. 'tesseract.exe' or 'tesseract' on PATH
      4. common install locations & registry hints

    Returns:
      Absolute path to tesseract.exe

    Raises:
      RuntimeError if nothing usable is found.
    """
    if os.name != "nt":
        raise RuntimeError("find_tesseract_cmd() is intended for Windows only.")

    # 1) Explicit override (e.g. from CLI / config)
    if explicit_cmd:
        p = Path(explicit_cmd)
        if p.is_file():
            return str(p)
        raise RuntimeError(
            f"Explicit Tesseract command '{explicit_cmd}' does not exist "
            "or is not a file."
        )

    # 2) Environment variable
    env_cmd = os.getenv(env_var)
    if env_cmd:
        p = Path(env_cmd)
        if p.is_file():
            return str(p)
        # If user set a bad env var, fail loudly instead of silently ignoring it.
        raise RuntimeError(
            f"Environment variable {env_var} points to '{env_cmd}', "
            "which does not exist or is not a file."
        )

    # 3) PATH lookup
    from_path = shutil.which("tesseract.exe") or shutil.which("tesseract")
    if from_path:
        return from_path

    # 4) Common locations & registry hints
    for candidate in _iter_common_paths():
        if candidate.is_file():
            return str(candidate)

    # 5) Give a detailed error
    msg_lines = [
        "Could not find the Tesseract OCR executable on this Windows system.",
        "",
        "Tried:",
        f"  * explicit_cmd argument: {explicit_cmd!r}",
        f"  * environment variable {env_var}",
        "  * 'tesseract.exe' or 'tesseract' on PATH",
        "  * common install locations and registry hints:",
    ]
    for c in _iter_common_paths():
        msg_lines.append(f"      - {c}")
    msg_lines.extend(
        [
            "",
            "To fix this:",
            "  1) Install Tesseract (e.g. from the official or UB Mannheim installer),",
            "  2) Either:",
            "       - Add the Tesseract install directory to your PATH, or",
            f"       - Set {env_var} to the full path of tesseract.exe, e.g.:",
            f"           {env_var}=C:\\\\Program Files\\\\Tesseract-OCR\\\\tesseract.exe",
        ]
    )

    raise RuntimeError("\n".join(msg_lines))


def configure_pytesseract(
    explicit_cmd: Optional[str] = None,
    env_var: str = "TESSERACT_CMD",
) -> str:
    """
    Discover Tesseract and configure pytesseract to use it.

    Returns:
      The resolved tesseract.exe path.
    """
    cmd = find_tesseract_cmd(explicit_cmd=explicit_cmd, env_var=env_var)
    pytesseract.pytesseract.tesseract_cmd = cmd
    return cmd
