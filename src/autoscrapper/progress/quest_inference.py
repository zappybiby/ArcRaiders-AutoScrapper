from __future__ import annotations

from collections import deque
import re
from typing import Dict, Iterable, List, Set, Tuple

from .progress_config import build_quest_index, group_quests_by_trader, resolve_active_quests


def _normalize_quest_name(value: str) -> str:
    normalized = str(value or "").lower().replace("'", "").replace("’", "")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _build_predecessors_by_id(
    quests: List[dict], quest_graph: Dict[str, object]
) -> Dict[str, Set[str]]:
    nodes = quest_graph.get("nodes")
    edges = quest_graph.get("edges")
    if not isinstance(nodes, dict) or not isinstance(edges, list):
        raise ValueError("Invalid quest graph format.")

    quest_id_by_name: Dict[str, str] = {}
    for quest in quests:
        quest_id = quest.get("id")
        quest_name = quest.get("name")
        if not quest_id or not quest_name:
            continue
        normalized_name = _normalize_quest_name(str(quest_name))
        existing = quest_id_by_name.get(normalized_name)
        if existing and existing != str(quest_id):
            raise ValueError(f"Duplicate quest name in data: {quest_name}")
        quest_id_by_name[normalized_name] = str(quest_id)

    node_to_quest_id: Dict[str, str] = {}
    unresolved_nodes: List[str] = []
    for node_id, node_name in nodes.items():
        if not isinstance(node_id, str):
            continue
        resolved = quest_id_by_name.get(_normalize_quest_name(str(node_name)))
        if resolved:
            node_to_quest_id[node_id] = resolved
        else:
            unresolved_nodes.append(node_id)

    if unresolved_nodes:
        examples = ", ".join(sorted(unresolved_nodes)[:5])
        raise ValueError(
            "Quest graph contains nodes that could not be matched to quests: "
            f"{examples}"
        )

    predecessors: Dict[str, Set[str]] = {}
    for quest in quests:
        quest_id = quest.get("id")
        if quest_id:
            predecessors[str(quest_id)] = set()

    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            continue
        src_node, dst_node = edge
        if not isinstance(src_node, str) or not isinstance(dst_node, str):
            continue
        src_id = node_to_quest_id.get(src_node)
        dst_id = node_to_quest_id.get(dst_node)
        if not src_id or not dst_id:
            continue
        predecessors.setdefault(dst_id, set()).add(src_id)

    return predecessors


def _build_trader_sequences(quests: List[dict]) -> Tuple[List[str], Dict[str, List[str]]]:
    quests_by_trader = group_quests_by_trader(quests)
    trader_order = sorted(quests_by_trader.keys())
    sequences: Dict[str, List[str]] = {}
    for trader in trader_order:
        ids = []
        for quest in quests_by_trader[trader]:
            quest_id = quest.get("id")
            if quest_id:
                ids.append(str(quest_id))
        sequences[trader] = ids
    return trader_order, sequences


def _state_completed_ids(
    state: Tuple[int, ...], trader_order: List[str], trader_sequences: Dict[str, List[str]]
) -> List[str]:
    completed: List[str] = []
    for idx, trader in enumerate(trader_order):
        completed.extend(trader_sequences[trader][: state[idx]])
    return completed


def _state_active_signature(
    state: Tuple[int, ...],
    trader_order: List[str],
    trader_sequences: Dict[str, List[str]],
    predecessors_by_id: Dict[str, Set[str]],
) -> Tuple[str, ...]:
    completed = set(_state_completed_ids(state, trader_order, trader_sequences))
    active: List[str] = []
    for idx, trader in enumerate(trader_order):
        line = trader_sequences[trader]
        cursor = state[idx]
        if cursor >= len(line):
            continue
        next_quest_id = line[cursor]
        predecessors = predecessors_by_id.get(next_quest_id, set())
        if predecessors.issubset(completed):
            active.append(next_quest_id)
    return tuple(sorted(active))


def _resolve_active_ids(quests: List[dict], active_quests: Iterable[str]) -> Set[str]:
    quests_by_trader = group_quests_by_trader(quests)
    quest_index = build_quest_index(quests_by_trader)
    active_resolved, missing = resolve_active_quests(list(active_quests), quest_index)
    if missing:
        raise ValueError(f"Active quests not found: {', '.join(missing)}")
    return {str(quest.get('id')) for quest in active_resolved if quest.get("id")}


def infer_completed_from_active(
    quests: List[dict], quest_graph: Dict[str, object], active_quests: Iterable[str]
) -> List[str]:
    target_active = tuple(sorted(_resolve_active_ids(quests, active_quests)))
    trader_order, trader_sequences = _build_trader_sequences(quests)
    predecessors_by_id = _build_predecessors_by_id(quests, quest_graph)

    trader_index_by_id: Dict[str, int] = {}
    for idx, trader in enumerate(trader_order):
        for quest_id in trader_sequences[trader]:
            trader_index_by_id[quest_id] = idx

    start_state = tuple(0 for _ in trader_order)
    queue: deque[Tuple[int, ...]] = deque([start_state])
    seen: Set[Tuple[int, ...]] = {start_state}
    matches: List[Tuple[int, ...]] = []

    while queue:
        state = queue.popleft()
        active_signature = _state_active_signature(
            state, trader_order, trader_sequences, predecessors_by_id
        )
        if active_signature == target_active:
            matches.append(state)

        for quest_id in active_signature:
            trader_idx = trader_index_by_id[quest_id]
            next_state = list(state)
            next_state[trader_idx] += 1
            encoded = tuple(next_state)
            if encoded not in seen:
                seen.add(encoded)
                queue.append(encoded)

    if not matches:
        raise ValueError(
            "Active quests do not match a valid quest progression state. "
            "Update your active quests and try again."
        )
    if len(matches) > 1:
        raise ValueError(
            "Active quests map to multiple progression states. "
            "Please review your active quest list."
        )

    return _state_completed_ids(matches[0], trader_order, trader_sequences)
