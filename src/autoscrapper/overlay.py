from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading


class ScanOverlay:
    """Keep Qt's event loop in a console-free child process."""

    def __init__(self, hwnd: int, rect: tuple[int, int, int, int]) -> None:
        self.ready = False
        self.error = ""
        self._closed = threading.Event()
        self._updates: queue.Queue[dict] = queue.Queue(maxsize=1)
        self._process = subprocess.Popen(
            [sys.executable, "-m", "autoscrapper.overlay_window"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        threading.Thread(
            target=self._run, args=({"hwnd": hwnd, "rect": rect},), daemon=True
        ).start()

    def _run(self, initial: dict) -> None:
        try:
            self._write(initial)
            output = "Overlay exited before it was ready."
            for line in self._process.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    output = line.strip() or output
                    continue
                if message.get("error"):
                    raise RuntimeError(message["error"])
                if message.get("ready"):
                    self.ready = True
                    output = "Overlay window closed."
                    threading.Thread(target=self._send_updates, daemon=True).start()
            raise RuntimeError(output)
        except (OSError, ValueError, RuntimeError) as exc:
            if not self._closed.is_set():
                self.error = str(exc)

    def _send_updates(self) -> None:
        try:
            while not self._closed.is_set() and not self.error:
                try:
                    state = self._updates.get(timeout=0.1)
                except queue.Empty:
                    continue
                self._write(state)
        except OSError, ValueError:
            # Let the stdout reader preserve any final error sent by the child.
            return

    def _write(self, message: dict) -> None:
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()

    def update(self, state: dict) -> None:
        # A slow GUI needs only the newest snapshot, never an item-event backlog.
        try:
            self._updates.get_nowait()
        except queue.Empty:
            pass
        self._updates.put_nowait(state)

    def close(self) -> None:
        self._closed.set()
        if self._process.poll() is None:
            self._process.terminate()
        self._process.wait()
        try:
            self._process.stdin.close()
        except OSError:
            pass  # Closing a buffered pipe can flush after the child has exited.
        self._process.stdout.close()
