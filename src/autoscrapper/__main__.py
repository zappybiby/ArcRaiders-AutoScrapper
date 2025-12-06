from __future__ import annotations

import sys

from .cli import progress as progress_cli
from .cli import rules as rules_cli
from .cli import scan as scan_cli


def main(argv=None) -> int:
    """
    Entry point for the CLI that dispatches to subcommands or shows an interactive menu.
    
    When called, this function uses argv (or the process arguments if argv is None) to determine a command:
    - "scan" dispatches to the scan subcommand
    - "rules" dispatches to the rules subcommand
    - "progress" dispatches to the progress subcommand
    If no arguments are provided or the command is unrecognized, an interactive menu is presented.
    
    Parameters:
        argv (Optional[Sequence[str]]): Arguments to parse (omitting the program name). If None, uses the process arguments.
    
    Returns:
        int: Exit status code produced by the invoked subcommand or the interactive menu.
    """
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
    """
    Display an interactive text menu to choose and run a CLI subcommand.
    
    Prompts the user to select scanning, rules editing/viewing, progress editing, or quit, then dispatches to the corresponding subcommand. For any other input, exits without running a subcommand.
    
    Returns:
        int: Exit code returned by the chosen subcommand, or 0 when quitting or on unrecognized input.
    """
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