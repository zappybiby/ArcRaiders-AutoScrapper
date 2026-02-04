from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from .common import AppScreen, MessageScreen, update_inline_filter
from ..items.rules_diff import RuleChange
from ..items.rules_store import (
    CUSTOM_RULES_PATH,
    load_rules,
    normalize_action,
    save_custom_rules,
    using_custom_rules,
)


def _display_action(item: dict) -> str:
    action = item.get("action")
    if isinstance(action, str) and action.strip():
        return action.strip().upper()
    decisions = item.get("decision")
    if isinstance(decisions, list):
        return ", ".join(str(d).upper() for d in decisions if isinstance(d, str))
    return ""


def _action_badge(item: dict) -> tuple[str, str]:
    action = normalize_action(str(item.get("action", "")))
    if action == "keep":
        return ("KEEP", "bold green")
    if action == "sell":
        return ("SELL", "bold yellow")
    if action == "recycle":
        return ("RECYCLE", "bold magenta")
    display = _display_action(item).strip().upper()
    if display:
        return (display, "cyan")
    return ("UNKNOWN", "dim")


def _filter_indices(items: List[dict], query: str) -> List[int]:
    if not query:
        return list(range(len(items)))
    q = query.lower().strip()
    matches: List[int] = []
    for idx, item in enumerate(items):
        name = str(item.get("name", "")).lower()
        item_id = str(item.get("id", "")).lower()
        if q in name or (item_id and q in item_id):
            matches.append(idx)
    return matches


class ConfirmResetRulesScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmResetRulesScreen {
        align: center middle;
    }

    #confirm-reset-box {
        width: 72%;
        max-width: 84;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }

    #confirm-reset-actions {
        margin-top: 1;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-reset-box"):
            yield Static("Reset rules to default?", classes="modal-title")
            yield Static("This deletes your custom rules and restores defaults.")
            with Horizontal(id="confirm-reset-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Reset", id="confirm-reset", variant="warning")

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(False)
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(False)
        elif event.button.id == "confirm-reset":
            self.dismiss(True)


class RulesScreen(AppScreen):
    BINDINGS = [
        *AppScreen.BINDINGS,
        Binding("up", "cursor_up", "Move up", priority=True),
        Binding("down", "cursor_down", "Move down", priority=True),
        Binding("left", "previous_action", "Prev action", priority=True),
        Binding("right", "next_action", "Next action", priority=True),
        Binding("ctrl+1", "set_keep", "Keep"),
        Binding("ctrl+2", "set_sell", "Sell"),
        Binding("ctrl+3", "set_recycle", "Recycle"),
        Binding("ctrl+n", "new_rule", "Add rule"),
        Binding("ctrl+d", "delete_rule", "Delete"),
        Binding("ctrl+r", "reset_rules", "Reset"),
        Binding("escape", "clear_or_back", "Clear filter / Back"),
    ]

    DEFAULT_CSS = """
    RulesScreen {
        padding: 1 2;
    }

    #rules-filter {
        margin-bottom: 1;
    }

    #rules-layout {
        height: 1fr;
    }

    #rules-list {
        width: 55%;
    }

    #rules-detail {
        width: 45%;
        padding-left: 1;
    }

    #rule-selected {
        margin-top: 1;
        text-style: bold;
    }

    #action-buttons {
        margin-top: 1;
        height: auto;
    }

    #action-buttons Button {
        min-width: 12;
    }

    #action-buttons Button:focus {
        border: tall #60a5fa;
    }

    #action-buttons Button.is-current-action {
        background: #14532d;
        color: #dcfce7;
        border: tall #22c55e;
        text-style: bold;
    }

    #action-buttons Button.is-current-action:focus {
        background: #1e3a8a;
        color: #eff6ff;
        border: tall #93c5fd;
    }

    #rules-advanced {
        margin-top: 1;
    }

    #rules-advanced-actions,
    #rules-actions,
    #rules-actions-2 {
        margin-top: 1;
        height: auto;
    }

    .hint {
        color: $text-muted;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.payload = load_rules()
        self.items = list(self.payload.get("items", []))
        self.filtered: List[int] = []
        self.search_query = ""
        self.selected_index: Optional[int] = None
        self.mode: str = "edit"
        self.current_action: str = "keep"
        self._updating_form = False

    def compose(self) -> ComposeResult:
        yield Static("Rules", classes="menu-title")
        yield Static(id="rules-filter", classes="hint")
        with Horizontal(id="rules-layout"):
            yield OptionList(id="rules-list")
            with Vertical(id="rules-detail"):
                yield Static(id="rules-status", classes="hint")
                yield Static(id="rule-selected")
                yield Static(id="rule-details")
                yield Static("Edit rule", classes="section-title")
                yield Static("Action", classes="section-title")
                with Horizontal(id="action-buttons"):
                    yield Button("Keep", id="action-keep")
                    yield Button("Sell", id="action-sell")
                    yield Button("Recycle", id="action-recycle")
                yield Static(
                    "Ctrl+1 keep • Ctrl+2 sell • Ctrl+3 recycle • "
                    "Ctrl+N add rule • All edits auto-save",
                    classes="hint",
                )
                with Vertical(id="rules-advanced"):
                    yield Static("Advanced", classes="section-title")
                    yield Input(placeholder="Name", id="rule-name")
                    yield Input(placeholder="Item id (optional)", id="rule-id")
                    with Horizontal(id="rules-advanced-actions"):
                        yield Button("New rule", id="new")
                with Horizontal(id="rules-actions"):
                    yield Button("Delete", id="delete", variant="warning")
                with Horizontal(id="rules-actions-2"):
                    yield Button("Reset to default", id="reset")
                    yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_list()
        self._refresh_details()
        self.query_one("#rules-list", OptionList).focus()

    def _refresh_filter_hint(self) -> None:
        filter_text = self.search_query or "all"
        self.query_one("#rules-filter", Static).update(
            f"Type to filter by name or id • Backspace deletes • Esc clears/back • "
            f"Filter: {filter_text} ({len(self.filtered)} matches)"
        )

    def _refresh_list(self) -> None:
        previous_selection = self.selected_index
        self.filtered = _filter_indices(self.items, self.search_query)
        menu = self.query_one("#rules-list", OptionList)
        options = []
        for idx in self.filtered:
            item = self.items[idx]
            action_label, action_style = _action_badge(item)
            label = Text.assemble(
                (f"{idx + 1:>3} ", "dim"),
                (str(item.get("name", "")), "bold"),
                ("  ", ""),
                (action_label, action_style),
            )
            options.append(Option(label, id=str(idx)))
        menu.set_options(options)
        if options:
            if previous_selection in self.filtered:
                highlighted = self.filtered.index(previous_selection)
            else:
                highlighted = 0
            menu.highlighted = highlighted
            self.selected_index = self.filtered[highlighted]
        else:
            self.selected_index = None
        self._refresh_filter_hint()

    def _refresh_details(self) -> None:
        status = "Custom rules active • Auto-save enabled"
        if not using_custom_rules():
            status = "Default rules active • First edit creates custom rules"
        self.query_one("#rules-status", Static).update(status)

        if self.mode == "add":
            self.query_one("#rule-selected", Static).update("Selected: New rule")
            self.query_one("#rule-details", Static).update(
                "Create a new rule using the Advanced fields."
            )
            return

        if self.selected_index is None:
            if self.search_query:
                self.query_one("#rule-selected", Static).update("Selected: none")
                self.query_one("#rule-details", Static).update(
                    "No matching rules for this filter."
                )
            else:
                self.query_one("#rule-selected", Static).update("Selected: none")
                self.query_one("#rule-details", Static).update("No rule selected.")
            self._populate_edit_fields(None, set_add_mode=False)
            return

        item = self.items[self.selected_index]
        self.query_one("#rule-selected", Static).update(
            f"Selected: {item.get('name', '')}"
        )
        details = [
            f"Current action: {_display_action(item)}",
        ]
        analysis = item.get("analysis")
        if isinstance(analysis, list) and analysis:
            details.append("Reasons:")
            details.extend([f" • {reason}" for reason in analysis[:6]])
            if len(analysis) > 6:
                details.append(f" • … +{len(analysis) - 6} more")
        self.query_one("#rule-details", Static).update("\n".join(details))
        self._populate_edit_fields(item)

    def _populate_edit_fields(
        self, item: Optional[dict], *, set_add_mode: bool = False
    ) -> None:
        name_input = self.query_one("#rule-name", Input)
        id_input = self.query_one("#rule-id", Input)
        self._updating_form = True
        if not item:
            try:
                name_input.value = ""
                id_input.value = ""
            finally:
                self._updating_form = False
            self.current_action = "keep"
            if set_add_mode:
                self.mode = "add"
            elif self.mode != "add":
                self.mode = "edit"
            self._refresh_action_buttons()
            return
        try:
            name_input.value = str(item.get("name", ""))
            id_input.value = str(item.get("id", ""))
        finally:
            self._updating_form = False
        self.current_action = (
            normalize_action(str(item.get("action", "keep"))) or "keep"
        )
        self.mode = "edit"
        self._refresh_action_buttons()

    def _refresh_action_buttons(self) -> None:
        button_ids = {
            "keep": "action-keep",
            "sell": "action-sell",
            "recycle": "action-recycle",
        }
        for action, button_id in button_ids.items():
            button = self.query_one(f"#{button_id}", Button)
            if action == self.current_action:
                button.add_class("is-current-action")
            else:
                button.remove_class("is-current-action")

    def _persist_rules(self) -> None:
        self.payload["items"] = self.items
        save_custom_rules(self.payload)

    def _set_action(self, action: str) -> None:
        action_value = normalize_action(action)
        if not action_value:
            return
        if self.current_action == action_value and self.mode != "edit":
            return
        self.current_action = action_value
        self._refresh_action_buttons()
        if self.mode == "edit" and self.selected_index is not None:
            item = self.items[self.selected_index]
            if normalize_action(str(item.get("action", ""))) != action_value:
                item["action"] = action_value
                self._persist_rules()
                self._refresh_list()
                self._refresh_details()

    def _autosave_detail_changes(self) -> None:
        if self._updating_form:
            return

        name = self.query_one("#rule-name", Input).value.strip()
        item_id = self.query_one("#rule-id", Input).value.strip()
        action = normalize_action(self.current_action) or "keep"

        if self.mode == "add":
            if not name:
                return
            entry = {"name": name, "action": action}
            if item_id:
                entry["id"] = item_id
            self.items.append(entry)
            self.selected_index = len(self.items) - 1
            self.mode = "edit"
            self._persist_rules()
            self._refresh_list()
            self._refresh_details()
            return

        if self.selected_index is None or not name:
            return

        item = self.items[self.selected_index]
        changed = False
        if str(item.get("name", "")) != name:
            item["name"] = name
            changed = True
        if normalize_action(str(item.get("action", ""))) != action:
            item["action"] = action
            changed = True
        if item_id:
            if str(item.get("id", "")) != item_id:
                item["id"] = item_id
                changed = True
        elif "id" in item:
            item.pop("id", None)
            changed = True

        if not changed:
            return

        self._persist_rules()
        self._refresh_list()
        self._refresh_details()

    def _confirm_reset_default(self) -> None:
        self.app.push_screen(ConfirmResetRulesScreen(), self._handle_reset_confirmation)

    def _handle_reset_confirmation(self, confirmed: bool) -> None:
        if confirmed:
            self._reset_default()

    def _delete_selected(self) -> None:
        if self.selected_index is None:
            self.app.push_screen(MessageScreen("No rule selected."))
            return
        item = self.items.pop(self.selected_index)
        self._persist_rules()
        self.app.push_screen(MessageScreen(f"Removed '{item.get('name', '')}'."))
        self._refresh_list()
        self._refresh_details()

    def _reset_default(self) -> None:
        if CUSTOM_RULES_PATH.exists():
            CUSTOM_RULES_PATH.unlink(missing_ok=True)
        self.payload = load_rules()
        self.items = list(self.payload.get("items", []))
        self.app.push_screen(MessageScreen("Custom rules removed. Defaults restored."))
        self._refresh_list()
        self._refresh_details()

    def _is_editing_advanced_fields(self) -> bool:
        focused = self.focused
        return isinstance(focused, Input) and focused.id in {"rule-name", "rule-id"}

    def _move_highlight(self, delta: int) -> None:
        if not self.filtered:
            return
        menu = self.query_one("#rules-list", OptionList)
        current = menu.highlighted if menu.highlighted is not None else 0
        new_index = max(0, min(len(self.filtered) - 1, current + delta))
        if new_index == current:
            return
        menu.highlighted = new_index
        self.selected_index = self.filtered[new_index]
        self.mode = "edit"
        self._refresh_details()

    def action_cursor_up(self) -> None:
        if self._is_editing_advanced_fields():
            return
        self._move_highlight(-1)

    def action_cursor_down(self) -> None:
        if self._is_editing_advanced_fields():
            return
        self._move_highlight(1)

    def action_set_keep(self) -> None:
        self._set_action("keep")

    def action_set_sell(self) -> None:
        self._set_action("sell")

    def action_set_recycle(self) -> None:
        self._set_action("recycle")

    def _cycle_action(self, delta: int) -> None:
        actions = ["keep", "sell", "recycle"]
        current = normalize_action(self.current_action) or "keep"
        index = actions.index(current)
        next_index = (index + delta) % len(actions)
        self._set_action(actions[next_index])

    def action_previous_action(self) -> None:
        if self._is_editing_advanced_fields():
            return
        self._cycle_action(-1)

    def action_next_action(self) -> None:
        if self._is_editing_advanced_fields():
            return
        self._cycle_action(1)

    def action_new_rule(self) -> None:
        self._populate_edit_fields(None, set_add_mode=True)
        self._refresh_details()
        self.query_one("#rule-name", Input).focus()

    def action_delete_rule(self) -> None:
        self._delete_selected()

    def action_reset_rules(self) -> None:
        self._confirm_reset_default()

    def action_clear_or_back(self) -> None:
        if self._is_editing_advanced_fields():
            self.query_one("#rules-list", OptionList).focus()
            return
        if self.mode == "add":
            self.mode = "edit"
            self._refresh_details()
            self.query_one("#rules-list", OptionList).focus()
            return
        if self.search_query:
            self.search_query = ""
            self._refresh_list()
            self._refresh_details()
            return
        self.app.pop_screen()

    def on_key(self, event: events.Key) -> None:
        if self._is_editing_advanced_fields():
            return

        updated_query, consumed = update_inline_filter(event, self.search_query)
        if not consumed:
            return
        if updated_query != self.search_query:
            self.search_query = updated_query
            self._refresh_list()
            self._refresh_details()
        event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id not in {"rule-name", "rule-id"}:
            return
        self._autosave_detail_changes()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is None:
            return
        try:
            self.selected_index = int(event.option_id)
        except ValueError:
            return
        self.mode = "edit"
        self._refresh_details()

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option_id is None:
            return
        try:
            self.selected_index = int(event.option_id)
        except ValueError:
            return
        self.mode = "edit"
        self._refresh_details()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "action-keep":
            self._set_action("keep")
        elif button_id == "action-sell":
            self._set_action("sell")
        elif button_id == "action-recycle":
            self._set_action("recycle")
        elif button_id == "new":
            self.action_new_rule()
        elif button_id == "delete":
            self._delete_selected()
        elif button_id == "reset":
            self._confirm_reset_default()
        elif button_id == "back":
            self.app.pop_screen()


class RulesChangesScreen(AppScreen):
    BINDINGS = [
        *AppScreen.BINDINGS,
        Binding("ctrl+p", "back", "Back"),
        Binding("escape", "back", "Back"),
        Binding("/", "focus_search", "Search"),
    ]

    DEFAULT_CSS = """
    RulesChangesScreen {
        padding: 1 2;
    }

    #changes-layout {
        height: 1fr;
    }

    #changes-list {
        width: 55%;
    }

    #changes-detail {
        width: 45%;
        padding-left: 1;
    }

    #changes-actions {
        margin-top: 1;
        height: auto;
    }

    .hint {
        color: $text-muted;
    }
    """

    def __init__(
        self,
        changes: List[RuleChange],
        *,
        item_count: int,
        default_count: int,
    ) -> None:
        super().__init__()
        self.changes = list(changes)
        self.filtered: List[int] = []
        self.search_query = ""
        self.selected_index: Optional[int] = None
        self.item_count = item_count
        self.default_count = default_count

    def compose(self) -> ComposeResult:
        yield Static("Rule Changes", classes="menu-title")
        yield Static(id="changes-summary", classes="hint")
        yield Input(placeholder="Search changes by name or id", id="changes-search")
        with Horizontal(id="changes-layout"):
            yield OptionList(id="changes-list")
            with Vertical(id="changes-detail"):
                yield Static(id="changes-detail-body")
        with Horizontal(id="changes-actions"):
            yield Button("Done", id="done", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_list()
        self._refresh_details()
        if self.changes:
            self.query_one("#changes-list", OptionList).focus()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_focus_search(self) -> None:
        self.query_one("#changes-search", Input).focus()

    def _update_summary(self) -> None:
        total_changes = len(self.changes)
        showing = len(self.filtered)
        base_total = self.default_count or self.item_count
        summary = (
            f"Changed rules: {total_changes} | "
            f"Default items: {base_total} | "
            f"Showing: {showing}"
        )
        self.query_one("#changes-summary", Static).update(summary)

    def _filter_indices(self) -> List[int]:
        if not self.search_query:
            return list(range(len(self.changes)))
        q = self.search_query.lower().strip()
        if not q:
            return list(range(len(self.changes)))
        matches: List[int] = []
        for idx, change in enumerate(self.changes):
            name = change.name.lower()
            item_id = change.item_id.lower()
            if q in name or (item_id and q in item_id):
                matches.append(idx)
        return matches

    def _option_label(self, change: RuleChange, index: int) -> Text:
        action = f"{change.before_action.upper()} -> {change.after_action.upper()}"
        return Text.assemble(
            (f"{index + 1:>3} ", "dim"),
            (change.name, "bold"),
            ("  ", ""),
            (action, "cyan"),
        )

    def _refresh_list(self) -> None:
        self.filtered = self._filter_indices()
        menu = self.query_one("#changes-list", OptionList)
        options = []
        for list_index, change_index in enumerate(self.filtered):
            change = self.changes[change_index]
            label = self._option_label(change, list_index)
            options.append(Option(label, id=str(change_index)))
        menu.set_options(options)
        if options:
            menu.highlighted = 0
            self.selected_index = self.filtered[0]
        else:
            self.selected_index = None
        self._update_summary()

    def _refresh_details(self) -> None:
        detail = self.query_one("#changes-detail-body", Static)
        if self.selected_index is None:
            detail.update(
                "No changes match your filter."
                if self.changes
                else "No changes detected."
            )
            return
        change = self.changes[self.selected_index]
        lines = [
            f"Name: {change.name}",
            f"ID: {change.item_id}",
            f"Action: {change.before_action.upper()} -> {change.after_action.upper()}",
        ]
        if change.reasons:
            lines.append("Reasons:")
            lines.extend([f"- {reason}" for reason in change.reasons[:8]])
            if len(change.reasons) > 8:
                lines.append(f"- ... +{len(change.reasons) - 8} more")
        else:
            lines.append("Reasons: none recorded")
        detail.update("\n".join(lines))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "changes-search":
            self.search_query = event.value
            self._refresh_list()
            self._refresh_details()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is None:
            return
        try:
            self.selected_index = int(event.option_id)
        except ValueError:
            return
        self._refresh_details()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "done":
            self.app.pop_screen()
