from __future__ import annotations

import sys
from unittest.mock import patch

from autoscrapper.__main__ import _print_usage, main


def test_main_no_args() -> None:
    with patch("autoscrapper.__main__._run_tui") as mock_run_tui:
        mock_run_tui.return_value = 0
        result = main([])
        assert result == 0
        mock_run_tui.assert_called_once()


def test_main_sys_argv_no_args() -> None:
    with patch.object(sys, "argv", ["autoscrapper"]):
        with patch("autoscrapper.__main__._run_tui") as mock_run_tui:
            mock_run_tui.return_value = 0
            result = main()
            assert result == 0
            mock_run_tui.assert_called_once()


def test_main_help(capsys) -> None:
    for arg in ["-h", "--help", "help"]:
        result = main([arg])
        assert result == 0
        captured = capsys.readouterr()
        assert "Usage: autoscrapper" in captured.out


def test_main_scan() -> None:
    with patch("autoscrapper.scanner.cli.main") as mock_scan_main:
        mock_scan_main.return_value = 0
        result = main(["scan", "--dry-run"])
        assert result == 0
        mock_scan_main.assert_called_once_with(["--dry-run"])


def test_main_unknown_command(capsys) -> None:
    result = main(["unknown"])
    assert result == 2
    captured = capsys.readouterr()
    assert "Unknown command: unknown" in captured.out
    assert "Usage: autoscrapper" in captured.out


def test_print_usage(capsys) -> None:
    _print_usage()
    captured = capsys.readouterr()
    assert "Usage: autoscrapper" in captured.out
