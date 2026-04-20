"""ArcTracker API client with rate limiting and OCR fallback support."""

from __future__ import annotations

import logging
import functools
from types import MappingProxyType
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import orjson

if TYPE_CHECKING:
    from ..config import ApiSettings

# requests is in optional-dependencies "scraper"
try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    requests = None  # type: ignore
    HAS_REQUESTS = False

DATA_DIR = Path(__file__).resolve().parent.parent / "progress" / "data"

_log = logging.getLogger(__name__)

ARCTRACKER_BASE_URL = "https://arctracker.io"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0

# Rate limit: 500 req/hour = 1 req per 7.2 seconds max sustained
# We use a more conservative 8 seconds to stay well under the limit
MIN_REQUEST_INTERVAL_SECONDS = 8.0


type ItemDecision = Literal["KEEP", "SELL", "RECYCLE"]


@functools.cache
def _get_cached_item_mappings() -> tuple[MappingProxyType[str, str], MappingProxyType[str, str]]:
    """Load and cache item ID to display name mapping from items.json."""
    id_to_name: dict[str, str] = {}
    name_to_id: dict[str, str] = {}
    try:
        items_path = DATA_DIR / "items.json"
        raw = orjson.loads(items_path.read_bytes())
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    item_id = item.get("id")
                    item_name = item.get("name")
                    if isinstance(item_id, str) and isinstance(item_name, str):
                        id_to_name[item_id] = item_name
                        name_to_id[item_name.lower()] = item_id
    except Exception as exc:
        _log.warning("api: Failed to load item mapping: %s", exc)
    return MappingProxyType(id_to_name), MappingProxyType(name_to_id)


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

    def time_until_next_request(self) -> float:
        """Calculate time to wait before next request."""
        now = time.time()
        time_since_last = now - self.last_request_timestamp
        cooldown = max(0.0, MIN_REQUEST_INTERVAL_SECONDS - time_since_last)

        if self.is_rate_limited:
            return max(cooldown, self.seconds_until_reset)
        return cooldown


@dataclass(slots=True)
class StashItem:
    """An item in the user's stash from API."""

    item_id: str
    name: str
    quantity: int
    slot: int | None
    item_type: str
    rarity: str
    value: int


@dataclass(slots=True)
class StashData:
    """Complete stash data from API."""

    items: list[StashItem] = field(default_factory=list)
    total_slots: int = 0
    used_slots: int = 0
    api_error: str | None = None


@dataclass(slots=True)
class HideoutModule:
    """Hideout module progress from API."""

    module_id: str
    name: str
    current_level: int
    max_level: int


@dataclass(slots=True)
class ProjectPhase:
    """A single phase of a project."""

    phase_number: int
    name: str
    completed: bool


@dataclass(slots=True)
class ProjectProgress:
    """Project progress from API."""

    project_id: str
    name: str
    current_phase: int
    max_phases: int
    completed: bool
    phases: list[ProjectPhase] = field(default_factory=list)


@dataclass(slots=True)
class APIItemDecision:
    """Single item decision from API."""

    item_id: str
    decision: ItemDecision
    item_name: str | None = None  # populated from items.json mapping


@dataclass(slots=True)
class APIInventoryResult:
    """Result from API inventory fetch."""

    decisions: list[APIItemDecision] = field(default_factory=list)
    from_cache: bool = False
    api_error: str | None = None


class ArcTrackerClient:
    """Client for arctracker.io API with rate limiting and fallback support."""

    def __init__(
        self,
        app_key: str | None = None,
        user_key: str | None = None,
        base_url: str = ARCTRACKER_BASE_URL,
    ) -> None:
        self.app_key = app_key
        self.user_key = user_key
        self.base_url = base_url.rstrip("/")
        self.rate_limit = RateLimitState()
        self._session: Any = None
        self._item_id_to_name, self._item_name_to_id = _get_cached_item_mappings()

        if requests is not None:
            self._session = requests.Session()
            self._session.headers.update(
                {
                    "Accept": "application/json",
                    "User-Agent": "ArcRaiders-AutoScrapper/0.2.0",
                }
            )

    def _wait_for_rate_limit(self) -> None:
        """Pre-emptively throttle requests to respect rate limits."""
        wait_time = self.rate_limit.time_until_next_request()
        if wait_time > 0:
            _log.debug("api: Rate limit cooldown: %.2fs", wait_time)
            time.sleep(wait_time)

    def _update_rate_limit(self, headers: dict[str, str]) -> None:
        """Update rate limit state from response headers."""
        try:
            if "X-RateLimit-Limit" in headers:
                self.rate_limit.limit = int(headers["X-RateLimit-Limit"])
            if "X-RateLimit-Remaining" in headers:
                self.rate_limit.remaining = int(headers["X-RateLimit-Remaining"])
            if "X-RateLimit-Reset" in headers:
                # Reset is usually a Unix timestamp
                reset_val = int(headers["X-RateLimit-Reset"])
                # Handle both absolute timestamp and relative seconds
                if reset_val > 1_000_000_000:  # Unix timestamp
                    self.rate_limit.reset_timestamp = float(reset_val)
                else:  # Relative seconds
                    self.rate_limit.reset_timestamp = time.time() + reset_val
        except (ValueError, TypeError) as exc:
            _log.debug("api: Failed to parse rate limit headers: %s", exc)

        self.rate_limit.last_request_timestamp = time.time()

    def _get_headers(self, *, require_auth: bool = False) -> dict[str, str]:
        """Build request headers with optional authentication."""
        headers: dict[str, str] = {}
        if require_auth:
            if self.app_key:
                headers["X-App-Key"] = self.app_key
            if self.user_key:
                headers["Authorization"] = f"Bearer {self.user_key}"
        return headers

    def _make_request(
        self,
        method: str,
        endpoint: str,
        *,
        require_auth: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Make an HTTP request with rate limiting and error handling."""
        if not HAS_REQUESTS:
            _log.warning("api: requests library not available")
            return None

        if require_auth and (not self.app_key or not self.user_key):
            _log.debug("api: Auth required but keys not configured")
            return None

        self._wait_for_rate_limit()

        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(require_auth=require_auth)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        try:
            response = self._session.request(
                method,
                url,
                headers=headers,
                timeout=DEFAULT_TIMEOUT,
                **kwargs,
            )
            self._update_rate_limit(dict(response.headers))

            if response.status_code == 429:
                _log.warning("api: Rate limited (429)")
                return None
            if response.status_code == 401:
                _log.warning("api: Unauthorized (401) - check your app/user keys")
                return None
            if response.status_code == 403:
                _log.warning("api: Forbidden (403) - invalid keys")
                return None

            response.raise_for_status()
            return response.json()
        except Exception as exc:
            if HAS_REQUESTS and requests is not None:
                if isinstance(exc, requests.Timeout):
                    _log.warning("api: Request timeout to %s", endpoint)
                elif isinstance(exc, requests.RequestException):
                    _log.warning("api: Request failed: %s", exc)
                else:
                    _log.warning("api: Unexpected error: %s", exc)
            else:
                _log.warning("api: Unexpected error: %s", exc)

        return None

    def get_public_items(self, locale: str = "en") -> dict[str, Any] | None:
        """Fetch public item data from /api/items (no auth required)."""
        return self._make_request("GET", "/api/items", require_auth=False, params={"locale": locale})

    def get_public_hideout(self, locale: str = "en") -> dict[str, Any] | None:
        """Fetch public hideout data from /api/hideout (no auth required)."""
        return self._make_request("GET", "/api/hideout", require_auth=False, params={"locale": locale})

    def get_public_projects(self, locale: str = "en", season: int | None = None) -> dict[str, Any] | None:
        """Fetch public projects data from /api/projects (no auth required)."""
        params: dict[str, Any] = {"locale": locale}
        if season is not None:
            params["season"] = season
        return self._make_request("GET", "/api/projects", require_auth=False, params=params)

    def get_user_stash(
        self,
        locale: str = "en",
        page: int = 1,
        per_page: int = 500,
    ) -> StashData:
        """Fetch user's stash from /api/v2/user/stash (auth required).

        Args:
            locale: Language code (e.g., "en", "de", "fr").
            page: Page number for pagination.
            per_page: Items per page (max 500).

        Returns:
            StashData with items and metadata.
        """
        result = StashData()

        if not self.is_configured():
            result.api_error = "API not configured (missing app_key or user_key)"
            return result

        data = self._make_request(
            "GET",
            "/api/v2/user/stash",
            require_auth=True,
            params={
                "locale": locale,
                "page": page,
                "per_page": min(per_page, 500),
            },
        )

        if data is None:
            result.api_error = "Failed to fetch stash from API"
            return result

        return self._parse_stash_response(data)

    def get_all_stash_items(self, locale: str = "en") -> StashData:
        """Fetch all stash items across all pages.

        Args:
            locale: Language code.

        Returns:
            StashData with all items merged.
        """
        all_items: list[StashItem] = []
        total_slots = 0
        used_slots = 0
        page = 1
        per_page = 500
        api_error: str | None = None

        while True:
            page_data = self.get_user_stash(locale=locale, page=page, per_page=per_page)

            if page_data.api_error:
                api_error = page_data.api_error
                break

            all_items.extend(page_data.items)
            total_slots = page_data.total_slots
            used_slots = page_data.used_slots

            # Check if we've fetched all items
            if len(page_data.items) < per_page:
                break

            # Safety check: if we somehow got no items, stop
            if not page_data.items:
                break

            page += 1

            # Sanity limit
            if page > 100:
                _log.warning("api: Stash pagination exceeded 100 pages, stopping")
                break

        return StashData(
            items=all_items,
            total_slots=total_slots,
            used_slots=used_slots,
            api_error=api_error,
        )

    def _parse_stash_response(self, data: dict[str, Any]) -> StashData:
        """Parse API stash response into structured result."""
        result = StashData()

        # The response envelope has data and meta
        stash_data = data.get("data", data)
        if not isinstance(stash_data, dict):
            _log.warning("api: Unexpected stash response format")
            return result

        result.total_slots = int(stash_data.get("totalSlots", 0))
        result.used_slots = int(stash_data.get("usedSlots", 0))

        items_data = stash_data.get("items", [])
        if not isinstance(items_data, list):
            _log.warning("api: Unexpected stash items format")
            return result

        for item_data in items_data:
            if not isinstance(item_data, dict):
                continue

            item_id = item_data.get("id")
            name = item_data.get("name")

            if not isinstance(item_id, str) or not isinstance(name, str):
                continue

            result.items.append(
                StashItem(
                    item_id=item_id,
                    name=name,
                    quantity=int(item_data.get("quantity", 1)),
                    slot=item_data.get("slot"),
                    item_type=str(item_data.get("type", "")),
                    rarity=str(item_data.get("rarity", "")),
                    value=int(item_data.get("value", 0)),
                )
            )

        return result

    def get_user_hideout(self, locale: str = "en") -> list[HideoutModule]:
        """Fetch user's hideout progress from /api/v2/user/hideout (auth required).

        Args:
            locale: Language code.

        Returns:
            List of hideout modules with progress.
        """
        if not self.is_configured():
            _log.warning("api: Cannot fetch hideout - API not configured")
            return []

        data = self._make_request(
            "GET",
            "/api/v2/user/hideout",
            require_auth=True,
            params={"locale": locale},
        )

        if data is None:
            return []

        modules_data = data.get("data", [])
        if not isinstance(modules_data, list):
            _log.warning("api: Unexpected hideout response format")
            return []

        modules: list[HideoutModule] = []
        for module_data in modules_data:
            if not isinstance(module_data, dict):
                continue

            module_id = module_data.get("id")
            name = module_data.get("name")

            if not isinstance(module_id, str) or not isinstance(name, str):
                continue

            modules.append(
                HideoutModule(
                    module_id=module_id,
                    name=name,
                    current_level=int(module_data.get("currentLevel", 0)),
                    max_level=int(module_data.get("maxLevel", 0)),
                )
            )

        return modules

    def get_user_projects(
        self,
        locale: str = "en",
        season: int | None = None,
    ) -> list[ProjectProgress]:
        """Fetch user's project progress from /api/v2/user/projects (auth required).

        Args:
            locale: Language code.
            season: Filter by expedition season.

        Returns:
            List of projects with progress.
        """
        if not self.is_configured():
            _log.warning("api: Cannot fetch projects - API not configured")
            return []

        params: dict[str, Any] = {"locale": locale}
        if season is not None:
            params["season"] = season

        data = self._make_request(
            "GET",
            "/api/v2/user/projects",
            require_auth=True,
            params=params,
        )

        if data is None:
            return []

        projects_data = data.get("data", [])
        if not isinstance(projects_data, list):
            _log.warning("api: Unexpected projects response format")
            return []

        projects: list[ProjectProgress] = []
        for project_data in projects_data:
            if not isinstance(project_data, dict):
                continue

            project_id = project_data.get("id")
            name = project_data.get("name")

            if not isinstance(project_id, str) or not isinstance(name, str):
                continue

            # Parse phases
            phases: list[ProjectPhase] = []
            phases_data = project_data.get("phases", [])
            if isinstance(phases_data, list):
                for phase_data in phases_data:
                    if isinstance(phase_data, dict):
                        phases.append(
                            ProjectPhase(
                                phase_number=int(phase_data.get("phase", 0)),
                                name=str(phase_data.get("name", "")),
                                completed=bool(phase_data.get("completed", False)),
                            )
                        )

            projects.append(
                ProjectProgress(
                    project_id=project_id,
                    name=name,
                    current_phase=int(project_data.get("currentPhase", 0)),
                    max_phases=int(project_data.get("maxPhases", 0)),
                    completed=bool(project_data.get("completed", False)),
                    phases=phases,
                )
            )

        return projects

    def test_connection(self) -> dict[str, Any] | None:
        """Test API connection and authentication.

        Returns:
            User profile data if successful, None if failed.
        """
        if not self.is_configured():
            _log.warning("api: Cannot test connection - API not configured")
            return None

        return self._make_request("GET", "/api/v2/user/profile", require_auth=True)

    def get_item_decisions(self, *, fallback_to_ocr: bool = True) -> APIInventoryResult:
        """
        Get item decisions from API with automatic fallback.

        First tries user-specific endpoint (if keys configured),
        then falls back to OCR if API fails.
        """
        result = APIInventoryResult()

        # Try user stash endpoint first if keys are available
        if self.app_key and self.user_key:
            stash_data = self.get_all_stash_items()
            if stash_data.api_error:
                _log.debug("api: Stash fetch failed: %s", stash_data.api_error)
                if not fallback_to_ocr:
                    result.api_error = stash_data.api_error
                    return result
            else:
                # Convert stash items to decisions using action rules
                # This is done in the datasource module
                result.api_error = None  # Success
                return result
        else:
            _log.debug("api: No API keys configured, skipping API lookup")

        # API failed or not configured, fallback will be handled by caller
        result.api_error = "API not configured or unavailable"
        return result

    def is_configured(self) -> bool:
        """Check if API client has necessary configuration."""
        return HAS_REQUESTS and bool(self.app_key and self.user_key)

    def is_public_available(self) -> bool:
        """Check if public API endpoints are reachable."""
        return HAS_REQUESTS


class APIOrchestrator:
    """Orchestrates API and OCR data sources with automatic fallback."""

    def __init__(self, client: ArcTrackerClient | None = None) -> None:
        self.client = client or ArcTrackerClient()
        self._log = logging.getLogger(__name__)

    def get_item_decisions(
        self,
        ocr_items: list[str] | None = None,
        *,
        prefer_api: bool = True,
    ) -> dict[str, ItemDecision]:
        """
        Get decisions for items, preferring API when available.

        Returns a mapping of item names (from OCR) to decisions.
        Falls back to OCR-only if API fails.
        """
        decisions: dict[str, ItemDecision] = {}

        # Try API first if preferred and configured
        if prefer_api and self.client.is_configured():
            api_result = self.client.get_item_decisions(fallback_to_ocr=True)
            if api_result and not api_result.api_error:
                for item in api_result.decisions:
                    # Use display name if available, otherwise item ID
                    key = item.item_name or item.item_id
                    decisions[key] = item.decision
                self._log.info(
                    "api: Retrieved %d decisions from API",
                    len(api_result.decisions),
                )
                return decisions
            self._log.warning("api: API lookup failed, will fallback")

        # Fallback: if OCR items provided, we return empty dict
        # Caller should use their own decision logic
        if ocr_items:
            self._log.debug("api: Using OCR fallback for %d items", len(ocr_items))

        return decisions


def create_client_from_config(
    config: dict[str, Any] | "ApiSettings" | None = None,
) -> ArcTrackerClient:
    """Create API client from config dict or ApiSettings (loaded from settings)."""
    if config is None:
        from ..config import load_api_settings

        settings = load_api_settings()
        return ArcTrackerClient(
            app_key=settings.app_key or None,
            user_key=settings.user_key or None,
        )

    if isinstance(config, dict):
        return ArcTrackerClient(
            app_key=config.get("app_key") or None,
            user_key=config.get("user_key") or None,
        )

    # It's an ApiSettings object
    return ArcTrackerClient(
        app_key=config.app_key or None,
        user_key=config.user_key or None,
    )
