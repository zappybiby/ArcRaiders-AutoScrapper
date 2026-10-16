from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, SelectionList, Static

from ..items.rules_store import build_rule_migration, complete_rule_migration
from .common import MessageScreen, RuleSelectionList, rule_columns


class RulesMigrationScreen(Screen[bool]):
    BINDINGS = [Binding("escape,ctrl+b", "cancel", "Cancel", priority=True)]

    DEFAULT_CSS = """
    RulesMigrationScreen {
        padding: 1 2;
    }

    #migration-list > .selection-list--button,
    #migration-list > .selection-list--button-highlighted {
        color: $panel;
    }

    #migration-actions {
        height: auto;
    }

    #migration-actions Button {
        margin-right: 1;
    }
    """

    def __init__(self, base: str | None = None) -> None:
        super().__init__()
        self.migration = build_rule_migration(base)
        self.changes_by_key = {change.key: change for change in self.migration.changes}
        self.selected_keys: set[str] = set()
        self.search_query = ""

    def compose(self) -> ComposeResult:
        yield Static("Update custom rules", id="migration-title", classes="rule-title")
        yield Input(placeholder="Search items", id="migration-search")
        yield Static(
            id="migration-columns", classes="rule-columns rule-columns-with-checkbox"
        )
        yield RuleSelectionList(id="migration-list", classes="rule-list")
        yield Static(id="migration-details", classes="rule-details")
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
        highlighted_key = (
            selections.get_option_at_index(selections.highlighted).value
            if selections.highlighted is not None
            else None
        )
        prompt_width = selections.scrollable_content_region.width - 6

        self.query_one("#migration-columns", Static).update(
            rule_columns("Item", "Current Action", "Proposed Update", prompt_width)
        )
        selections.clear_options()
        selections.add_options(
            (
                rule_columns(
                    change.name,
                    (change.before_action or "skip").upper(),
                    (change.after_action or "skip").upper(),
                    prompt_width,
                ),
                change.key,
                change.key in self.selected_keys,
            )
            for change in changes
        )
        selections.highlighted = (
            next(
                (
                    i
                    for i, change in enumerate(changes)
                    if change.key == highlighted_key
                ),
                0,
            )
            if changes
            else None
        )
        self._refresh_details()

    def _refresh_details(self) -> None:
        selections = self.query_one("#migration-list", SelectionList)
        detail = self.query_one("#migration-details", Static)
        if selections.highlighted is None:
            detail.update("")
            return
        key = selections.get_option_at_index(selections.highlighted).value
        change = self.changes_by_key[key]
        analysis = change.item.get("analysis", [])
        if not isinstance(analysis, list):
            analysis = []
        reasons = [
            reason.strip()
            for reason in analysis
            if isinstance(reason, str)
            and reason.strip()
            and not reason.strip().lower().startswith("override:")
        ]
        if change.after_action is None:
            reasons = ["This saved item has no rule in the current game data."]
        elif not reasons:
            reasons = ["No reasons recorded for this recommendation."]
        before = change.before_item or {}
        for field, label in (("name", "Name"), ("value", "Value")):
            old, new = before.get(field), change.item.get(field)
            if old is not None and new is not None and old != new:
                reasons.append(f"{label}: {old} → {new}")
        detail.update(Text.assemble((f"{change.name}\n", "bold"), "\n".join(reasons)))

    def on_resize(self, _event: events.Resize) -> None:
        if self.is_mounted:
            self._refresh_list()

    def on_selection_list_selection_highlighted(
        self, _event: SelectionList.SelectionHighlighted[str]
    ) -> None:
        self._refresh_details()

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

    def _apply(self) -> None:
        retained_keys = {
            change.key
            for change in self.migration.changes
            if change.key not in self.selected_keys
        }
        try:
            complete_rule_migration(self.migration, retained_keys)
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
