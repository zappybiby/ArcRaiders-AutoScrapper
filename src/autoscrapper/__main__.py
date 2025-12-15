from __future__ import annotations

import sys

from .cli import config as config_cli
from .cli import progress as progress_cli
from .cli import rules as rules_cli
from .cli import scan as scan_cli


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return _menu()

    cmd, *rest = args
    cmd = cmd.lower().strip()

    if cmd == "scan":
        return scan_cli.main(rest)
    if cmd == "rules":
        return rules_cli.main(rest)
    if cmd == "progress":
        return progress_cli.main(rest)
    if cmd in {"config", "scan-config", "scan_configuration", "settings"}:
        return config_cli.main(rest)

    print(f"Unknown command: {cmd}\n")
    return _menu()


def _menu() -> int:
    while True:
        print("Autoscrapper\n")
        print("  1) Scan inventory now")
        print("  2) Dry run scan (no clicks)")
        print("  3) Edit / view rules")
        print("  4) Edit game progress (coming soon)")
        print("  5) Scan configuration")
        print("  q) Quit\n")

        choice = input("Select an option: ").strip().lower()
        if choice == "1":
            return scan_cli.main([])
        if choice == "2":
            return scan_cli.main(["--dry-run"])
        if choice == "3":
            return rules_cli.main([])
        if choice == "4":
            return progress_cli.main([])
        if choice == "5":
            return config_cli.main([])
        if choice in {"q", "quit", "exit"}:
            return 0

        print("\nInvalid choice. Please try again.\n")


if __name__ == "__main__":
    raise SystemExit(main())
