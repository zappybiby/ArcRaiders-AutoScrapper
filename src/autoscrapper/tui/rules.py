from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from .common import AppScreen, MessageScreen
from ..items.rules_store import (
    CUSTOM_RULES_PATH,
    active_rules_path,
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


class RulesScreen(AppScreen):
    DEFAULT_CSS = """
    RulesScreen {
        padding: 1 2;
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

    #rules-actions {
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

    def compose(self) -> ComposeResult:
        yield Static("Rules", classes="menu-title")
        yield Input(placeholder="Search rules by name or id", id="rules-search")
        with Horizontal(id="rules-layout"):
            yield OptionList(id="rules-list")
            with Vertical(id="rules-detail"):
                yield Static(id="rules-status", classes="hint")
                yield Static(id="rule-details")
                yield Static("Edit rule", classes="section-title")
                yield Input(placeholder="Name", id="rule-name")
                yield Input(placeholder="Item id (optional)", id="rule-id")
                yield Static("Action", classes="section-title")
                with Horizontal():
                    yield Button("Keep", id="action-keep")
                    yield Button("Sell", id="action-sell")
                    yield Button("Recycle", id="action-recycle")
                yield Static(id="rule-action", classes="hint")
                with Horizontal(id="rules-actions"):
                    yield Button("Save changes", id="save", variant="primary")
                    yield Button("New rule", id="new")
                    yield Button("Delete", id="delete", variant="warning")
                with Horizontal(id="rules-actions-2"):
                    yield Button("Reset to default", id="reset")
                    yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_list()
        self._refresh_details()

    def _refresh_list(self) -> None:
        self.filtered = _filter_indices(self.items, self.search_query)
        menu = self.query_one("#rules-list", OptionList)
        options = []
        for idx in self.filtered:
            item = self.items[idx]
            label = Text.assemble(
                (f"{idx + 1:>3} ", "dim"),
                (str(item.get("name", "")), "bold"),
                ("  ", ""),
                (_display_action(item), "cyan"),
            )
            options.append(Option(label, id=str(idx)))
        menu.set_options(options)
        if options:
            menu.highlighted = 0
            self.selected_index = self.filtered[0]
        else:
            self.selected_index = None

    def _refresh_details(self) -> None:
        status = "Custom rules" if using_custom_rules() else "Default rules"
        status += f" • {active_rules_path()}"
        self.query_one("#rules-status", Static).update(status)

        if self.selected_index is None:
            self.query_one("#rule-details", Static).update("No rule selected.")
            self._populate_edit_fields(None)
            return

        item = self.items[self.selected_index]
        details = [
            f"Name: {item.get('name', '')}",
            f"ID: {item.get('id', '')}",
            f"Action: {_display_action(item)}",
        ]
        analysis = item.get("analysis")
        if isinstance(analysis, list) and analysis:
            details.append("Reasons:")
            details.extend([f" • {reason}" for reason in analysis[:6]])
            if len(analysis) > 6:
                details.append(f" • … +{len(analysis) - 6} more")
        self.query_one("#rule-details", Static).update("\n".join(details))
        self._populate_edit_fields(item)

    def _populate_edit_fields(self, item: Optional[dict]) -> None:
        name_input = self.query_one("#rule-name", Input)
        id_input = self.query_one("#rule-id", Input)
        if not item:
            name_input.value = ""
            id_input.value = ""
            self.current_action = "keep"
            self.query_one("#rule-action", Static).update("Action: keep")
            self.mode = "add"
            return
        name_input.value = str(item.get("name", ""))
        id_input.value = str(item.get("id", ""))
        self.current_action = (
            normalize_action(str(item.get("action", "keep"))) or "keep"
        )
        self.query_one("#rule-action", Static).update(f"Action: {self.current_action}")
        self.mode = "edit"

    def _set_action(self, action: str) -> None:
        action_value = normalize_action(action)
        if not action_value:
            return
        self.current_action = action_value
        self.query_one("#rule-action", Static).update(f"Action: {action_value}")

    def _save_changes(self) -> None:
        name = self.query_one("#rule-name", Input).value.strip()
        item_id = self.query_one("#rule-id", Input).value.strip()
        action = normalize_action(self.current_action) or "keep"

        if not name:
            self.app.push_screen(MessageScreen("Name cannot be empty."))
            return

        if self.mode == "add":
            entry = {"name": name, "action": action}
            if item_id:
                entry["id"] = item_id
            self.items.append(entry)
        else:
            if self.selected_index is None:
                self.app.push_screen(MessageScreen("No rule selected."))
                return
            item = self.items[self.selected_index]
            item["name"] = name
            item["action"] = action
            if item_id:
                item["id"] = item_id
            else:
                item.pop("id", None)

        self.payload["items"] = self.items
        save_custom_rules(self.payload)
        self.app.push_screen(MessageScreen("Rules saved."))
        self._refresh_list()
        self._refresh_details()

    def _delete_selected(self) -> None:
        if self.selected_index is None:
            self.app.push_screen(MessageScreen("No rule selected."))
            return
        item = self.items.pop(self.selected_index)
        self.payload["items"] = self.items
        save_custom_rules(self.payload)
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

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "rules-search":
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
        elif button_id == "save":
            self._save_changes()
        elif button_id == "new":
            self._populate_edit_fields(None)
        elif button_id == "delete":
            self._delete_selected()
        elif button_id == "reset":
            self._reset_default()
        elif button_id == "back":
            self.app.pop_screen()
