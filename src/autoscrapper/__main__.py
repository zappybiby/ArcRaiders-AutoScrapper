from __future__ import annotations

import sys

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

    print(f"Unknown command: {cmd}\n")
    return _menu()


def _menu() -> int:
    print("Autoscrapper\n")
    print("  1) Scan inventory now")
    print("  2) Edit / view rules")
    print("  3) Edit game progress (coming soon)")
    print("  q) Quit\n")

    choice = input("Select an option: ").strip().lower()
    if choice == "1":
        return scan_cli.main([])
    if choice == "2":
        return rules_cli.main([])
    if choice == "3":
        return progress_cli.main([])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
