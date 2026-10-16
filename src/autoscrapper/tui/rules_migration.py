from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, SelectionList, Static

from ..items.rules_store import build_rule_migration, complete_rule_migration
from .common import MessageScreen


class RulesMigrationScreen(Screen[bool]):
    BINDINGS = [Binding("escape,ctrl+b", "cancel", "Cancel", priority=True)]

    DEFAULT_CSS = """
    RulesMigrationScreen {
        padding: 1 2;
    }

    #migration-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #migration-search {
        margin-top: 1;
    }

    #migration-list {
        height: 1fr;
    }

    #migration-actions {
        height: auto;
        margin-top: 1;
    }

    #migration-actions Button {
        margin-right: 1;
    }
    """

    def __init__(self, base: str | None = None) -> None:
        super().__init__()
        self.migration = build_rule_migration(base)
        self.selected_keys = {change.key for change in self.migration.changes}
        self.search_query = ""

    def compose(self) -> ComposeResult:
        yield Static("Review existing rules", id="migration-title")
        yield Static("Checked: keep current choice. Unchecked: use automatic.")
        yield Input(placeholder="Search items", id="migration-search")
        yield Static("Current → Automatic", classes="section-title")
        yield Static(id="migration-count")
        yield SelectionList[str](id="migration-list")
        with Horizontal(id="migration-actions"):
            yield Button("Select all", id="migration-select-all")
            yield Button("Clear all", id="migration-clear-all")
            yield Button("Apply", id="migration-apply", variant="primary")
            yield Button("Cancel", id="migration-cancel")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_list()
        self.query_one("#migration-list", SelectionList).focus()

    def _refresh_list(self) -> None:
        query = self.search_query.casefold().strip()
        changes = [
            change
            for change in self.migration.changes
            if not query or query in change.name.casefold()
        ]
        selections = self.query_one("#migration-list", SelectionList)
        selections.clear_options()
        selections.add_options(
            (
                Text.assemble(
                    (change.name, "bold"),
                    f"  {(change.before_action or 'skip').upper()} → "
                    f"{(change.after_action or 'skip').upper()}",
                ),
                change.key,
                change.key in self.selected_keys,
            )
            for change in changes
        )
        self._refresh_count(len(changes))

    def _refresh_count(self, visible_count: int | None = None) -> None:
        if visible_count is None:
            visible_count = self.query_one(
                "#migration-list", SelectionList
            ).option_count
        total = len(self.migration.changes)
        self.query_one("#migration-count", Static).update(
            f"{visible_count}/{total} differences · {len(self.selected_keys)} kept"
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "migration-search":
            self.search_query = event.value
            self._refresh_list()

    def on_selection_list_selection_toggled(
        self, event: SelectionList.SelectionToggled[str]
    ) -> None:
        key = event.selection.value
        if key in event.selection_list.selected:
            self.selected_keys.add(key)
        else:
            self.selected_keys.discard(key)
        self._refresh_count()

    def _apply(self) -> None:
        try:
            complete_rule_migration(self.migration, self.selected_keys)
        except Exception as exc:
            self.app.push_screen(MessageScreen(f"Failed to update rules: {exc}"))
            return
        self.dismiss(True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "migration-select-all":
            self.selected_keys = {change.key for change in self.migration.changes}
            self._refresh_list()
        elif event.button.id == "migration-clear-all":
            self.selected_keys.clear()
            self._refresh_list()
        elif event.button.id == "migration-apply":
            self._apply()
        elif event.button.id == "migration-cancel":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)
