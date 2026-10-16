from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Literal, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from .common import (
    AppScreen,
    MessageScreen,
    RuleOptionList,
    rule_columns,
    update_inline_filter,
)
from ..items.rules_diff import RuleChange
from ..items.rules_store import (
    active_rules_path,
    clear_rule_override,
    legacy_rules_pending,
    load_base_rules,
    load_rules,
    normalize_action,
    reset_rules,
    rule_override_keys,
    rules_key,
    set_rule_action,
)


def _normalized_action(item: dict) -> Optional[str]:
    action = normalize_action(str(item.get("action", "")))
    if action:
        return action
    decisions = item.get("decision")
    if isinstance(decisions, list):
        for decision in decisions:
            if isinstance(decision, str):
                parsed = normalize_action(decision)
                if parsed:
                    return parsed
    return None


def _lookup_key(value: object) -> Optional[str]:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized:
            return normalized
    return None


def _should_hide_reason(reason: str) -> bool:
    return reason.strip().lower().startswith("override:")


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
        if event.key in {"escape", "ctrl+b"}:
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
        Binding(
            "up",
            "cursor_up",
            "List",
            key_display="Up/Down",
            priority=True,
        ),
        Binding("down", "cursor_down", "List", show=False, priority=True),
        Binding(
            "left",
            "previous_action",
            "Actions",
            key_display="Left/Right",
            priority=True,
        ),
        Binding("right", "next_action", "Actions", show=False, priority=True),
        Binding("tab", "focus_next_control", "Next focus", show=False, priority=True),
        Binding(
            "shift+tab",
            "focus_previous_control",
            "Previous focus",
            show=False,
            priority=True,
        ),
        Binding("ctrl+f", "cycle_sort", "Sort", priority=True),
    ]

    DEFAULT_CSS = """
    #rules-topbar {
        height: 1;
    }

    #rules-title {
        width: auto;
    }

    #rules-save-chip {
        width: 1fr;
        margin-left: 2;
        text-align: right;
        text-style: none;
        color: #94a3b8;
    }

    #rules-save-chip.is-saved { color: #86efac; }
    #rules-save-chip.is-saving { color: #fbbf24; }
    #rules-save-chip.is-error { color: #fca5a5; }
    #rules-save-chip.is-save-flash { text-style: bold reverse; }

    #rules-filterbar {
        height: 3;
    }

    #rules-search {
        width: 1fr;
        margin-right: 1;
    }

    #rules-sort {
        width: 16;
        min-width: 0;
    }

    #rule-selected {
        height: 1;
        text-style: bold;
    }

    #rule-reasons {
        height: auto;
    }

    #rules-actions, #action-buttons, #rule-management-actions {
        height: auto;
    }

    #action-buttons, #rule-management-actions {
        width: auto;
    }

    #rules-actions Button {
        width: auto;
        min-width: 0;
        padding: 0;
    }

    #rules-actions Button.is-current-action {
        text-style: bold reverse;
    }

    RulesScreen.is-adding #action-automatic,
    RulesScreen.is-adding #rule-management-actions,
    RulesScreen.is-adding #back,
    RulesScreen.is-adding #rules-details {
        display: none;
    }

    #new-rule-panel, #new-rule-actions {
        height: auto;
    }

    .is-hidden {
        display: none;
    }
    """

    SORT_LABELS: dict[str, str] = {
        "name_asc": "Name",
        "action": "Action",
        "modified": "Source",
    }
    SORT_SEQUENCE: tuple[str, ...] = ("name_asc", "action", "modified")
    ACTION_SORT_ORDER: dict[str, int] = {"keep": 0, "sell": 1, "recycle": 2}

    def __init__(self) -> None:
        super().__init__()
        self.payload: dict = {}
        self.items: list[dict] = []
        self.filtered: List[int] = []
        self.modified_map: dict[int, bool] = {}
        self.search_query = ""
        self.sort_mode: Literal["name_asc", "action", "modified"] = "name_asc"
        self.selected_index: Optional[int] = None
        self.mode: str = "edit"
        self.current_action: str = "keep"
        self._save_flash_timer = None
        self._reload_rules()

    def compose(self) -> ComposeResult:
        with Horizontal(id="rules-topbar", classes="rule-title"):
            yield Static("Review rules", id="rules-title")
            yield Static(id="rules-save-chip", classes="is-saved")
        with Horizontal(id="rules-filterbar"):
            yield Input(placeholder="Search items", id="rules-search")
            yield Button("Sort: Name", id="rules-sort")
        yield Static(id="rules-columns", classes="rule-columns")
        yield RuleOptionList(id="rules-list", classes="rule-list")
        with Vertical(id="rules-details", classes="rule-details"):
            yield Static(id="rule-selected")
            yield Static(id="rule-reasons")
        with Horizontal(id="rules-actions"):
            with Horizontal(id="action-buttons"):
                yield Button("Keep", id="action-keep")
                yield Button("Sell", id="action-sell")
                yield Button("Recycle", id="action-recycle")
                yield Button("Use recommendation", id="action-automatic")
            with Horizontal(id="rule-management-actions"):
                yield Button("New", id="new-rule")
                yield Button("Delete", id="delete-rule")
                yield Button("Reset", id="reset-rules", variant="error")
            yield Button("Back", id="back")
        with Vertical(id="new-rule-panel", classes="is-hidden"):
            yield Input(placeholder="Item name", id="new-rule-name")
            with Horizontal(id="new-rule-actions"):
                yield Button("Add rule", id="add-rule", variant="primary")
                yield Button("Cancel", id="cancel-add")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_list()
        self._refresh_details()
        self._set_save_chip(self._last_saved_label(), state="saved")
        self.query_one("#rules-list", OptionList).focus()
        if legacy_rules_pending():
            from .rules_migration import RulesMigrationScreen

            self.app.push_screen(RulesMigrationScreen(), self._handle_migration)

    def _handle_migration(self, applied: bool) -> None:
        if not applied:
            self.app.pop_screen()
            return
        self._reload_rules()
        self._refresh_list()
        self._refresh_details()
        self._set_saved_with_timestamp()

    def on_resize(self, _event: events.Resize) -> None:
        if not self.is_mounted:
            return
        self._refresh_list(preserve_scroll=True)
        self._refresh_details()

    def _last_saved_label(self) -> str:
        try:
            rules_path = active_rules_path()
            if rules_path.exists():
                timestamp = datetime.fromtimestamp(rules_path.stat().st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                return f"Last saved: {timestamp}"
        except OSError:
            pass
        return "Last saved: unknown"

    def _reload_rules(self) -> None:
        selected_key = None
        selected_name = None
        if self.selected_index is not None and self.selected_index < len(self.items):
            selected_item = self.items[self.selected_index]
            selected_key = rules_key(selected_item)
            selected_name = _lookup_key(selected_item.get("name"))
        self.payload = load_rules()
        self.override_keys = rule_override_keys()
        base_items = list(load_base_rules().get("items", []))
        (
            self.base_items_by_id,
            self.base_items_by_name,
        ) = self._build_base_item_indexes(base_items)
        self.base_rule_keys_by_name: dict[str, set[str]] = {}
        for item in base_items:
            name = _lookup_key(item.get("name"))
            if name:
                self.base_rule_keys_by_name.setdefault(name, set()).add(rules_key(item))

        visible_by_name: dict[str, dict] = {}
        for item in self.payload.get("items", []):
            name = _lookup_key(item.get("name"))
            if not name:
                continue
            # The scanner can only distinguish names and uses the last valid rule.
            if name not in visible_by_name or _normalized_action(item) is not None:
                visible_by_name[name] = dict(item)
        for item in base_items:
            name = _lookup_key(item.get("name"))
            if name and name not in visible_by_name and self._is_modified(item):
                skipped = {**item, "action": None}
                skipped.pop("decision", None)
                visible_by_name[name] = skipped
        for name, item in visible_by_name.items():
            if len(self.base_rule_keys_by_name.get(name, ())) > 1:
                item.pop("id", None)
        self.items = list(visible_by_name.values())
        self.selected_index = next(
            (
                index
                for index, item in enumerate(self.items)
                if rules_key(item) == selected_key
            ),
            None,
        )
        if self.selected_index is None and selected_name:
            self.selected_index = next(
                (
                    index
                    for index, item in enumerate(self.items)
                    if _lookup_key(item.get("name")) == selected_name
                ),
                None,
            )

    def _build_base_item_indexes(
        self, items: list[object]
    ) -> tuple[dict[str, dict], dict[str, dict]]:
        by_id: dict[str, dict] = {}
        by_name: dict[str, dict] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = _lookup_key(item.get("id"))
            if item_id:
                by_id[item_id] = item
            name = _lookup_key(item.get("name"))
            if name:
                by_name[name] = item
        return by_id, by_name

    def _base_item_for_item(self, item: dict) -> Optional[dict]:
        item_id = _lookup_key(item.get("id"))
        if item_id and item_id in self.base_items_by_id:
            return self.base_items_by_id[item_id]
        name = _lookup_key(item.get("name"))
        if name and name in self.base_items_by_name:
            return self.base_items_by_name[name]
        return None

    def _base_reason_lines(self, item: dict) -> tuple[list[str], bool]:
        base_item = self._base_item_for_item(item)
        if base_item is None:
            return ([], False)

        base_analysis = base_item.get("analysis")
        if not isinstance(base_analysis, list):
            return ([], True)

        lines = [
            reason.strip()
            for reason in base_analysis
            if isinstance(reason, str)
            and reason.strip()
            and not _should_hide_reason(reason)
        ]
        return (lines, True)

    def _is_modified(self, item: dict) -> bool:
        name = _lookup_key(item.get("name"))
        return bool(
            (
                {rules_key(item), rules_key({"name": item.get("name")})}
                | self.base_rule_keys_by_name.get(name, set())
            )
            & self.override_keys
        )

    def _is_modified_index(self, index: int) -> bool:
        return self.modified_map.get(index, False)

    def _refresh_modified_map(self) -> None:
        self.modified_map = {
            idx: self._is_modified(item) for idx, item in enumerate(self.items)
        }

    def _sort_indices(self, indices: List[int]) -> List[int]:
        if self.sort_mode == "action":
            return sorted(
                indices,
                key=lambda idx: (
                    self.ACTION_SORT_ORDER.get(
                        _normalized_action(self.items[idx]) or "", 99
                    ),
                    str(self.items[idx].get("name", "")).lower(),
                ),
            )
        if self.sort_mode == "modified":
            return sorted(
                indices,
                key=lambda idx: (
                    0 if self._is_modified_index(idx) else 1,
                    str(self.items[idx].get("name", "")).lower(),
                ),
            )
        return sorted(
            indices, key=lambda idx: str(self.items[idx].get("name", "")).lower()
        )

    def _refresh_list(self, *, preserve_scroll: bool = False) -> None:
        previous_selection = self.selected_index
        menu = self.query_one("#rules-list", OptionList)
        previous_scroll_y = menu.scroll_y if preserve_scroll else None
        width = menu.scrollable_content_region.width - 2
        self.query_one("#rules-columns", Static).update(
            rule_columns("Item", "Current Action", "Rule Source", width)
        )
        self._refresh_modified_map()
        filtered_indices = _filter_indices(self.items, self.search_query)
        self.filtered = self._sort_indices(filtered_indices)
        options = []
        for item_index in self.filtered:
            item = self.items[item_index]
            custom = self._is_modified_index(item_index)
            label = rule_columns(
                str(item.get("name", "")),
                (_normalized_action(item) or "skip").upper(),
                "Custom" if custom else "Recommended",
                width,
                custom=custom,
            )
            options.append(Option(label, id=str(item_index)))
        menu.set_options(options)

        if options:
            if previous_selection in self.filtered:
                highlighted = self.filtered.index(previous_selection)
            else:
                highlighted = 0
            menu.highlighted = highlighted
            self.selected_index = self.filtered[highlighted]
            if self.mode != "add":
                self.current_action = (
                    _normalized_action(self.items[self.selected_index]) or "skip"
                )
        else:
            self.selected_index = None
            if self.mode != "add":
                self.current_action = "keep"

        if previous_scroll_y is not None:
            menu.scroll_to(
                y=previous_scroll_y, animate=False, force=True, immediate=True
            )

        self._refresh_action_buttons()
        sort_label = self.SORT_LABELS[self.sort_mode]
        self.query_one("#rules-sort", Button).label = f"Sort: {sort_label}"

    def _set_add_mode(self, enabled: bool) -> None:
        self.set_class(enabled, "is-adding")
        panel = self.query_one("#new-rule-panel", Vertical)
        if enabled:
            panel.remove_class("is-hidden")
        else:
            panel.add_class("is-hidden")

    def _refresh_details(self) -> None:
        self._set_add_mode(self.mode == "add")
        title = self.query_one("#rule-selected", Static)
        reasons = self.query_one("#rule-reasons", Static)

        if self.mode == "add":
            title.update("Create New Rule")
            reasons.update("")
            self._refresh_action_buttons()
            return

        if self.selected_index is None:
            title.update("No rule selected")
            if self.search_query:
                reasons.update("No matching rules for this filter.")
            else:
                reasons.update("")
            self._refresh_action_buttons()
            return

        item = self.items[self.selected_index]
        name = str(item.get("name", ""))
        base_item = self._base_item_for_item(item)
        heading = name
        if base_item is not None:
            recommendation = (_normalized_action(base_item) or "skip").upper()
            heading += f" · Recommended: {recommendation}"
        title.update(Text(heading, style="bold"))
        self.current_action = _normalized_action(item) or "skip"
        reason_lines, has_base_rule = self._base_reason_lines(item)
        if not reason_lines and has_base_rule:
            reason_lines = ["No reasons recorded for this recommendation."]
        reasons.update(Text("\n".join(reason_lines)))
        self._refresh_action_buttons()

    def _set_save_chip(
        self, text: str, *, state: Literal["saved", "saving", "error"]
    ) -> None:
        save_chip = self.query_one("#rules-save-chip", Static)
        save_chip.remove_class("is-saved")
        save_chip.remove_class("is-saving")
        save_chip.remove_class("is-error")
        save_chip.remove_class("is-save-flash")
        if state != "saved" and self._save_flash_timer is not None:
            self._save_flash_timer.stop()
            self._save_flash_timer = None
        save_chip.add_class(f"is-{state}")
        save_chip.update(text)

    def _set_saved_with_timestamp(self) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._set_save_chip(f"Last saved: {timestamp}", state="saved")
        self._flash_save_chip()

    def _flash_save_chip(self) -> None:
        save_chip = self.query_one("#rules-save-chip", Static)
        save_chip.add_class("is-save-flash")
        if self._save_flash_timer is not None:
            self._save_flash_timer.stop()
        self._save_flash_timer = self.set_timer(0.9, self._clear_save_chip_flash)

    def _clear_save_chip_flash(self) -> None:
        self.query_one("#rules-save-chip", Static).remove_class("is-save-flash")
        self._save_flash_timer = None

    def _refresh_action_buttons(self) -> None:
        item = (
            self.items[self.selected_index] if self.selected_index is not None else None
        )
        is_custom = item is not None and self._is_modified(item)
        has_base = item is not None and self._base_item_for_item(item) is not None
        button_ids = {
            "keep": "action-keep",
            "sell": "action-sell",
            "recycle": "action-recycle",
        }
        for action, button_id in button_ids.items():
            button = self.query_one(f"#{button_id}", Button)
            button.disabled = self.mode != "add" and item is None
            if action == self.current_action and (self.mode == "add" or is_custom):
                button.add_class("is-current-action")
            else:
                button.remove_class("is-current-action")
        automatic = self.query_one("#action-automatic", Button)
        automatic.disabled = self.mode == "add" or not has_base
        automatic.set_class(
            self.mode != "add" and item is not None and not is_custom,
            "is-current-action",
        )
        delete = self.query_one("#delete-rule", Button)
        delete.label = "Skip" if has_base else "Delete"
        delete.disabled = self.mode == "add" or item is None

    def _save_change(self, operation: Callable[[], None]) -> bool:
        self._set_save_chip("Saving...", state="saving")
        try:
            operation()
            self._reload_rules()
        except Exception as exc:
            self._set_save_chip("Save failed", state="error")
            self.app.push_screen(MessageScreen(f"Failed to save rules: {exc}"))
            return False
        self._set_saved_with_timestamp()
        return True

    def _set_action(self, action: str) -> None:
        action_value = normalize_action(action)
        if not action_value:
            return
        if self.mode == "add":
            if self.current_action == action_value:
                return
            self.current_action = action_value
            self._refresh_action_buttons()
            self._refresh_details()
            return

        if self.selected_index is None:
            return

        item = self.items[self.selected_index]
        if not self._save_change(lambda: set_rule_action(item, action_value)):
            return
        self.current_action = action_value
        self._refresh_list(preserve_scroll=True)
        self._refresh_details()

    def _set_automatic(self) -> None:
        if self.mode == "add" or self.selected_index is None:
            return
        item = self.items[self.selected_index]
        if self._save_change(lambda: clear_rule_override(item)):
            self._refresh_list(preserve_scroll=True)
            self._refresh_details()

    def _add_rule(self) -> None:
        name = self.query_one("#new-rule-name", Input).value.strip()
        if not name:
            self.app.push_screen(MessageScreen("Enter a name before adding a rule."))
            self.query_one("#new-rule-name", Input).focus()
            return
        normalized_name = name.casefold()
        if any(
            str(item.get("name", "")).strip().casefold() == normalized_name
            for item in self.items
        ):
            self.app.push_screen(MessageScreen(f"A rule for '{name}' already exists."))
            return
        action = normalize_action(self.current_action) or "keep"
        item = {"name": name}
        if not self._save_change(lambda: set_rule_action(item, action)):
            return
        self.selected_index = next(
            index
            for index, saved in enumerate(self.items)
            if rules_key(saved) == rules_key(item)
        )
        self.mode = "edit"
        self.search_query = name
        self.query_one("#rules-search", Input).value = name
        self._refresh_list()
        self._refresh_details()
        self.query_one("#rules-search", Input).focus()

    def _confirm_reset_default(self) -> None:
        self.app.push_screen(ConfirmResetRulesScreen(), self._handle_reset_confirmation)

    def _handle_reset_confirmation(self, confirmed: bool) -> None:
        if confirmed:
            self._reset_default()

    def _delete_selected(self) -> None:
        if self.selected_index is None:
            self.app.push_screen(MessageScreen("No rule selected."))
            return
        item = self.items[self.selected_index]
        if not self._save_change(lambda: set_rule_action(item, None)):
            return
        self._refresh_list()
        self._refresh_details()

    def _reset_default(self) -> None:
        if not self._save_change(reset_rules):
            return
        self.mode = "edit"
        self.current_action = "keep"
        self._set_saved_with_timestamp()
        self._refresh_list()
        self._refresh_details()
        self.app.push_screen(MessageScreen("Custom rules removed. Defaults restored."))

    def _is_text_input_focused(self) -> bool:
        focused = self.focused
        return isinstance(focused, Input) and focused.id == "new-rule-name"

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
        if self._is_text_input_focused():
            return
        self._move_highlight(-1)

    def action_cursor_down(self) -> None:
        if self._is_text_input_focused():
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
        if self._is_text_input_focused():
            return
        self._cycle_action(-1)

    def action_next_action(self) -> None:
        if self._is_text_input_focused():
            return
        self._cycle_action(1)

    def action_focus_next_control(self) -> None:
        self.focus_next()

    def action_focus_previous_control(self) -> None:
        self.focus_previous()

    def action_new_rule(self) -> None:
        if self.mode == "add":
            self._add_rule()
            return
        self.mode = "add"
        self.current_action = "keep"
        self.query_one("#new-rule-name", Input).value = ""
        self._refresh_action_buttons()
        self._refresh_details()
        self.query_one("#new-rule-name", Input).focus()

    def action_delete_rule(self) -> None:
        self._delete_selected()

    def action_reset_rules(self) -> None:
        self._confirm_reset_default()

    def action_focus_search(self) -> None:
        self.query_one("#rules-search", Input).focus()

    def action_cycle_sort(self) -> None:
        current_index = self.SORT_SEQUENCE.index(self.sort_mode)
        next_index = (current_index + 1) % len(self.SORT_SEQUENCE)
        self._set_sort_mode(self.SORT_SEQUENCE[next_index])

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_key(self, event: events.Key) -> None:
        if isinstance(self.focused, Input):
            return
        updated_query, consumed = update_inline_filter(event, self.search_query)
        if not consumed:
            return
        self.search_query = updated_query
        search_input = self.query_one("#rules-search", Input)
        search_input.value = updated_query
        search_input.focus()
        event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "rules-search":
            if event.value == self.search_query:
                return
            self.search_query = event.value
            self._refresh_list()
            self._refresh_details()
            return
        if event.input.id == "new-rule-name":
            return

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "new-rule-name":
            self._add_rule()

    def _set_sort_mode(self, mode: str) -> None:
        if mode not in self.SORT_LABELS:
            return
        if mode == self.sort_mode:
            return
        self.sort_mode = mode
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
        if event.option_id is None or self.mode == "add":
            return
        try:
            self.selected_index = int(event.option_id)
        except ValueError:
            return
        self._refresh_details()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "action-keep":
            self._set_action("keep")
        elif button_id == "action-sell":
            self._set_action("sell")
        elif button_id == "action-recycle":
            self._set_action("recycle")
        elif button_id == "action-automatic":
            self._set_automatic()
        elif button_id == "add-rule":
            self._add_rule()
        elif button_id == "cancel-add":
            self.mode = "edit"
            self._refresh_list(preserve_scroll=True)
            self._refresh_details()
            self.query_one("#rules-search", Input).focus()
        elif button_id == "new-rule":
            self.action_new_rule()
        elif button_id == "delete-rule":
            self.action_delete_rule()
        elif button_id == "reset-rules":
            self.action_reset_rules()
        elif button_id == "rules-sort":
            self.action_cycle_sort()
        elif button_id == "back":
            self.action_back()


class RulesChangesScreen(AppScreen):
    BINDINGS = [*AppScreen.BINDINGS]

    DEFAULT_CSS = """
    #changes-actions {
        height: auto;
    }
    """

    def __init__(self, changes: List[RuleChange]) -> None:
        super().__init__()
        self.changes = list(changes)
        self.filtered: List[int] = []
        self.search_query = ""
        self.selected_index: Optional[int] = None

    def compose(self) -> ComposeResult:
        yield Static("Rule changes", classes="rule-title")
        yield Input(placeholder="Search items", id="changes-search")
        yield Static(id="changes-columns", classes="rule-columns")
        yield RuleOptionList(id="changes-list", classes="rule-list")
        yield Static(id="changes-detail-body", classes="rule-details")
        with Horizontal(id="changes-actions"):
            yield Button("Done", id="done", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_list()
        if self.changes:
            self.query_one("#changes-list", OptionList).focus()

    def on_resize(self, _event: events.Resize) -> None:
        if self.is_mounted:
            self._refresh_list()

    def action_focus_search(self) -> None:
        self.query_one("#changes-search", Input).focus()

    def _filter_indices(self) -> List[int]:
        query = self.search_query.casefold().strip()
        return [
            index
            for index, change in enumerate(self.changes)
            if not query
            or query in change.name.casefold()
            or query in change.item_id.casefold()
        ]

    def _refresh_list(self) -> None:
        self.filtered = self._filter_indices()
        menu = self.query_one("#changes-list", OptionList)
        width = menu.scrollable_content_region.width - 2
        self.query_one("#changes-columns", Static).update(
            rule_columns("Item", "Default Action", "Current Action", width)
        )
        menu.set_options(
            Option(
                rule_columns(
                    self.changes[index].name,
                    self.changes[index].before_action.upper(),
                    self.changes[index].after_action.upper(),
                    width,
                ),
                id=str(index),
            )
            for index in self.filtered
        )
        if self.filtered:
            highlighted = (
                self.filtered.index(self.selected_index)
                if self.selected_index in self.filtered
                else 0
            )
            menu.highlighted = highlighted
            self.selected_index = self.filtered[highlighted]
        else:
            self.selected_index = None
        self._refresh_details()

    def _refresh_details(self) -> None:
        detail = self.query_one("#changes-detail-body", Static)
        if self.selected_index is None:
            detail.update("No matching items." if self.changes else "No changes.")
            return
        change = self.changes[self.selected_index]
        reasons = [
            reason for reason in change.reasons if not _should_hide_reason(reason)
        ]
        detail.update(
            Text.assemble(
                (f"{change.name}\n", "bold"),
                "\n".join(reasons) or "No reasons recorded for this recommendation.",
            )
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "changes-search":
            self.search_query = event.value
            self._refresh_list()

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option_id is not None:
            self.selected_index = int(event.option_id)
            self._refresh_details()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "done":
            self.app.pop_screen()
