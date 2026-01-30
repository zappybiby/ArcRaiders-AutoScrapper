from __future__ import annotations

from .progress_flow import show_progress_menu


def main(argv=None) -> int:
    _ = argv
    return show_progress_menu()
