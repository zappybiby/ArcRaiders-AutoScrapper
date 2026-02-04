from __future__ import annotations

import sys

_LEGACY_TEXT_MENU_COMMANDS = {
    "--cli",
    "cli",
    "rules",
    "progress",
    "config",
    "scan-config",
    "scan_configuration",
    "settings",
}


def _run_tui() -> int:
    from .tui import run_tui

    return run_tui()


def _print_usage() -> None:
    print("Usage: autoscrapper [scan [scan options]]")
    print("       autoscrapper [tui|ui]")
    print()
    print("No command starts the Textual UI.")
    print("'scan' runs an immediate scan without opening the UI.")


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return _run_tui()

    cmd, *rest = args
    cmd = cmd.lower().strip()

    if cmd in {"-h", "--help", "help"}:
        _print_usage()
        return 0

    if cmd in {"--tui", "tui", "ui"}:
        return _run_tui()

    if cmd == "scan":
        from .scanner.cli import main as scan_main

        return scan_main(rest)

    if cmd in _LEGACY_TEXT_MENU_COMMANDS:
        print(
            f"'{cmd}' is now managed inside the Textual UI. "
            "Launching the UI instead."
        )
        return _run_tui()

    print(f"Unknown command: {cmd}\n")
    _print_usage()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
