from __future__ import annotations

import html
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .data_loader import DATA_DIR
from .quest_overrides import apply_quest_overrides

METAFORGE_APP_URL = "https://metaforge.app/arc-raiders"
METAFORGE_API_BASE = "https://metaforge.app/api/arc-raiders"
METAFORGE_SOURCES_FILENAME = "metaforge_sources.json"
DEFAULT_SUPABASE_URL = "https://sb.metaforge.app/rest/v1"
DEFAULT_SUPABASE_ANON_KEY = "sb_publishable_C7SqVOoZBPFy4W0DxKcOGQ_emEIw-rj"
SUPABASE_URL = os.environ.get(
    "METAFORGE_SUPABASE_URL",
    DEFAULT_SUPABASE_URL,
).rstrip("/")

SUPABASE_ANON_KEY = os.environ.get(
    "METAFORGE_SUPABASE_ANON_KEY",
    DEFAULT_SUPABASE_ANON_KEY,
)

SUPABASE_AUTH_ERROR_MARKERS = (
    "unauthorized",
    "invalid api key",
    "legacy api keys are disabled",
    "unauthorized_disabled_legacy_key",
    "jwt",
)
_discovered_supabase_config: Optional["SupabaseConfig"] = None


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    anon_key: str
    source: str
    persist_discovery: bool


class DownloadError(RuntimeError):
    pass


class HttpDownloadError(DownloadError):
    def __init__(self, url: str, status_code: int, body: str) -> None:
        self.url = url
        self.status_code = status_code
        self.body = body
        details = body.strip().replace("\n", " ")[:300]
        message = f"HTTP {status_code} for {url}"
        if details:
            message = f"{message}: {details}"
        super().__init__(message)


def _fetch_text(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    *,
    accept: str = "application/json",
) -> str:
    request_headers = {
        "Accept": accept,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/132.0.0.0 Safari/537.36"
        ),
    }
    if headers:
        request_headers.update(headers)

    req = Request(url, headers=request_headers)
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise HttpDownloadError(url, exc.code, body) from exc
    except URLError as exc:
        raise DownloadError(f"Failed to reach {url}: {exc}") from exc


def _fetch_json(url: str, headers: Optional[Dict[str, str]] = None) -> object:
    payload = _fetch_text(url, headers)
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DownloadError(f"Invalid JSON response for {url}") from exc


def _fetch_all_items() -> List[dict]:
    items: List[dict] = []
    current_page = 1
    has_next = True
    limit = 100

    while has_next:
        url = f"{METAFORGE_API_BASE}/items?page={current_page}&limit={limit}"
        response = _fetch_json(url)
        if not isinstance(response, dict):
            raise DownloadError("Unexpected response for items")
        data = response.get("data") or []
        if isinstance(data, list):
            items.extend(data)
        pagination = response.get("pagination") or {}
        has_next = bool(pagination.get("hasNextPage"))
        current_page += 1
        if has_next:
            time.sleep(0.1)

    return items


def _fetch_all_quests() -> List[dict]:
    quests: List[dict] = []
    current_page = 1
    has_next = True
    limit = 100

    while has_next:
        url = f"{METAFORGE_API_BASE}/quests?page={current_page}&limit={limit}"
        response = _fetch_json(url)
        if not isinstance(response, dict):
            raise DownloadError("Unexpected response for quests")
        data = response.get("data") or []
        if isinstance(data, list):
            quests.extend(data)
        pagination = response.get("pagination") or {}
        has_next = bool(pagination.get("hasNextPage"))
        current_page += 1
        if has_next:
            time.sleep(0.1)

    return quests


def _normalize_supabase_rest_url(supabase_url: str) -> str:
    normalized = supabase_url.strip().rstrip("/")
    if normalized.endswith("/rest/v1"):
        return normalized
    return f"{normalized}/rest/v1"


def _sources_path(data_dir: Path) -> Path:
    return data_dir / METAFORGE_SOURCES_FILENAME


def _load_sources_config(path: Path) -> Optional[SupabaseConfig]:
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DownloadError(f"Could not parse {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise DownloadError(f"{path} must contain a JSON object")

    supabase_url = payload.get("supabaseUrl")
    anon_key = payload.get("supabaseAnonKey")
    if not isinstance(supabase_url, str) or not supabase_url.strip():
        raise DownloadError(f"{path} is missing supabaseUrl")
    if not isinstance(anon_key, str) or not anon_key.strip():
        raise DownloadError(f"{path} is missing supabaseAnonKey")

    return SupabaseConfig(
        url=_normalize_supabase_rest_url(supabase_url),
        anon_key=anon_key,
        source=str(path),
        persist_discovery=True,
    )


def _configured_supabase_config(sources_path: Path) -> SupabaseConfig:
    env_url = os.environ.get("METAFORGE_SUPABASE_URL")
    env_key = os.environ.get("METAFORGE_SUPABASE_ANON_KEY")

    if env_url and env_key:
        return SupabaseConfig(
            url=_normalize_supabase_rest_url(env_url),
            anon_key=env_key,
            source="environment",
            persist_discovery=False,
        )

    try:
        file_config = _load_sources_config(sources_path)
    except DownloadError:
        if not env_url and not env_key:
            raise
        file_config = None

    if env_url or env_key:
        fallback = file_config or SupabaseConfig(
            url=DEFAULT_SUPABASE_URL,
            anon_key=DEFAULT_SUPABASE_ANON_KEY,
            source="defaults",
            persist_discovery=False,
        )
        return SupabaseConfig(
            url=_normalize_supabase_rest_url(env_url) if env_url else fallback.url,
            anon_key=env_key if env_key else fallback.anon_key,
            source="environment",
            persist_discovery=False,
        )

    if file_config is not None:
        return file_config

    return SupabaseConfig(
        url=DEFAULT_SUPABASE_URL,
        anon_key=DEFAULT_SUPABASE_ANON_KEY,
        source="defaults",
        persist_discovery=True,
    )


def _sources_config_matches(path: Path, config: SupabaseConfig) -> bool:
    if not path.exists():
        return False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False

    if not isinstance(payload, dict):
        return False

    supabase_url = payload.get("supabaseUrl")
    anon_key = payload.get("supabaseAnonKey")
    if not isinstance(supabase_url, str) or not isinstance(anon_key, str):
        return False

    return (
        _normalize_supabase_rest_url(supabase_url) == config.url
        and anon_key == config.anon_key
        and payload.get("sourcePage") == METAFORGE_APP_URL
    )


def _write_sources_config(path: Path, config: SupabaseConfig) -> None:
    if _sources_config_matches(path, config):
        return

    payload = {
        "sourcePage": METAFORGE_APP_URL,
        "supabaseUrl": config.url,
        "supabaseAnonKey": config.anon_key,
        "lastDiscoveredAt": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _extract_public_env_value(source: str, key: str) -> str:
    unescaped_source = html.unescape(source)
    match = re.search(
        rf'"{re.escape(key)}"\s*:\s*("(?:\\.|[^"\\])*")',
        unescaped_source,
    )
    if not match:
        raise DownloadError(f"Could not find {key} in {METAFORGE_APP_URL}")
    value = json.loads(match.group(1))
    if not isinstance(value, str) or not value.strip():
        raise DownloadError(f"Invalid {key} in {METAFORGE_APP_URL}")
    return value


def _discover_supabase_config() -> SupabaseConfig:
    global _discovered_supabase_config

    if _discovered_supabase_config is not None:
        return _discovered_supabase_config

    page = _fetch_text(METAFORGE_APP_URL, accept="text/html,application/xhtml+xml")
    supabase_url = _normalize_supabase_rest_url(
        _extract_public_env_value(page, "PUBLIC_SUPABASE_URL")
    )
    anon_key = _extract_public_env_value(page, "PUBLIC_SUPABASE_ANON_KEY")
    _discovered_supabase_config = SupabaseConfig(
        url=supabase_url,
        anon_key=anon_key,
        source=METAFORGE_APP_URL,
        persist_discovery=False,
    )
    return _discovered_supabase_config


def _is_supabase_auth_error(exc: DownloadError) -> bool:
    if not isinstance(exc, HttpDownloadError):
        return False
    if exc.status_code in {401, 403}:
        return True
    body = exc.body.lower()
    return any(marker in body for marker in SUPABASE_AUTH_ERROR_MARKERS)


def _fetch_supabase_all_with_config(table: str, config: SupabaseConfig) -> List[dict]:
    headers = {
        "apikey": config.anon_key,
        "Authorization": f"Bearer {config.anon_key}",
    }
    page_size = 1000
    offset = 0
    all_rows: List[dict] = []

    while True:
        url = f"{config.url}/{table}?select=*&limit={page_size}&offset={offset}"
        batch = _fetch_json(url, headers=headers)
        if not isinstance(batch, list):
            raise DownloadError(f"Unexpected response for {table}: expected array")
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
        time.sleep(0.1)

    return all_rows


def _fetch_supabase_all(table: str, sources_path: Path) -> List[dict]:
    configured = _configured_supabase_config(sources_path)
    if _discovered_supabase_config is not None:
        if configured.persist_discovery:
            _write_sources_config(sources_path, _discovered_supabase_config)
        supabase_config = _discovered_supabase_config
    else:
        supabase_config = configured
    try:
        return _fetch_supabase_all_with_config(table, supabase_config)
    except DownloadError as exc:
        if not _is_supabase_auth_error(exc):
            raise

        discovered = _discover_supabase_config()
        if discovered == supabase_config:
            raise DownloadError(
                "Supabase auth failed and Metaforge page discovery returned "
                "the same public Supabase config."
            ) from exc
        if configured.persist_discovery:
            _write_sources_config(sources_path, discovered)
        return _fetch_supabase_all_with_config(table, discovered)


def _build_component_map(components: List[dict]) -> Dict[str, Dict[str, int]]:
    component_map: Dict[str, Dict[str, int]] = {}
    for component in components:
        item_id = component.get("item_id")
        component_id = component.get("component_id")
        quantity = component.get("quantity")
        if not item_id or not component_id or quantity is None:
            continue
        component_map.setdefault(item_id, {})[component_id] = int(quantity)
    return component_map


def _map_metaforge_item(
    metaforge_item: dict,
    crafting_map: Dict[str, Dict[str, int]],
    recycle_map: Dict[str, Dict[str, int]],
) -> dict:
    stat_block = metaforge_item.get("stat_block") or {}
    return {
        "id": metaforge_item.get("id"),
        "name": metaforge_item.get("name"),
        "type": metaforge_item.get("item_type") or "Unknown",
        "rarity": (
            str(metaforge_item.get("rarity")).lower()
            if metaforge_item.get("rarity")
            else None
        ),
        "value": metaforge_item.get("value") or 0,
        "weightKg": stat_block.get("weight") or 0,
        "stackSize": stat_block.get("stackSize") or 1,
        "craftBench": metaforge_item.get("workbench") or None,
        "updatedAt": metaforge_item.get("updated_at")
        or datetime.now(timezone.utc).isoformat(),
        "recipe": crafting_map.get(metaforge_item.get("id")) or None,
        "recyclesInto": recycle_map.get(metaforge_item.get("id")) or None,
    }


def _map_metaforge_quest(metaforge_quest: dict) -> dict:
    position = metaforge_quest.get("position") or {}
    sort_order = position.get("y", metaforge_quest.get("sort_order", 0))

    required_items = metaforge_quest.get("required_items") or []
    rewards = metaforge_quest.get("rewards") or []

    reward_item_ids: List[str] = []
    if isinstance(rewards, list):
        for reward in rewards:
            reward_item_id: Optional[str] = None
            if isinstance(reward, dict):
                reward_item_id = reward.get("item_id")
                if not reward_item_id:
                    reward_item = reward.get("item")
                    if isinstance(reward_item, dict):
                        reward_item_id = reward_item.get("id")
                    elif isinstance(reward_item, str):
                        reward_item_id = reward_item
            elif isinstance(reward, str):
                reward_item_id = reward

            if isinstance(reward_item_id, str) and reward_item_id:
                reward_item_ids.append(reward_item_id)

    # Keep IDs stable while removing duplicates.
    reward_item_ids = list(dict.fromkeys(reward_item_ids))

    return {
        "id": metaforge_quest.get("id"),
        "name": metaforge_quest.get("name"),
        "objectives": metaforge_quest.get("objectives") or [],
        "requirements": required_items,
        "rewardItemIds": reward_item_ids,
        "rewards": rewards,
        "trader": metaforge_quest.get("trader_name") or "Unknown",
        "xp": metaforge_quest.get("xp") or 0,
        "sortOrder": sort_order,
    }


def _build_quests_by_trader(quests: List[dict]) -> Dict[str, List[dict]]:
    by_trader: Dict[str, List[dict]] = {}
    for quest in quests:
        trader = quest.get("trader") or "Unknown"
        by_trader.setdefault(trader, []).append(
            {
                "id": quest.get("id"),
                "name": quest.get("name"),
                "sortOrder": quest.get("sortOrder", 0),
            }
        )

    for trader, quests_list in by_trader.items():
        quests_list.sort(key=lambda q: q.get("sortOrder") or 0)

    return by_trader


def update_data_snapshot(data_dir: Optional[Path] = None) -> dict:
    data_dir = data_dir or DATA_DIR
    (data_dir / "static").mkdir(parents=True, exist_ok=True)
    sources_path = _sources_path(data_dir)

    metaforge_items = _fetch_all_items()
    metaforge_quests = _fetch_all_quests()

    components = _fetch_supabase_all("arc_item_components", sources_path)
    recycle_components = _fetch_supabase_all(
        "arc_item_recycle_components", sources_path
    )

    crafting_map = _build_component_map(components)
    recycle_map = _build_component_map(recycle_components)

    mapped_items = [
        _map_metaforge_item(item, crafting_map, recycle_map) for item in metaforge_items
    ]
    mapped_quests = [_map_metaforge_quest(quest) for quest in metaforge_quests]
    mapped_quests = apply_quest_overrides(mapped_quests)

    (data_dir / "items.json").write_text(
        json.dumps(mapped_items, indent=2), encoding="utf-8"
    )
    (data_dir / "quests.json").write_text(
        json.dumps(mapped_quests, indent=2), encoding="utf-8"
    )

    quests_by_trader = {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "quests.json",
        "traders": _build_quests_by_trader(mapped_quests),
    }
    (data_dir / "quests_by_trader.json").write_text(
        json.dumps(quests_by_trader, indent=2), encoding="utf-8"
    )

    metadata = {
        "lastUpdated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "https://metaforge.app/arc-raiders",
        "version": "autoscrapper-data-1",
        "itemCount": len(mapped_items),
        "questCount": len(mapped_quests),
        # Kept for compatibility with older metadata consumers.
        "hasPriceOverrides": False,
    }
    (data_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    return metadata
