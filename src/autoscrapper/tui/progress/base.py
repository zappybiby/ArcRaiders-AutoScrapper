from __future__ import annotations

from ..common import AppScreen


class ProgressScreen(AppScreen):
    BINDINGS = [*AppScreen.BINDINGS]


def pop_progress_stack(app) -> None:
    while isinstance(app.screen, ProgressScreen):
        app.pop_screen()
