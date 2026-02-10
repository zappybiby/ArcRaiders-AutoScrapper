from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from ...config import ProgressSettings
from ..common import MessageScreen, update_inline_filter
from .base import ProgressScreen
from .state import QuestEntry, normalize_quest_value, persist_progress_settings


class ReviewQuestsScreen(ProgressScreen):
    DEFAULT_CSS = """
    ReviewQuestsScreen {
        padding: 1 2;
    }

    #review-title {
        width: auto;
        text-style: bold;
        color: #7dd3fc;
    }

    #review-filterbar {
        height: auto;
        align: left middle;
        margin-bottom: 1;
    }

    #review-search {
        width: 1fr;
        margin-right: 1;
    }

    #review-sort {
        width: 20;
        text-style: bold;
    }

    #review-list-summary {
        margin-bottom: 1;
    }

    #review-list {
        height: 1fr;
    }

    #review-list > .option-list--option {
        padding: 0 0 1 0;
    }

    #review-list > .option-list--option-highlighted {
        text-style: bold;
    }

    #review-actions {
        margin-top: 1;
        height: auto;
    }
    """

    SORT_LABELS: dict[str, str] = {
        "name_asc": "Name A-Z",
        "trader": "Trader",
    }
    SORT_SEQUENCE: tuple[str, ...] = ("name_asc", "trader")

    BINDINGS = [
        *ProgressScreen.BINDINGS,
        Binding("up", "cursor_up", "up", priority=True),
        Binding("down", "cursor_down", "down", priority=True),
        Binding("enter", "toggle_completed", "Toggle done"),
        Binding("ctrl+f", "cycle_sort", "Sort", priority=True),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(
        self, quest_entries: List[QuestEntry], settings: ProgressSettings
    ) -> None:
        super().__init__()
        self.quest_entries = quest_entries
        self.completed = set(settings.completed_quests)
        self.active_read_only = set(settings.active_quests)
        self.original = ProgressSettings(
            all_quests_completed=settings.all_quests_completed,
            active_quests=list(settings.active_quests),
            completed_quests=list(settings.completed_quests),
            hideout_levels=dict(settings.hideout_levels),
            last_updated=settings.last_updated,
        )
        self.search_query = ""
        self.sort_mode: str = "name_asc"
        self.filtered: List[QuestEntry] = []

    def compose(self) -> ComposeResult:
        yield Static("Review Completed Quests", id="review-title")
        yield Static(
            "Active quests are read-only from setup. Press Enter to toggle completed.",
            classes="hint",
        )
        with Horizontal(id="review-filterbar"):
            yield Input(
                placeholder="Search quests... (name, id, trader)", id="review-search"
            )
            yield Button("Sort: Name A-Z", id="review-sort", variant="primary")
        yield Static(id="review-list-summary", classes="hint")
        yield OptionList(id="review-list")
        yield Static(id="review-count", classes="hint")
        with Horizontal(id="review-actions"):
            yield Button("Cancel", id="cancel")
            yield Button("Save", id="save", variant="primary")
        yield Static(
            "Type to search • Enter toggles completed • Up/Down move list • Ctrl+F cycles sort • Esc clears/back",
            classes="hint",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()
        self.query_one("#review-list", OptionList).focus()

    def _sorted_entries(self) -> List[QuestEntry]:
        entries = list(self.quest_entries)
        if self.sort_mode == "trader":
            entries.sort(
                key=lambda entry: (
                    normalize_quest_value(entry.trader),
                    normalize_quest_value(entry.name),
                    entry.sort_order,
                )
            )
            return entries
        entries.sort(
            key=lambda entry: (
                normalize_quest_value(entry.name),
                normalize_quest_value(entry.trader),
                entry.sort_order,
            )
        )
        return entries

    def _visible_entries(self) -> List[QuestEntry]:
        entries = self._sorted_entries()
        if not self.search_query:
            return entries
        normalized = normalize_quest_value(self.search_query)
        if not normalized:
            return entries
        matches: List[QuestEntry] = []
        for entry in entries:
            name_norm = normalize_quest_value(entry.name)
            trader_norm = normalize_quest_value(entry.trader)
            if (
                normalized in name_norm
                or normalized in trader_norm
                or normalized == entry.id
            ):
                matches.append(entry)
        return matches

    def _status_label(self, entry: QuestEntry) -> Text:
        if entry.id in self.completed:
            return Text("✓", style="green")
        if entry.id in self.active_read_only:
            return Text("A", style="cyan")
        return Text("·", style="dim")

    def _refresh(self) -> None:
        menu = self.query_one("#review-list", OptionList)
        prev_filtered = list(self.filtered)
        prev_highlight = menu.highlighted
        prev_id = None
        if prev_highlight is not None and 0 <= prev_highlight < len(prev_filtered):
            prev_id = prev_filtered[prev_highlight].id

        self.filtered = self._visible_entries()
        options: List[Option] = []
        for list_index, entry in enumerate(self.filtered):
            label = Text()
            label.append(f"{list_index + 1:>3} ", style="dim")
            label.append_text(self._status_label(entry))
            label.append(" ")
            label.append(entry.name, style="bold")
            label.append("  ")
            label.append(entry.trader, style="dim")
            options.append(Option(label, id=entry.id))
        had_focus = menu.has_focus
        menu.set_options(options)
        if options:
            if prev_id:
                for idx, entry in enumerate(self.filtered):
                    if entry.id == prev_id:
                        menu.highlighted = idx
                        break
                else:
                    menu.highlighted = 0
            else:
                menu.highlighted = 0
        if had_focus:
            menu.focus()

        sort_label = self.SORT_LABELS.get(self.sort_mode, self.sort_mode)
        self.query_one("#review-sort", Button).label = f"Sort: {sort_label}"
        filter_text = self.search_query if self.search_query.strip() else "all"
        self.query_one("#review-list-summary", Static).update(
            f"Showing {len(self.filtered)} of {len(self.quest_entries)} • "
            f"Sort: {sort_label} • Filter: {filter_text}"
        )
        count_text = (
            f"Completed: {len(self.completed)} • "
            f"Active (read-only): {len(self.active_read_only)} • "
            f"Showing: {len(self.filtered)} • "
            f"Total: {len(self.quest_entries)}"
        )
        self.query_one("#review-count", Static).update(count_text)

    def _move_highlight(self, delta: int) -> None:
        if not self.filtered:
            return
        menu = self.query_one("#review-list", OptionList)
        current = menu.highlighted if menu.highlighted is not None else 0
        new_index = max(0, min(len(self.filtered) - 1, current + delta))
        if new_index == current:
            return
        menu.highlighted = new_index

    def _selected_entry(self) -> Optional[QuestEntry]:
        menu = self.query_one("#review-list", OptionList)
        if menu.highlighted is None:
            return None
        if not self.filtered or menu.highlighted >= len(self.filtered):
            return None
        return self.filtered[menu.highlighted]

    def _toggle_completed(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        if entry.id in self.completed:
            self.completed.remove(entry.id)
        else:
            if entry.id in self.active_read_only:
                self.app.push_screen(
                    MessageScreen(
                        "This quest is marked active. Update active quests in setup first."
                    )
                )
                return
            self.completed.add(entry.id)
        self._refresh()

    def _save(self) -> None:
        active_quests = [
            quest_id
            for quest_id in self.original.active_quests
            if quest_id not in self.completed
        ]
        persist_progress_settings(
            all_quests_completed=(len(self.completed) == len(self.quest_entries)),
            active_quests=active_quests,
            completed_quests=list(self.completed),
            hideout_levels=self.original.hideout_levels,
        )
        self.app.pop_screen()
        self.app.push_screen(MessageScreen("Completed quest overrides saved."))

    def action_toggle_completed(self) -> None:
        self._toggle_completed()

    def action_cursor_up(self) -> None:
        self._move_highlight(-1)

    def action_cursor_down(self) -> None:
        self._move_highlight(1)

    def action_cycle_sort(self) -> None:
        current_index = self.SORT_SEQUENCE.index(self.sort_mode)
        next_index = (current_index + 1) % len(self.SORT_SEQUENCE)
        self.sort_mode = self.SORT_SEQUENCE[next_index]
        self._refresh()

    def action_save(self) -> None:
        self._save()

    def action_back(self) -> None:
        if self.search_query:
            self.search_query = ""
            self.query_one("#review-search", Input).value = ""
            self._refresh()
            return
        self.app.pop_screen()

    def on_key(self, event: events.Key) -> None:
        if isinstance(self.focused, Input):
            return
        if event.key in {"up", "down", "enter"}:
            return

        updated_text, consumed = update_inline_filter(event, self.search_query)
        if not consumed:
            return
        if updated_text != self.search_query:
            self.search_query = updated_text
            self.query_one("#review-search", Input).value = updated_text
            self._refresh()
        event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "review-search":
            return
        if event.value == self.search_query:
            return
        self.search_query = event.value
        self._refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "review-search":
            self._toggle_completed()

    def on_option_list_option_selected(self, _event: OptionList.OptionSelected) -> None:
        self._toggle_completed()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "review-sort":
            self.action_cycle_sort()
        elif event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "save":
            self._save()
