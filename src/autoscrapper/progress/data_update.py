from __future__ import annotations

import concurrent.futures
import io
import logging
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import orjson

from .data_loader import DATA_DIR
from .quest_overrides import apply_quest_overrides

_log = logging.getLogger(__name__)

METAFORGE_API_DOCS_URL = "https://metaforge.app/arc-raiders/api"
METAFORGE_API_BASE = "https://metaforge.app/api/arc-raiders"
RAIDTHEORY_REPO_URL = "https://github.com/fgrzesiak/arcraiders-data"
RAIDTHEORY_ARCHIVE_URL = "https://github.com/fgrzesiak/arcraiders-data/archive/refs/heads/main.zip"
WIKI_LOOT_URL = "https://arcraiders.wiki/wiki/Loot"
WIKI_USER_AGENT = "arc-raiders-autoscrapper/1.0 (https://github.com/Ven0m0/arc-raiders-autoscrapper)"

ARCTRACKER_BASE_URL = "https://arctracker.io"
ARCTRACKER_API_DOCS_URL = "https://arctracker.io/developers/docs"


try:
    import requests as _requests
    from bs4 import BeautifulSoup as _BeautifulSoup

    _SCRAPER_AVAILABLE = True
except ImportError:
    _requests = None  # type: ignore[assignment]
    _BeautifulSoup = None  # type: ignore[assignment]
    _SCRAPER_AVAILABLE = False


class DownloadError(RuntimeError):
    pass


def _fetch_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    request_headers = {
        "Accept": "application/json",
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
            return resp.read()
    except HTTPError as exc:
        raise DownloadError(f"HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise DownloadError(f"Failed to reach {url}: {exc}") from exc


def _fetch_json(url: str, headers: dict[str, str] | None = None) -> object:
    try:
        return orjson.loads(_fetch_bytes(url, headers=headers))
    except orjson.JSONDecodeError as exc:
        raise DownloadError(f"Invalid JSON returned from {url}") from exc


def _fetch_arctracker_items() -> list[dict]:
    """Fetch all items from arctracker.io public API."""
    url = f"{ARCTRACKER_BASE_URL}/api/items"
    response = _fetch_json(url)
    if not isinstance(response, dict):
        raise DownloadError("Unexpected response from arctracker items endpoint")
    data = response.get("data") or []
    if not isinstance(data, list):
        raise DownloadError("Unexpected arctracker items payload: data must be a list")
    return [entry for entry in data if isinstance(entry, dict)]


def _fetch_arctracker_quests() -> list[dict]:
    """Fetch all quests from arctracker.io public API."""
    url = f"{ARCTRACKER_BASE_URL}/api/quests"
    response = _fetch_json(url)
    if not isinstance(response, dict):
        raise DownloadError("Unexpected response from arctracker quests endpoint")
    data = response.get("data") or []
    if not isinstance(data, list):
        raise DownloadError("Unexpected arctracker quests payload: data must be a list")
    return [entry for entry in data if isinstance(entry, dict)]


def _fetch_arctracker_hideout() -> list[dict]:
    """Fetch all hideout modules from arctracker.io public API."""
    url = f"{ARCTRACKER_BASE_URL}/api/hideout"
    response = _fetch_json(url)
    if not isinstance(response, dict):
        raise DownloadError("Unexpected response from arctracker hideout endpoint")
    data = response.get("data") or []
    if not isinstance(data, list):
        raise DownloadError("Unexpected arctracker hideout payload: data must be a list")
    return [entry for entry in data if isinstance(entry, dict)]


def _fetch_arctracker_projects() -> list[dict]:
    """Fetch all projects from arctracker.io public API."""
    url = f"{ARCTRACKER_BASE_URL}/api/projects"
    response = _fetch_json(url)
    if not isinstance(response, dict):
        raise DownloadError("Unexpected response from arctracker projects endpoint")
    data = response.get("data") or []
    if not isinstance(data, list):
        raise DownloadError("Unexpected arctracker projects payload: data must be a list")
    return [entry for entry in data if isinstance(entry, dict)]


def _map_arctracker_item(arctracker_item: dict) -> dict | None:
    """Map arctracker.io item format to internal format."""
    item_id = arctracker_item.get("id")
    item_name = arctracker_item.get("name")
    if not isinstance(item_id, str) or not isinstance(item_name, str):
        return None

    return {
        "id": item_id,
        "name": item_name,
        "type": arctracker_item.get("type") or "Unknown",
        "rarity": (str(arctracker_item.get("rarity")).lower() if arctracker_item.get("rarity") else None),
        "value": arctracker_item.get("value") or 0,
        "weightKg": arctracker_item.get("weightKg") or 0,
        "stackSize": arctracker_item.get("stackSize") or 1,
        "craftBench": arctracker_item.get("craftBench") or None,
        "updatedAt": arctracker_item.get("updatedAt") or datetime.now(timezone.utc).isoformat(),
        "recipe": None,  # arctracker doesn't provide recipe data in public endpoint
        "recyclesInto": None,  # arctracker doesn't provide recycle data in public endpoint
    }


def _map_arctracker_quest(arctracker_quest: dict) -> dict | None:
    """Map arctracker.io quest format to internal format."""
    quest_id = arctracker_quest.get("id")
    quest_name = arctracker_quest.get("name")
    if not isinstance(quest_id, str) or not isinstance(quest_name, str):
        return None

    # Extract objectives from multilingual object
    objectives: list[str] = []
    raw_objectives = arctracker_quest.get("objectives")
    if isinstance(raw_objectives, dict):
        # Try to get English objectives first
        en_objectives = raw_objectives.get("en")
        if isinstance(en_objectives, list):
            objectives = [str(obj) for obj in en_objectives if isinstance(obj, str)]
    elif isinstance(raw_objectives, list):
        objectives = [str(obj) for obj in raw_objectives if isinstance(obj, str)]

    # Extract rewards
    reward_item_ids: list[str] = []
    rewards: list[dict] = []
    raw_rewards = arctracker_quest.get("rewards")
    if isinstance(raw_rewards, list):
        for reward in raw_rewards:
            if isinstance(reward, dict):
                item_id = reward.get("item_id") or reward.get("itemId")
                if isinstance(item_id, str):
                    reward_item_ids.append(item_id)
                    reward_payload: dict[str, object] = {"item_id": item_id}
                    quantity = reward.get("quantity")
                    if quantity is not None:
                        reward_payload["quantity"] = str(quantity)
                    # Add item name if available
                    item_name = reward.get("item_name") or reward.get("itemName")
                    if isinstance(item_name, str):
                        reward_payload["item"] = {"id": item_id, "name": item_name}
                    rewards.append(reward_payload)

    return {
        "id": quest_id,
        "name": quest_name,
        "objectives": objectives,
        "requirements": [],
        "rewardItemIds": list(dict.fromkeys(reward_item_ids)),  # Remove duplicates while preserving order
        "rewards": rewards,
        "trader": arctracker_quest.get("trader") or "Unknown",
        "xp": arctracker_quest.get("xp") or 0,
        "sortOrder": arctracker_quest.get("sortOrder") or arctracker_quest.get("sort_order") or 0,
    }


def _fetch_metaforge_collection(resource: str, extra_params: str = "") -> list[dict]:
    rows: list[dict] = []
    limit = 100

    url = f"{METAFORGE_API_BASE}/{resource}?page=1&limit={limit}{extra_params}"
    response = _fetch_json(url)
    if not isinstance(response, dict):
        raise DownloadError(f"Unexpected response for {resource}")
    data = response.get("data") or []
    if not isinstance(data, list):
        raise DownloadError(f"Unexpected {resource} payload: data must be a list")
    rows.extend(entry for entry in data if isinstance(entry, dict))

    pagination = response.get("pagination") or {}
    if not isinstance(pagination, dict):
        raise DownloadError(f"Unexpected {resource} payload: pagination must be an object")

    raw_total_pages = pagination.get("totalPages")
    total_pages: int | None
    if raw_total_pages is None:
        total_pages = None
    elif isinstance(raw_total_pages, bool):
        raise DownloadError(f"Unexpected {resource} payload: totalPages must be an integer")
    elif isinstance(raw_total_pages, int):
        total_pages = raw_total_pages
    elif isinstance(raw_total_pages, str):
        try:
            total_pages = int(raw_total_pages)
        except ValueError as exc:
            raise DownloadError(f"Unexpected {resource} payload: totalPages must be an integer") from exc
    else:
        raise DownloadError(f"Unexpected {resource} payload: totalPages must be an integer")

    if total_pages is not None and total_pages > 1:

        def fetch_page(page: int) -> list[dict]:
            page_url = f"{METAFORGE_API_BASE}/{resource}?page={page}&limit={limit}{extra_params}"
            try:
                page_response = _fetch_json(page_url)
                if not isinstance(page_response, dict):
                    raise DownloadError(f"Unexpected response for {resource} on page {page} ({page_url})")
                page_data = page_response.get("data") or []
                if not isinstance(page_data, list):
                    raise DownloadError(
                        f"Unexpected {resource} payload on page {page} ({page_url}): data must be a list"
                    )
                return [entry for entry in page_data if isinstance(entry, dict)]
            except DownloadError:
                raise
            except Exception as exc:
                raise DownloadError(f"Failed to fetch {resource} page {page} ({page_url})") from exc

        max_workers = min(10, total_pages - 1)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for page_rows in executor.map(fetch_page, range(2, total_pages + 1)):
                rows.extend(page_rows)
    elif pagination.get("hasNextPage"):
        # Fallback to sequential if totalPages is not available
        current_page = 2
        has_next = True
        while has_next:
            url = f"{METAFORGE_API_BASE}/{resource}?page={current_page}&limit={limit}{extra_params}"
            response = _fetch_json(url)
            if not isinstance(response, dict):
                raise DownloadError(f"Unexpected response for {resource} on page {current_page} ({url})")
            data = response.get("data") or []
            if not isinstance(data, list):
                raise DownloadError(
                    f"Unexpected {resource} payload on page {current_page} ({url}): data must be a list"
                )
            rows.extend(entry for entry in data if isinstance(entry, dict))
            pagination = response.get("pagination") or {}
            has_next = bool(pagination.get("hasNextPage"))
            current_page += 1

    return rows


def _fetch_all_items() -> list[dict]:
    return _fetch_metaforge_collection("items", "&includeComponents=true")


def _fetch_all_quests() -> list[dict]:
    return _fetch_metaforge_collection("quests")


def _extract_component_dict(value: object) -> dict[str, int] | None:
    if isinstance(value, dict) and value:
        try:
            return {str(k): int(v) for k, v in value.items() if v is not None}
        except (TypeError, ValueError):
            return None
    if isinstance(value, list):
        result: dict[str, int] = {}
        for entry in value:
            if not isinstance(entry, dict):
                continue
            comp_id = entry.get("component_id") or entry.get("id") or entry.get("componentId")
            qty = entry.get("quantity") or entry.get("amount")
            if comp_id and qty is not None:
                result[str(comp_id)] = int(qty)
        return result or None
    return None


def _normalize_external_id(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value.replace("_", "-")


def _extract_english_text(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        english_value = value.get("en")
        if isinstance(english_value, str) and english_value:
            return english_value
    return None


def _normalize_component_values(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None

    normalized: dict[str, int] = {}
    for raw_item_id, raw_quantity in value.items():
        item_id = _normalize_external_id(raw_item_id)
        if item_id is None:
            continue
        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        normalized[item_id] = quantity

    return normalized or None


def _normalize_raidtheory_rewards(value: object, item_names: dict[str, str]) -> tuple[list[str], list[dict]]:
    if not isinstance(value, list):
        return [], []

    reward_ids: list[str] = []
    rewards: list[dict] = []
    for reward in value:
        if not isinstance(reward, dict):
            continue
        item_id = _normalize_external_id(reward.get("itemId") or reward.get("item_id"))
        if item_id is None:
            continue
        reward_ids.append(item_id)

        reward_payload: dict[str, object] = {"item_id": item_id}
        quantity = reward.get("quantity")
        if quantity is not None:
            reward_payload["quantity"] = str(quantity)

        item_payload: dict[str, object] = {"id": item_id}
        reward_name = item_names.get(item_id)
        if reward_name:
            item_payload["name"] = reward_name
        reward_payload["item"] = item_payload
        rewards.append(reward_payload)

    return list(dict.fromkeys(reward_ids)), rewards


def _normalize_raidtheory_objectives(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    objectives: list[str] = []
    for objective in value:
        text = _extract_english_text(objective)
        if text:
            objectives.append(text)
    return objectives


def _raidtheory_archive_prefix(names: list[str]) -> str:
    for name in names:
        if "/" in name:
            return name.split("/", 1)[0] + "/"
    raise DownloadError("RaidTheory archive is missing the expected root directory")


def _load_raidtheory_json_entries(archive: zipfile.ZipFile, prefix: str) -> list[dict]:
    entries: list[dict] = []
    for name in sorted(archive.namelist()):
        if not name.startswith(prefix) or not name.endswith(".json"):
            continue
        with archive.open(name) as file_obj:
            try:
                payload = orjson.loads(file_obj.read())
            except orjson.JSONDecodeError as exc:
                raise DownloadError(f"Invalid JSON in RaidTheory archive member {name}") from exc
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def _map_raidtheory_item(raidtheory_item: dict) -> dict | None:
    item_id = _normalize_external_id(raidtheory_item.get("id"))
    item_name = _extract_english_text(raidtheory_item.get("name"))
    if item_id is None or item_name is None:
        return None

    return {
        "id": item_id,
        "name": item_name,
        "type": raidtheory_item.get("type") or "Unknown",
        "rarity": (str(raidtheory_item.get("rarity")).lower() if raidtheory_item.get("rarity") else None),
        "value": raidtheory_item.get("value") or 0,
        "weightKg": raidtheory_item.get("weightKg") or 0,
        "stackSize": raidtheory_item.get("stackSize") or 1,
        "craftBench": raidtheory_item.get("craftBench") or None,
        "updatedAt": raidtheory_item.get("updatedAt") or datetime.now(timezone.utc).isoformat(),
        "recipe": _normalize_component_values(raidtheory_item.get("recipe")),
        "recyclesInto": _normalize_component_values(raidtheory_item.get("recyclesInto")),
    }


def _map_raidtheory_quest(raidtheory_quest: dict, item_names: dict[str, str]) -> dict | None:
    quest_id = _normalize_external_id(raidtheory_quest.get("id"))
    quest_name = _extract_english_text(raidtheory_quest.get("name"))
    if quest_id is None or quest_name is None:
        return None

    reward_item_ids, rewards = _normalize_raidtheory_rewards(raidtheory_quest.get("rewardItemIds"), item_names)

    return {
        "id": quest_id,
        "name": quest_name,
        "objectives": _normalize_raidtheory_objectives(raidtheory_quest.get("objectives")),
        "requirements": [],
        "rewardItemIds": reward_item_ids,
        "rewards": rewards,
        "trader": raidtheory_quest.get("trader") or "Unknown",
        "xp": raidtheory_quest.get("xp") or 0,
        "sortOrder": raidtheory_quest.get("sortOrder") or 0,
    }


def _load_raidtheory_fallback_data() -> tuple[list[dict], list[dict]]:
    archive_bytes = _fetch_bytes(
        RAIDTHEORY_ARCHIVE_URL,
        headers={"Accept": "application/octet-stream"},
    )
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            prefix = _raidtheory_archive_prefix(archive.namelist())
            raw_items = _load_raidtheory_json_entries(archive, f"{prefix}items/")
            raw_quests = _load_raidtheory_json_entries(archive, f"{prefix}quests/")
    except zipfile.BadZipFile as exc:
        raise DownloadError("RaidTheory fallback archive is not a valid zip file") from exc

    mapped_items = [mapped_item for item in raw_items if (mapped_item := _map_raidtheory_item(item)) is not None]
    item_names = {
        item["id"]: item["name"]
        for item in mapped_items
        if isinstance(item.get("id"), str) and isinstance(item.get("name"), str)
    }
    mapped_quests = [
        mapped_quest for quest in raw_quests if (mapped_quest := _map_raidtheory_quest(quest, item_names)) is not None
    ]
    return mapped_items, mapped_quests


def _normalize_entry_name(name: object) -> str:
    text = str(name or "").lower().replace("'", "").replace("\u2019", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _merge_missing_entries(primary: list[dict], fallback: list[dict]) -> tuple[list[dict], int]:
    merged: list[dict] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()

    for entry in primary:
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            continue
        if entry_id in seen_ids:
            continue
        merged.append(entry)
        seen_ids.add(entry_id)
        name_key = _normalize_entry_name(entry.get("name"))
        if name_key:
            seen_names.add(name_key)

    supplemental_count = 0
    for entry in fallback:
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            continue
        if entry_id in seen_ids:
            continue
        name_key = _normalize_entry_name(entry.get("name"))
        if name_key and name_key in seen_names:
            continue
        merged.append(entry)
        seen_ids.add(entry_id)
        if name_key:
            seen_names.add(name_key)
        supplemental_count += 1

    return merged, supplemental_count


def _map_metaforge_item(metaforge_item: dict) -> dict:
    stat_block = metaforge_item.get("stat_block") or {}
    return {
        "id": metaforge_item.get("id"),
        "name": metaforge_item.get("name"),
        "type": metaforge_item.get("item_type") or "Unknown",
        "rarity": (str(metaforge_item.get("rarity")).lower() if metaforge_item.get("rarity") else None),
        "value": metaforge_item.get("value") or 0,
        "weightKg": stat_block.get("weight") or 0,
        "stackSize": stat_block.get("stackSize") or 1,
        "craftBench": metaforge_item.get("workbench") or None,
        "updatedAt": metaforge_item.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        "recipe": _extract_component_dict(metaforge_item.get("components") or metaforge_item.get("recipe")),
        "recyclesInto": _extract_component_dict(
            metaforge_item.get("recycleComponents")
            or metaforge_item.get("recycle_components")
            or metaforge_item.get("recyclesInto")
        ),
    }


def _map_metaforge_quest(metaforge_quest: dict) -> dict:
    position = metaforge_quest.get("position") or {}
    sort_order = position.get("y", metaforge_quest.get("sort_order", 0))

    required_items = metaforge_quest.get("required_items") or []
    rewards = metaforge_quest.get("rewards") or []

    reward_item_ids: list[str] = []
    if isinstance(rewards, list):
        for reward in rewards:
            reward_item_id: str | None = None
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


def _build_quests_by_trader(quests: list[dict]) -> dict[str, list[dict]]:
    by_trader: dict[str, list[dict]] = {}
    for quest in quests:
        trader = quest.get("trader") or "Unknown"
        by_trader.setdefault(trader, []).append({
            "id": quest.get("id"),
            "name": quest.get("name"),
            "sortOrder": quest.get("sortOrder", 0),
        })

    for trader, quests_list in by_trader.items():
        quests_list.sort(key=lambda q: q.get("sortOrder") or 0)

    return by_trader


def _scrape_wiki_uses() -> dict[str, str]:
    """
    Scrape the Uses column from the Arc Raiders wiki loot table.

    Returns a mapping of lowercased item name to a uses string describing
    workshop upgrades, expedition requirements, and project-use data.
    Requires the ``scraper`` optional extra (``requests`` + ``beautifulsoup4``).
    Returns an empty dict when the extra is not installed or the page cannot be
    reached.
    """
    if not _SCRAPER_AVAILABLE:
        return {}

    assert _requests is not None and _BeautifulSoup is not None
    _log.info("Fetching wiki loot page from %s", WIKI_LOOT_URL)
    try:
        resp = _requests.get(
            WIKI_LOOT_URL,
            timeout=30,
            headers={"User-Agent": WIKI_USER_AGENT},
        )
        resp.raise_for_status()
    except Exception as exc:
        _log.warning("Wiki fetch failed: %s", exc)
        return {}

    soup = _BeautifulSoup(resp.text, "html.parser")

    loot_table = None
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if "item" in headers and "rarity" in headers and "recycles to" in headers:
            loot_table = table
            break

    if loot_table is None:
        _log.warning("Wiki loot table not found in page from %s", WIKI_LOOT_URL)
        return {}

    header_row = loot_table.find("tr")
    if header_row is None:
        return {}
    headers = [th.get_text(strip=True).lower() for th in header_row.find_all("th")]

    item_col: int | None = None
    uses_col: int | None = None
    for i, h in enumerate(headers):
        if h == "item":
            item_col = i
        elif h == "uses":
            uses_col = i

    if item_col is None or uses_col is None:
        _log.warning("Wiki loot table missing 'item' or 'uses' columns; found: %s", headers)
        return {}

    uses_map: dict[str, str] = {}
    for row in loot_table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) <= max(item_col, uses_col):
            continue

        item_cell = cells[item_col]
        name_link = item_cell.find("a")
        name = name_link.get_text(strip=True) if name_link else item_cell.get_text(strip=True)
        if not name:
            continue

        uses_cell = cells[uses_col]
        uses_text = uses_cell.get_text(" ", strip=True)
        uses_text = re.sub(r"\s+", " ", uses_text.replace("\u00d7", "x")).strip()
        if uses_text:
            uses_map[name.lower()] = uses_text

    _log.info("Wiki: scraped uses data for %d items", len(uses_map))
    return uses_map


def _enrich_items_with_wiki(items: list[dict], uses_map: dict[str, str]) -> tuple[list[dict], int]:
    """
    Merge wiki uses data into items in-place.

    Adds a ``wikiUses`` field to each item that has a matching entry in
    *uses_map* (keyed by lowercased item name).  Returns the enriched list and
    the number of items that received a non-empty ``wikiUses`` value.
    """
    enriched_count = 0
    result: list[dict] = []
    for item in items:
        name = (item.get("name") or "").lower()
        uses = uses_map.get(name, "")
        if uses:
            item = {**item, "wikiUses": uses}
            enriched_count += 1
        result.append(item)
    return result, enriched_count


def update_data_snapshot(data_dir: Path | None = None) -> dict:
    data_dir = data_dir or DATA_DIR
    (data_dir / "static").mkdir(parents=True, exist_ok=True)

    metaforge_items: list[dict] | None = None
    metaforge_quests: list[dict] | None = None
    metaforge_items_error: str | None = None
    metaforge_quests_error: str | None = None
    try:
        metaforge_items = _fetch_all_items()
    except DownloadError as exc:
        metaforge_items_error = str(exc)
        _log.warning("MetaForge items unavailable: %s", exc)
    try:
        metaforge_quests = _fetch_all_quests()
    except DownloadError as exc:
        metaforge_quests_error = str(exc)
        _log.warning("MetaForge quests unavailable: %s", exc)

    fallback_items: list[dict] = []
    fallback_quests: list[dict] = []
    fallback_error: str | None = None
    try:
        fallback_items, fallback_quests = _load_raidtheory_fallback_data()
    except DownloadError as exc:
        fallback_error = str(exc)
        _log.warning("RaidTheory fallback unavailable: %s", exc)

    mapped_metaforge_items = (
        [_map_metaforge_item(item) for item in metaforge_items] if metaforge_items is not None else []
    )
    mapped_metaforge_quests = (
        [_map_metaforge_quest(quest) for quest in metaforge_quests] if metaforge_quests is not None else []
    )

    mapped_items, supplemental_item_count = _merge_missing_entries(
        mapped_metaforge_items,
        fallback_items,
    )
    mapped_quests, supplemental_quest_count = _merge_missing_entries(
        mapped_metaforge_quests,
        fallback_quests,
    )

    if not mapped_items and metaforge_items is None and fallback_error is not None:
        raise DownloadError("Unable to load item data from MetaForge or RaidTheory fallback")
    if not mapped_quests and metaforge_quests is None and fallback_error is not None:
        raise DownloadError("Unable to load quest data from MetaForge or RaidTheory fallback")

    mapped_quests = apply_quest_overrides(mapped_quests)

    # Fetch arctracker.io data for enrichment
    arctracker_items: list[dict] | None = None
    arctracker_quests: list[dict] | None = None
    arctracker_hideout: list[dict] | None = None
    arctracker_projects: list[dict] | None = None
    arctracker_items_error: str | None = None
    arctracker_quests_error: str | None = None
    arctracker_hideout_error: str | None = None
    arctracker_projects_error: str | None = None

    try:
        arctracker_items = _fetch_arctracker_items()
        _log.info("Fetched %d items from arctracker.io", len(arctracker_items))
    except DownloadError as exc:
        arctracker_items_error = str(exc)
        _log.warning("ArcTracker items unavailable: %s", exc)

    try:
        arctracker_quests = _fetch_arctracker_quests()
        _log.info("Fetched %d quests from arctracker.io", len(arctracker_quests))
    except DownloadError as exc:
        arctracker_quests_error = str(exc)
        _log.warning("ArcTracker quests unavailable: %s", exc)

    try:
        arctracker_hideout = _fetch_arctracker_hideout()
        _log.info("Fetched %d hideout modules from arctracker.io", len(arctracker_hideout))
    except DownloadError as exc:
        arctracker_hideout_error = str(exc)
        _log.warning("ArcTracker hideout unavailable: %s", exc)

    try:
        arctracker_projects = _fetch_arctracker_projects()
        _log.info("Fetched %d projects from arctracker.io", len(arctracker_projects))
    except DownloadError as exc:
        arctracker_projects_error = str(exc)
        _log.warning("ArcTracker projects unavailable: %s", exc)

    # Map arctracker data
    mapped_arctracker_items = (
        [mapped for item in arctracker_items if (mapped := _map_arctracker_item(item)) is not None]
        if arctracker_items is not None
        else []
    )
    mapped_arctracker_quests = (
        [mapped for quest in arctracker_quests if (mapped := _map_arctracker_quest(quest)) is not None]
        if arctracker_quests is not None
        else []
    )

    # Merge arctracker data as supplemental (like RaidTheory fallback)
    mapped_items, arctracker_supplemental_items = _merge_missing_entries(
        mapped_items,
        mapped_arctracker_items,
    )
    mapped_quests, arctracker_supplemental_quests = _merge_missing_entries(
        mapped_quests,
        mapped_arctracker_quests,
    )

    # Save hideout and projects data from arctracker
    if arctracker_hideout:
        (data_dir / "static" / "arctracker_hideout.json").write_bytes(
            orjson.dumps(arctracker_hideout, option=orjson.OPT_INDENT_2)
        )
    if arctracker_projects:
        (data_dir / "static" / "arctracker_projects.json").write_bytes(
            orjson.dumps(arctracker_projects, option=orjson.OPT_INDENT_2)
        )

    wiki_uses_map = _scrape_wiki_uses()
    wiki_error: str | None = None
    wiki_enriched_count = 0
    if wiki_uses_map:
        mapped_items, wiki_enriched_count = _enrich_items_with_wiki(mapped_items, wiki_uses_map)
    elif _SCRAPER_AVAILABLE:
        wiki_error = "Wiki fetch returned no usable data"

    (data_dir / "items.json").write_bytes(orjson.dumps(mapped_items, option=orjson.OPT_INDENT_2))
    (data_dir / "quests.json").write_bytes(orjson.dumps(mapped_quests, option=orjson.OPT_INDENT_2))

    quests_by_trader = {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "quests.json",
        "traders": _build_quests_by_trader(mapped_quests),
    }
    (data_dir / "quests_by_trader.json").write_bytes(orjson.dumps(quests_by_trader, option=orjson.OPT_INDENT_2))

    item_source = "metaforge"
    if metaforge_items is None:
        item_source = "raidtheory-fallback"
    elif supplemental_item_count:
        item_source = "metaforge+raidtheory"

    quest_source = "metaforge"
    if metaforge_quests is None:
        quest_source = "raidtheory-fallback"
    elif supplemental_quest_count:
        quest_source = "metaforge+raidtheory"

    # Update source names if arctracker contributed data
    if arctracker_supplemental_items > 0:
        item_source = f"{item_source}+arctracker"
    if arctracker_supplemental_quests > 0:
        quest_source = f"{quest_source}+arctracker"

    metadata = {
        "lastUpdated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": METAFORGE_API_DOCS_URL,
        "version": "autoscrapper-data-1",
        "itemCount": len(mapped_items),
        "questCount": len(mapped_quests),
        "dataSources": {
            "items": {
                "provider": item_source,
                "primary": {
                    "documentation": METAFORGE_API_DOCS_URL,
                    "apiBase": METAFORGE_API_BASE,
                    "error": metaforge_items_error,
                },
                "fallback": {
                    "repository": RAIDTHEORY_REPO_URL,
                    "archive": RAIDTHEORY_ARCHIVE_URL,
                    "supplementalCount": supplemental_item_count,
                    "error": fallback_error,
                },
                "arctrackerEnrichment": {
                    "documentation": ARCTRACKER_API_DOCS_URL,
                    "apiBase": ARCTRACKER_BASE_URL,
                    "supplementalCount": arctracker_supplemental_items,
                    "error": arctracker_items_error,
                },
                "wikiEnrichment": {
                    "url": WIKI_LOOT_URL,
                    "available": _SCRAPER_AVAILABLE,
                    "enrichedCount": wiki_enriched_count,
                    "error": wiki_error,
                    "fields": ["wikiUses"],
                },
            },
            "quests": {
                "provider": quest_source,
                "primary": {
                    "documentation": METAFORGE_API_DOCS_URL,
                    "apiBase": METAFORGE_API_BASE,
                    "error": metaforge_quests_error,
                },
                "fallback": {
                    "repository": RAIDTHEORY_REPO_URL,
                    "archive": RAIDTHEORY_ARCHIVE_URL,
                    "supplementalCount": supplemental_quest_count,
                    "error": fallback_error,
                },
                "arctrackerEnrichment": {
                    "documentation": ARCTRACKER_API_DOCS_URL,
                    "apiBase": ARCTRACKER_BASE_URL,
                    "supplementalCount": arctracker_supplemental_quests,
                    "error": arctracker_quests_error,
                },
            },
            "hideout": {
                "arctracker": {
                    "documentation": ARCTRACKER_API_DOCS_URL,
                    "apiBase": ARCTRACKER_BASE_URL,
                    "count": len(arctracker_hideout) if arctracker_hideout else 0,
                    "error": arctracker_hideout_error,
                    "file": "static/arctracker_hideout.json",
                },
            },
            "projects": {
                "arctracker": {
                    "documentation": ARCTRACKER_API_DOCS_URL,
                    "apiBase": ARCTRACKER_BASE_URL,
                    "count": len(arctracker_projects) if arctracker_projects else 0,
                    "error": arctracker_projects_error,
                    "file": "static/arctracker_projects.json",
                },
            },
        },
        # Kept for compatibility with older metadata consumers.
        "hasPriceOverrides": False,
    }
    (data_dir / "metadata.json").write_bytes(orjson.dumps(metadata, option=orjson.OPT_INDENT_2))

    return metadata
