from __future__ import annotations

from textual.binding import Binding

from ..common import AppScreen


class ProgressScreen(AppScreen):
    BINDINGS = [
        *AppScreen.BINDINGS,
        Binding("ctrl+p", "back", "Back"),
        Binding("escape", "back", "Back"),
    ]

    def action_back(self) -> None:
        self.app.pop_screen()


def pop_progress_stack(app) -> None:
    while isinstance(app.screen, ProgressScreen):
        app.pop_screen()
