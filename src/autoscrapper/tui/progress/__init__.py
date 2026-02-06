from __future__ import annotations

from typing import List

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Button, Footer, OptionList, Static
from textual.widgets.option_list import Option

from ...config import has_saved_progress, load_progress_settings
from ...core.item_actions import ITEM_RULES_CUSTOM_PATH
from ...items.rules_diff import collect_rule_changes
from ...items.rules_store import DEFAULT_RULES_PATH, load_rules
from ...progress.data_loader import load_game_data
from ...progress.rules_generator import generate_rules_from_active, write_rules
from ..common import MessageScreen, update_inline_filter
from ..rules import RulesChangesScreen
from .base import ProgressScreen, pop_progress_stack
from .review import ReviewQuestsScreen
from .state import (
    HideoutModule,
    ProgressWizardState,
    QuestEntry,
    build_hideout_modules,
    build_quest_entries,
    build_wizard_state,
    compute_completed_quests,
    normalize_quest_value,
    persist_progress_settings,
    save_workshop_levels,
)


class ProgressIntroScreen(ProgressScreen):
    DEFAULT_CSS = """
    ProgressIntroScreen {
        padding: 1 2;
    }

    #intro-actions {
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(self, state: ProgressWizardState) -> None:
        super().__init__()
        self.state = state

    BINDINGS = [
        *ProgressScreen.BINDINGS,
        Binding("ctrl+n", "next", "Continue"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("Progress Setup", classes="menu-title")
        yield Static(
            "Enter your currently active quests. Completed quests are inferred automatically.",
            classes="hint",
        )
        yield Static(
            "Do you currently have any active quests?",
            classes="section-title",
        )
        yield OptionList(
            Option("No active quests (all quests completed)", id="yes"),
            Option("Yes, I have active quests now", id="no"),
            id="all-quests",
        )
        with Horizontal(id="intro-actions"):
            yield Button("Next", id="next", variant="primary")
            yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        menu = self.query_one(OptionList)
        menu.highlighted = 0 if self.state.all_quests_completed else 1

    def _next(self) -> None:
        menu = self.query_one(OptionList)
        index = menu.highlighted if menu.highlighted is not None else 0
        self.state.all_quests_completed = index == 0
        if self.state.all_quests_completed:
            self.state.active_ids.clear()
            self.app.push_screen(WorkshopLevelsScreen(self.state, wizard_mode=True))
        else:
            self.app.push_screen(ActiveQuestsScreen(self.state))

    def action_next(self) -> None:
        self._next()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next":
            self._next()
        elif event.button.id == "back":
            self.app.pop_screen()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id in {"yes", "no"}:
            self._next()


class ActiveQuestsScreen(ProgressScreen):
    DEFAULT_CSS = """
    ActiveQuestsScreen {
        padding: 1 2;
    }

    #quest-list {
        height: 1fr;
    }

    #quest-actions {
        margin-top: 1;
        height: auto;
    }
    """

    BINDINGS = [
        *ProgressScreen.BINDINGS,
        ("space", "toggle", "Toggle quest"),
        ("enter", "toggle", "Toggle quest"),
        ("ctrl+n", "next", "Continue"),
    ]

    def __init__(self, state: ProgressWizardState) -> None:
        super().__init__()
        self.state = state
        self.filter_text = ""
        self.filtered: List[QuestEntry] = []

    def compose(self) -> ComposeResult:
        yield Static("Select Active Quests", classes="menu-title")
        yield Static(
            "Select quests currently active in-game. Completed quests will be inferred.",
            classes="hint",
        )
        yield Static(id="quest-filter", classes="hint")
        yield OptionList(id="quest-list")
        yield Static(id="quest-count", classes="hint")
        with Horizontal(id="quest-actions"):
            yield Button("Back", id="back")
            yield Button("Continue", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_options()
        self._focus_list()

    def _focus_list(self) -> None:
        self.query_one("#quest-list", OptionList).focus()

    def _filtered_entries(self) -> List[QuestEntry]:
        if not self.filter_text:
            return list(self.state.quest_entries)
        normalized = normalize_quest_value(self.filter_text)
        if not normalized:
            return list(self.state.quest_entries)
        results: List[QuestEntry] = []
        for entry in self.state.quest_entries:
            name_norm = normalize_quest_value(entry.name)
            if normalized in name_norm or normalized == entry.id:
                results.append(entry)
        return results

    def _option_label(self, entry: QuestEntry) -> Text:
        selected = entry.id in self.state.active_ids
        marker = ("[x] ", "bold green") if selected else ("[ ] ", "dim")
        text = Text.assemble(
            marker, (entry.name, "bold"), ("  ", ""), (entry.trader, "dim")
        )
        return text

    def _refresh_options(self) -> None:
        menu = self.query_one("#quest-list", OptionList)
        prev_filtered = list(self.filtered)
        prev_highlight = menu.highlighted
        prev_id = None
        if prev_highlight is not None and 0 <= prev_highlight < len(prev_filtered):
            prev_id = prev_filtered[prev_highlight].id

        self.filtered = self._filtered_entries()
        options = [
            Option(self._option_label(entry), id=entry.id) for entry in self.filtered
        ]
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
        filter_text = self.filter_text or "all"
        self.query_one("#quest-filter", Static).update(
            f"Type to filter by name or id • Backspace deletes • Esc clears/back • "
            f"Filter: {filter_text} ({len(self.filtered)} matches)"
        )
        count_text = f"Selected: {len(self.state.active_ids)} • Total: {len(self.state.quest_entries)}"
        self.query_one("#quest-count", Static).update(count_text)

    def _toggle_selected(self) -> None:
        menu = self.query_one("#quest-list", OptionList)
        if not self.filtered or menu.highlighted is None:
            return
        entry = self.filtered[menu.highlighted]
        if entry.id in self.state.active_ids:
            self.state.active_ids.remove(entry.id)
        else:
            self.state.active_ids.add(entry.id)
        self._refresh_options()

    def on_option_list_option_selected(self, _event: OptionList.OptionSelected) -> None:
        self._toggle_selected()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "next":
            self._next()

    def _next(self) -> None:
        if not self.state.active_ids:
            self.app.push_screen(MessageScreen("Select at least one active quest."))
            return
        self.app.push_screen(WorkshopLevelsScreen(self.state, wizard_mode=True))

    def action_toggle(self) -> None:
        self._toggle_selected()

    def action_next(self) -> None:
        self._next()

    def action_back(self) -> None:
        if self.filter_text:
            self.filter_text = ""
            self._refresh_options()
            return
        self.app.pop_screen()

    def on_key(self, event: events.Key) -> None:
        if event.key in {"space", "enter"}:
            return

        updated_text, consumed = update_inline_filter(event, self.filter_text)
        if not consumed:
            return
        if updated_text != self.filter_text:
            self.filter_text = updated_text
            self._refresh_options()
        event.stop()


class WorkshopLevelsScreen(ProgressScreen):
    DEFAULT_CSS = """
    WorkshopLevelsScreen {
        padding: 1 2;
    }

    #workshop-list {
        height: 1fr;
    }

    #workshop-actions {
        margin-top: 1;
        height: auto;
    }
    """

    BINDINGS = [
        *ProgressScreen.BINDINGS,
        ("ctrl+n", "next", "Continue"),
    ]

    def __init__(self, state: ProgressWizardState, *, wizard_mode: bool) -> None:
        super().__init__()
        self.state = state
        self.wizard_mode = wizard_mode
        self.entries = state.hideout_modules
        self.levels = dict(state.hideout_levels)

    def compose(self) -> ComposeResult:
        yield Static("Workshop Levels", classes="menu-title")
        yield Static(
            "Use left/right or number keys to adjust the selected workshop.",
            classes="hint",
        )
        yield OptionList(id="workshop-list")
        yield Static(id="workshop-count", classes="hint")
        with Horizontal(id="workshop-actions"):
            yield Button("Back", id="back")
            yield Button(
                "Next" if self.wizard_mode else "Save",
                id="next" if self.wizard_mode else "save",
                variant="primary",
            )
        yield Footer()

    def on_mount(self) -> None:
        if not self.entries:
            self.app.push_screen(MessageScreen("No workshop modules found."))
            return
        for entry in self.entries:
            if entry.id not in self.levels:
                self.levels[entry.id] = 0
        self._refresh_options()

    def _option_label(self, entry: HideoutModule) -> Text:
        level = self.levels.get(entry.id, 0)
        return Text.assemble(
            (entry.name, "bold"),
            ("  ", ""),
            (f"Level {level}/{entry.max_level}", "cyan"),
        )

    def _refresh_options(self) -> None:
        menu = self.query_one("#workshop-list", OptionList)
        prev_highlight = menu.highlighted
        options = [
            Option(self._option_label(entry), id=entry.id) for entry in self.entries
        ]
        menu.set_options(options)
        if options:
            if prev_highlight is None:
                menu.highlighted = 0
            else:
                menu.highlighted = min(prev_highlight, len(options) - 1)
        count_text = f"Workshops set: {len(self.levels)}"
        self.query_one("#workshop-count", Static).update(count_text)

    def _adjust_selected(self, delta: int) -> None:
        menu = self.query_one("#workshop-list", OptionList)
        if menu.highlighted is None:
            return
        entry = self.entries[menu.highlighted]
        current = self.levels.get(entry.id, 0)
        new_value = max(0, min(entry.max_level, current + delta))
        self.levels[entry.id] = new_value
        self._refresh_options()

    def _set_selected(self, value: int) -> None:
        menu = self.query_one("#workshop-list", OptionList)
        if menu.highlighted is None:
            return
        entry = self.entries[menu.highlighted]
        if 0 <= value <= entry.max_level:
            self.levels[entry.id] = value
            self._refresh_options()

    def on_key(self, event: events.Key) -> None:
        if event.key == "left":
            self._adjust_selected(-1)
            event.stop()
        elif event.key == "right":
            self._adjust_selected(1)
            event.stop()
        elif event.key and event.key.isdigit():
            self._set_selected(int(event.key))
            event.stop()
        elif event.key in {"m", "M"}:
            menu = self.query_one("#workshop-list", OptionList)
            if menu.highlighted is None:
                return
            entry = self.entries[menu.highlighted]
            self.levels[entry.id] = entry.max_level
            self._refresh_options()
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id in {"next", "save"}:
            self._commit_levels()

    def _commit_levels(self) -> None:
        self.state.hideout_levels = dict(self.levels)
        if self.wizard_mode:
            self.app.push_screen(ProgressSummaryScreen(self.state))
        else:
            save_workshop_levels(self.state.hideout_levels)
            self.app.pop_screen()
            self.app.push_screen(MessageScreen("Workshop levels saved."))

    def action_next(self) -> None:
        self._commit_levels()

    def action_back(self) -> None:
        self.app.pop_screen()


class ProgressSummaryScreen(ProgressScreen):
    DEFAULT_CSS = """
    ProgressSummaryScreen {
        padding: 1 2;
    }

    #summary-actions {
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(self, state: ProgressWizardState) -> None:
        super().__init__()
        self.state = state
        self.inferred_completed_ids: list[str] = []

    BINDINGS = [
        *ProgressScreen.BINDINGS,
        Binding("ctrl+s", "save", "Generate"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("Review & Generate Rules", classes="menu-title")
        yield Static(id="summary-body")
        with Horizontal(id="summary-actions"):
            yield Button("Back", id="back")
            yield Button("Save & Generate", id="save", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._render_summary()

    def _render_summary(self) -> None:
        active_count = len(self.state.active_ids)
        workshop_count = len(self.state.hideout_levels)
        requirement_entries = [
            entry for entry in self.state.quest_entries if entry.has_requirements
        ]
        lines = [
            f"Active quests selected: {active_count}",
            f"Workshops configured: {workshop_count}",
            "",
            "Completed quests are inferred from your active quests using quest order and the quest graph.",
        ]
        try:
            if self.state.all_quests_completed:
                self.inferred_completed_ids = [
                    entry.id for entry in self.state.quest_entries
                ]
            else:
                self.inferred_completed_ids = compute_completed_quests(
                    list(self.state.active_ids)
                )
        except ValueError as exc:
            self.inferred_completed_ids = []
            lines.extend(["", f"Could not infer completed quests: {exc}"])
            self.query_one("#summary-body", Static).update("\n".join(lines))
            return

        completed_set = set(self.inferred_completed_ids)
        inferred_requirement_completed = [
            entry.name for entry in requirement_entries if entry.id in completed_set
        ]
        inferred_requirement_remaining = [
            entry.name for entry in requirement_entries if entry.id not in completed_set
        ]
        lines.extend(
            [
                "",
                f"Inferred completed quests: {len(self.inferred_completed_ids)} / {len(self.state.quest_entries)}",
                f"Requirement quests completed: {len(inferred_requirement_completed)} / {len(requirement_entries)}",
            ]
        )
        if inferred_requirement_remaining:
            lines.append("Requirement quests still incomplete:")
            lines.extend(f"- {name}" for name in inferred_requirement_remaining)
        else:
            lines.append("All requirement quests are inferred completed.")
        self.query_one("#summary-body", Static).update("\n".join(lines))

    def _save(self) -> None:
        try:
            completed_ids = list(
                self.inferred_completed_ids
            ) or compute_completed_quests(list(self.state.active_ids))
        except ValueError as exc:
            self.app.push_screen(MessageScreen(str(exc)))
            return

        progress_settings = persist_progress_settings(
            all_quests_completed=(len(completed_ids) == len(self.state.quest_entries)),
            active_quests=list(self.state.active_ids),
            completed_quests=completed_ids,
            hideout_levels=self.state.hideout_levels,
        )

        try:
            output = generate_rules_from_active(
                progress_settings.active_quests,
                progress_settings.hideout_levels,
                all_quests_completed=progress_settings.all_quests_completed,
                completed_quests_override=progress_settings.completed_quests,
            )
        except ValueError as exc:
            self.app.push_screen(MessageScreen(str(exc)))
            return

        write_rules(output, ITEM_RULES_CUSTOM_PATH)
        item_count = output.get("metadata", {}).get("itemCount", 0)
        default_payload = load_rules(DEFAULT_RULES_PATH)
        changes = collect_rule_changes(default_payload, output)
        default_items = default_payload.get("items")
        default_count = len(default_items) if isinstance(default_items, list) else 0
        pop_progress_stack(self.app)
        self.app.push_screen(
            RulesChangesScreen(
                changes,
                item_count=item_count,
                default_count=default_count,
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "save":
            self._save()

    def action_save(self) -> None:
        self._save()


def launch_progress_wizard(app) -> None:
    try:
        state = build_wizard_state()
    except FileNotFoundError as exc:
        app.push_screen(MessageScreen(str(exc)))
        return
    app.push_screen(ProgressIntroScreen(state))


def launch_review_quests(app) -> None:
    try:
        game_data = load_game_data()
    except FileNotFoundError as exc:
        app.push_screen(MessageScreen(str(exc)))
        return
    settings = load_progress_settings()
    if not has_saved_progress(settings):
        app.push_screen(MessageScreen("No saved progress found."))
        return
    quest_entries = build_quest_entries(game_data.quests)
    app.push_screen(ReviewQuestsScreen(quest_entries, settings))


def launch_edit_workshops(app) -> None:
    try:
        game_data = load_game_data()
    except FileNotFoundError as exc:
        app.push_screen(MessageScreen(str(exc)))
        return
    settings = load_progress_settings()
    state = ProgressWizardState(
        all_quests_completed=settings.all_quests_completed,
        active_ids=set(settings.active_quests),
        hideout_levels=dict(settings.hideout_levels),
        quest_entries=[],
        hideout_modules=build_hideout_modules(game_data.hideout_modules),
    )
    app.push_screen(WorkshopLevelsScreen(state, wizard_mode=False))


def launch_generate_rules(app) -> None:
    settings = load_progress_settings()
    if not has_saved_progress(settings):
        app.push_screen(MessageScreen("No saved progress found. Run setup first."))
        return

    try:
        output = generate_rules_from_active(
            settings.active_quests,
            settings.hideout_levels,
            all_quests_completed=settings.all_quests_completed,
            completed_quests_override=settings.completed_quests,
        )
    except (FileNotFoundError, ValueError) as exc:
        app.push_screen(MessageScreen(str(exc)))
        return

    write_rules(output, ITEM_RULES_CUSTOM_PATH)
    item_count = output.get("metadata", {}).get("itemCount", 0)
    app.push_screen(MessageScreen(f"Rules regenerated. Items: {item_count}."))


__all__ = [
    "launch_edit_workshops",
    "launch_generate_rules",
    "launch_progress_wizard",
    "launch_review_quests",
    "ProgressIntroScreen",
    "ActiveQuestsScreen",
    "WorkshopLevelsScreen",
    "ProgressSummaryScreen",
    "ReviewQuestsScreen",
]
