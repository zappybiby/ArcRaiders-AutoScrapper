from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
import sys
from typing import Callable, Iterator, Optional


@dataclass(frozen=True)
class KeyPress:
    name: str
    char: Optional[str] = None


if os.name == "nt":
    import msvcrt

    def _read_key_windows() -> KeyPress:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            code = msvcrt.getwch()
            mapping = {
                "H": "UP",
                "P": "DOWN",
                "K": "LEFT",
                "M": "RIGHT",
                "G": "HOME",
                "O": "END",
                "I": "PAGE_UP",
                "Q": "PAGE_DOWN",
            }
            return KeyPress(mapping.get(code, "UNKNOWN"))
        if ch in ("\r", "\n"):
            return KeyPress("ENTER")
        if ch in ("\x1b",):
            return KeyPress("ESC")
        if ch in ("\x08", "\x7f"):
            return KeyPress("BACKSPACE")
        if ch == "\t":
            return KeyPress("TAB")
        if ch == "\x03":
            raise KeyboardInterrupt
        return KeyPress("CHAR", ch)

    @contextmanager
    def key_reader() -> Iterator[Callable[[], KeyPress]]:
        yield _read_key_windows

else:
    import termios
    import tty

    def _read_key_posix() -> KeyPress:
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            nxt = sys.stdin.read(1)
            if nxt == "[":
                code = sys.stdin.read(1)
                mapping = {
                    "A": "UP",
                    "B": "DOWN",
                    "C": "RIGHT",
                    "D": "LEFT",
                    "H": "HOME",
                    "F": "END",
                }
                if code == "5":
                    sys.stdin.read(1)
                    return KeyPress("PAGE_UP")
                if code == "6":
                    sys.stdin.read(1)
                    return KeyPress("PAGE_DOWN")
                return KeyPress(mapping.get(code, "UNKNOWN"))
            if nxt == "O":
                code = sys.stdin.read(1)
                mapping = {"H": "HOME", "F": "END"}
                return KeyPress(mapping.get(code, "UNKNOWN"))
            return KeyPress("ESC")
        if ch in ("\r", "\n"):
            return KeyPress("ENTER")
        if ch in ("\x7f", "\b"):
            return KeyPress("BACKSPACE")
        if ch == "\t":
            return KeyPress("TAB")
        if ch == "\x03":
            raise KeyboardInterrupt
        return KeyPress("CHAR", ch)

    @contextmanager
    def key_reader() -> Iterator[Callable[[], KeyPress]]:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            yield _read_key_posix
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
