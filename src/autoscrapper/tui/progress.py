from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Dict, List, Optional, Set

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from ..config import (
    ProgressSettings,
    has_saved_progress,
    load_progress_settings,
    save_progress_settings,
)
from ..core.item_actions import ITEM_RULES_CUSTOM_PATH
from ..items.rules_store import DEFAULT_RULES_PATH, load_rules
from ..items.rules_diff import RuleChange, collect_rule_changes
from ..progress.data_loader import load_game_data
from ..progress.progress_config import (
    build_quest_index,
    infer_completed_by_trader,
    resolve_active_quests,
)
from ..progress.rules_generator import generate_rules_from_active, write_rules
from .common import AppScreen, MessageScreen


@dataclass(frozen=True)
class QuestEntry:
    id: str
    name: str
    trader: str
    sort_order: int


@dataclass(frozen=True)
class HideoutModule:
    id: str
    name: str
    max_level: int


@dataclass
class ProgressWizardState:
    all_quests_completed: bool
    active_ids: Set[str]
    hideout_levels: Dict[str, int]
    quest_entries: List[QuestEntry]
    hideout_modules: List[HideoutModule]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_quest_value(value: str) -> str:
    normalized = str(value or "").lower().replace("'", "").replace("’", "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _build_quest_entries(quests: List[dict]) -> List[QuestEntry]:
    entries: List[QuestEntry] = []
    for quest in quests:
        quest_id = quest.get("id")
        quest_name = quest.get("name")
        trader = quest.get("trader") or "Unknown"
        sort_order = int(quest.get("sortOrder") or 0)
        if not quest_id or not quest_name:
            continue
        entries.append(
            QuestEntry(
                id=str(quest_id),
                name=str(quest_name),
                trader=str(trader),
                sort_order=sort_order,
            )
        )
    entries.sort(key=lambda entry: (entry.trader, entry.sort_order, entry.name))
    return entries


def _build_hideout_modules(hideout_modules: List[dict]) -> List[HideoutModule]:
    modules: List[HideoutModule] = []
    for module in hideout_modules:
        module_id = module.get("id")
        max_level = int(module.get("maxLevel", 0) or 0)
        if not module_id or max_level <= 0:
            continue
        if module_id in {"stash", "workbench"}:
            continue
        name = module.get("name", module_id)
        modules.append(
            HideoutModule(id=str(module_id), name=str(name), max_level=max_level)
        )
    return modules


def _compute_completed_quests(
    quest_entries: List[QuestEntry],
    active_ids: List[str],
) -> List[str]:
    quests_by_trader: Dict[str, List[dict]] = {}
    for entry in quest_entries:
        quests_by_trader.setdefault(entry.trader, []).append(
            {
                "id": entry.id,
                "name": entry.name,
                "sortOrder": entry.sort_order,
            }
        )
    for trader, quests in quests_by_trader.items():
        quests.sort(key=lambda quest: quest.get("sortOrder") or 0)
        quests_by_trader[trader] = quests

    quest_index = build_quest_index(quests_by_trader)
    active_resolved, missing = resolve_active_quests(active_ids, quest_index)
    if missing:
        raise ValueError(f"Active quests not found: {', '.join(missing)}")
    return infer_completed_by_trader(quests_by_trader, active_resolved)


def _build_state() -> ProgressWizardState:
    game_data = load_game_data()
    quest_entries = _build_quest_entries(game_data.quests)
    hideout_modules = _build_hideout_modules(game_data.hideout_modules)
    settings = load_progress_settings()

    return ProgressWizardState(
        all_quests_completed=settings.all_quests_completed,
        active_ids=set(settings.active_quests),
        hideout_levels=dict(settings.hideout_levels),
        quest_entries=quest_entries,
        hideout_modules=hideout_modules,
    )


class ProgressScreen(AppScreen):
    pass


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

    def compose(self) -> ComposeResult:
        yield Static("Progress Setup", classes="menu-title")
        yield Static(
            "Tell us your current progress so we can generate a personalized rule list.",
            classes="hint",
        )
        yield Static(
            "Have you completed all quests? (If yes, active quests are skipped.)",
            classes="section-title",
        )
        yield OptionList(
            Option("Yes, all quests are completed", id="yes"),
            Option("No, I still have active quests", id="no"),
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
        ("/", "focus_search", "Search"),
        ("ctrl+n", "next", "Next"),
        ("ctrl+p", "back", "Back"),
    ]

    def __init__(self, state: ProgressWizardState) -> None:
        super().__init__()
        self.state = state
        self.filter_text = ""
        self.filtered: List[QuestEntry] = []

    def compose(self) -> ComposeResult:
        yield Static("Select Active Quests", classes="menu-title")
        yield Input(placeholder="Search quests by name or id", id="quest-search")
        yield OptionList(id="quest-list")
        yield Static(id="quest-count", classes="hint")
        with Horizontal(id="quest-actions"):
            yield Button("Back", id="back")
            yield Button("Next", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_options()
        self._focus_list()

    def _focus_list(self) -> None:
        self.query_one("#quest-list", OptionList).focus()

    def _focus_search(self) -> None:
        self.query_one("#quest-search", Input).focus()

    def _filtered_entries(self) -> List[QuestEntry]:
        if not self.filter_text:
            return list(self.state.quest_entries)
        normalized = _normalize_quest_value(self.filter_text)
        if not normalized:
            return list(self.state.quest_entries)
        results: List[QuestEntry] = []
        for entry in self.state.quest_entries:
            name_norm = _normalize_quest_value(entry.name)
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

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "quest-search":
            self.filter_text = event.value
            self._refresh_options()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "quest-search":
            self._focus_list()

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
        self.app.pop_screen()

    def action_focus_search(self) -> None:
        self._focus_search()


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
        ("ctrl+n", "next", "Next"),
        ("ctrl+p", "back", "Back"),
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

    def on_key(self, event) -> None:
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
            _save_workshop_levels(self.state.hideout_levels)
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
        self.error: Optional[str] = None

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
        status = "Yes" if self.state.all_quests_completed else "No"
        lines = [
            f"All quests completed: {status}",
            f"Active quests selected: {active_count}",
            f"Workshops configured: {workshop_count}",
            "",
            "We will infer completed quests and generate a personalized rule list.",
        ]
        self.query_one("#summary-body", Static).update("\n".join(lines))

    def _save(self) -> None:
        try:
            if self.state.all_quests_completed:
                completed_ids = [q.id for q in self.state.quest_entries]
            else:
                completed_ids = _compute_completed_quests(
                    self.state.quest_entries, list(self.state.active_ids)
                )
        except ValueError as exc:
            self.app.push_screen(MessageScreen(str(exc)))
            return

        progress_settings = ProgressSettings(
            all_quests_completed=self.state.all_quests_completed,
            active_quests=sorted(self.state.active_ids),
            completed_quests=sorted(completed_ids),
            hideout_levels=self.state.hideout_levels,
            last_updated=_iso_now(),
        )
        save_progress_settings(progress_settings)

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
        _pop_progress_stack(self.app)
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


class RulesChangesScreen(AppScreen):
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


class ReviewQuestsScreen(ProgressScreen):
    DEFAULT_CSS = """
    ReviewQuestsScreen {
        padding: 1 2;
    }

    #review-actions {
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(
        self, quest_entries: List[QuestEntry], settings: ProgressSettings
    ) -> None:
        super().__init__()
        self.quest_entries = quest_entries
        self.completed = set(settings.completed_quests)
        self.active = set(settings.active_quests)
        self.original = ProgressSettings(
            all_quests_completed=settings.all_quests_completed,
            active_quests=list(settings.active_quests),
            completed_quests=list(settings.completed_quests),
            hideout_levels=dict(settings.hideout_levels),
            last_updated=settings.last_updated,
        )

    def compose(self) -> ComposeResult:
        yield Static("Review Quest Completion", classes="menu-title")
        yield Static(
            "Space toggles completed. Press A to toggle active.",
            classes="hint",
        )
        yield OptionList(id="review-list")
        yield Static(id="review-count", classes="hint")
        with Horizontal(id="review-actions"):
            yield Button("Cancel", id="cancel")
            yield Button("Save", id="save", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def _status_label(self, entry: QuestEntry) -> Text:
        if entry.id in self.completed:
            return Text("✓", style="green")
        if entry.id in self.active:
            return Text("A", style="cyan")
        return Text("·", style="dim")

    def _refresh(self) -> None:
        menu = self.query_one("#review-list", OptionList)
        options: List[Option] = []
        for entry in self.quest_entries:
            label = Text()
            label.append_text(self._status_label(entry))
            label.append(" ")
            label.append(entry.name, style="bold")
            label.append("  ")
            label.append(entry.trader, style="dim")
            options.append(Option(label, id=entry.id))
        menu.set_options(options)
        if options:
            menu.highlighted = 0
        count_text = f"Completed: {len(self.completed)} • Active: {len(self.active)} • Total: {len(self.quest_entries)}"
        self.query_one("#review-count", Static).update(count_text)

    def _toggle_completed(self) -> None:
        menu = self.query_one("#review-list", OptionList)
        if menu.highlighted is None:
            return
        entry = self.quest_entries[menu.highlighted]
        if entry.id in self.completed:
            self.completed.remove(entry.id)
        else:
            self.completed.add(entry.id)
            self.active.discard(entry.id)
        self._refresh()

    def _toggle_active(self) -> None:
        menu = self.query_one("#review-list", OptionList)
        if menu.highlighted is None:
            return
        entry = self.quest_entries[menu.highlighted]
        if entry.id in self.active:
            self.active.remove(entry.id)
        else:
            self.active.add(entry.id)
            self.completed.discard(entry.id)
        self._refresh()

    def on_key(self, event) -> None:
        if event.key == "space":
            self._toggle_completed()
            event.stop()
        elif event.key in {"a", "A"}:
            self._toggle_active()
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
        elif event.button.id == "save":
            updated = ProgressSettings(
                all_quests_completed=(len(self.completed) == len(self.quest_entries)),
                active_quests=sorted(self.active),
                completed_quests=sorted(self.completed),
                hideout_levels=self.original.hideout_levels,
                last_updated=_iso_now(),
            )
            save_progress_settings(updated)
            self.app.pop_screen()
            self.app.push_screen(MessageScreen("Quest progress saved."))


def _save_workshop_levels(levels: Dict[str, int]) -> None:
    settings = load_progress_settings()
    updated = ProgressSettings(
        all_quests_completed=settings.all_quests_completed,
        active_quests=settings.active_quests,
        completed_quests=settings.completed_quests,
        hideout_levels=levels,
        last_updated=_iso_now(),
    )
    save_progress_settings(updated)


def _pop_progress_stack(app) -> None:
    while isinstance(app.screen, ProgressScreen):
        app.pop_screen()


def launch_progress_wizard(app) -> None:
    try:
        state = _build_state()
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
    quest_entries = _build_quest_entries(game_data.quests)
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
        hideout_modules=_build_hideout_modules(game_data.hideout_modules),
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
