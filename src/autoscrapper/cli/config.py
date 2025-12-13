from __future__ import annotations

from dataclasses import replace

from ..config import ScanSettings, config_path, load_scan_settings, reset_scan_settings, save_scan_settings
from ..interaction.ui_windows import SCROLL_CLICKS_PER_PAGE


def _format_settings(settings: ScanSettings) -> list[str]:
    pages_label = "Auto-detect" if settings.pages_mode == "auto" else f"Manual ({settings.pages})"
    scroll_label = (
        f"Default ({SCROLL_CLICKS_PER_PAGE})"
        if settings.scroll_clicks_per_page is None
        else f"Custom ({settings.scroll_clicks_per_page})"
    )
    debug_label = "On" if settings.debug_ocr else "Off"
    profile_label = "On" if settings.profile else "Off"

    return [
        f"Pages: {pages_label}",
        f"Scroll clicks/page: {scroll_label}",
        f"Debug OCR: {debug_label}",
        f"Profile timing: {profile_label}",
    ]


def _prompt_int(prompt: str, *, min_value: int) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            value = int(raw)
        except ValueError:
            print("Please enter a whole number.")
            continue
        if value < min_value:
            print(f"Please enter a value >= {min_value}.")
            continue
        return value


def main(argv=None) -> int:
    _ = argv
    while True:
        settings = load_scan_settings()
        print("\nScan Configuration (persists across sessions)\n")
        for idx, line in enumerate(_format_settings(settings), start=1):
            print(f"  {idx}) {line}")
        print("  5) Reset all to defaults")
        print("  b) Back\n")
        print(f"Config file: {config_path()}\n")

        choice = input("Select an option: ").strip().lower()
        if choice == "b":
            return 0

        if choice == "1":
            mode = input("Pages: (a)uto-detect or (m)anual? ").strip().lower()
            if mode.startswith("a"):
                save_scan_settings(replace(settings, pages_mode="auto", pages=None))
                continue
            if mode.startswith("m"):
                pages = _prompt_int("Enter number of pages to scan: ", min_value=1)
                save_scan_settings(replace(settings, pages_mode="manual", pages=pages))
                continue
            print("Invalid choice.")
            continue

        if choice == "2":
            mode = input("Scroll clicks/page: (d)efault or (c)ustom? ").strip().lower()
            if mode.startswith("d"):
                save_scan_settings(replace(settings, scroll_clicks_per_page=None))
                continue
            if mode.startswith("c"):
                clicks = _prompt_int("Enter scroll clicks per page: ", min_value=0)
                save_scan_settings(replace(settings, scroll_clicks_per_page=clicks))
                continue
            print("Invalid choice.")
            continue

        if choice == "3":
            save_scan_settings(replace(settings, debug_ocr=not settings.debug_ocr))
            continue

        if choice == "4":
            save_scan_settings(replace(settings, profile=not settings.profile))
            continue

        if choice == "5":
            reset_scan_settings()
            continue

        print("Invalid choice.")
