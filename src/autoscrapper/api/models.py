"""ArcTracker API models for API responses."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal


type ItemDecision = Literal["KEEP", "SELL", "RECYCLE"]


@dataclass(slots=True)
class RateLimitState:
    """Tracks rate limit information from API responses."""

    limit: int = 500
    remaining: int = 500
    reset_timestamp: float = 0.0
    last_request_timestamp: float = 0.0

    @property
    def is_rate_limited(self) -> bool:
        """Check if we're currently rate limited."""
        if self.remaining <= 0:
            now = time.time()
            if now < self.reset_timestamp:
                return True
        return False

    @property
    def seconds_until_reset(self) -> float:
        """Seconds until rate limit resets."""
        now = time.time()
        return max(0.0, self.reset_timestamp - now)

    def time_until_next_request(self, min_interval: float = 8.0) -> float:
        """Calculate time to wait before next request."""
        now = time.time()
        time_since_last = now - self.last_request_timestamp
        cooldown = max(0.0, min_interval - time_since_last)

        if self.is_rate_limited:
            return max(cooldown, self.seconds_until_reset)
        return cooldown


@dataclass(frozen=True, slots=True)
class StashItem:
    """An item in the user's stash."""

    item_id: str
    name: str
    quantity: int
    slot: int | None
    item_type: str
    rarity: str
    value: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> StashItem:
        """Create a StashItem from API response data."""
        return cls(
            item_id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            quantity=int(data.get("quantity", 1)),
            slot=data.get("slot"),
            item_type=str(data.get("type", "")),
            rarity=str(data.get("rarity", "")),
            value=int(data.get("value", 0)),
        )


@dataclass(slots=True)
class StashData:
    """Complete stash data from API."""

    items: list[StashItem] = field(default_factory=list)
    total_slots: int = 0
    used_slots: int = 0
    api_error: str | None = None


@dataclass(frozen=True, slots=True)
class HideoutModule:
    """A hideout module with its upgrade progress."""

    module_id: str
    name: str
    current_level: int
    max_level: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> HideoutModule:
        """Create a HideoutModule from API response data."""
        return cls(
            module_id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            current_level=int(data.get("currentLevel", 0)),
            max_level=int(data.get("maxLevel", 0)),
        )


@dataclass(frozen=True, slots=True)
class ProjectPhase:
    """A single phase of a project."""

    phase_number: int
    name: str
    completed: bool

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ProjectPhase:
        """Create a ProjectPhase from API response data."""
        return cls(
            phase_number=int(data.get("phase", 0)),
            name=str(data.get("name", "")),
            completed=bool(data.get("completed", False)),
        )


@dataclass(frozen=True, slots=True)
class ProjectProgress:
    """A project with its completion progress."""

    project_id: str
    name: str
    current_phase: int
    max_phases: int
    completed: bool
    phases: list[ProjectPhase]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ProjectProgress:
        """Create a ProjectProgress from API response data."""
        phases_data = data.get("phases", [])
        phases = [ProjectPhase.from_api(p) for p in phases_data if isinstance(p, dict)]

        return cls(
            project_id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            current_phase=int(data.get("currentPhase", 0)),
            max_phases=int(data.get("maxPhases", 0)),
            completed=bool(data.get("completed", False)),
            phases=phases,
        )


@dataclass(slots=True)
class APIItemDecision:
    """Single item decision from API."""

    item_id: str
    decision: ItemDecision
    item_name: str | None = None


@dataclass(slots=True)
class APIInventoryResult:
    """Result from API inventory fetch."""

    decisions: list[APIItemDecision] = field(default_factory=list)
    from_cache: bool = False
    api_error: str | None = None


@dataclass(frozen=True, slots=True)
class UserProfile:
    """User profile information."""

    username: str
    level: int
    member_since: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> UserProfile:
        return cls(
            username=str(data.get("username", "")),
            level=int(data.get("level", 0)),
            member_since=str(data.get("memberSince", "")),
        )


@dataclass(frozen=True, slots=True)
class UserQuest:
    """A quest with user completion status."""

    quest_id: str
    name: str
    completed: bool
    objectives: list[Any]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> UserQuest:
        return cls(
            quest_id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            completed=bool(data.get("completed", False)),
            objectives=data.get("objectives", []),
        )


@dataclass(frozen=True, slots=True)
class RoundEntry:
    """A single round from the user's round history."""

    round_id: str
    outcome: str
    map_slug: str
    kills: int
    damage: float
    season: int | None
    looted_items: list[Any]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> RoundEntry:
        return cls(
            round_id=str(data.get("id", "")),
            outcome=str(data.get("outcome", "unknown")),
            map_slug=str(data.get("map", "")),
            kills=int(data.get("kills", 0)),
            damage=float(data.get("damage", 0.0)),
            season=data.get("season"),
            looted_items=data.get("lootedItems", []),
        )


@dataclass(frozen=True, slots=True)
class Blueprint:
    """A blueprint with learned status."""

    blueprint_id: str
    name: str
    category: str
    learned: bool

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Blueprint:
        return cls(
            blueprint_id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            category=str(data.get("category", "")),
            learned=bool(data.get("learned", False)),
        )
