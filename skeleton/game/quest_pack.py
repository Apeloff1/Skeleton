"""Named pointer quests. Threshold ticks."""

from __future__ import annotations

from typing import Any


class QuestPackError(ValueError):
    pass


QUESTS: dict[str, tuple[str, int, bool]] = {
    "stoke_heat": ("heat", 8, False),
    "sleep_full": ("sleep", 8, False),
    "find_key": ("key", 1, False),
    "craft_coil": ("coil", 1, False),
    "bait_drop": ("bait", 1, False),
    "extract_gate": ("extracted", 1, False),
    "learn_ward": ("xp", 8, False),
    "calm_hall": ("alert", 0, True),
    "feed_forge": ("scrap", 4, False),
    "open_lock": ("locked", 0, True),
    "climb_shaft": ("floor", 3, False),
    "clear_fog": ("los_pen", 0, True),
    "save_slot": ("saved", 1, False),
    "mark_prey": ("alert", 3, False),
    "hide_cell": ("alert", 0, True),
    "vent_peak": ("heat", 4, False),
    "dream_once": ("slept", 1, False),
    "barter_parts": ("parts", 1, False),
    "squad_contact": ("contacts", 1, False),
    "monte_four": ("unique", 4, False),
    "path_extract": ("path_len", 2, False),
    "bundle_seal": ("digest", 1, False),
    "warp_once": ("warp_count", 1, False),
}


def open_quest(name: str, seed: int) -> dict[str, Any]:
    if name not in QUESTS:
        raise QuestPackError(name)
    stat, need, lte = QUESTS[name]
    return {"quest": name, "stat": stat, "need": need, "lte": lte, "done": False, "seed": int(seed), "stored_prose": 0}


def tick_quest(card: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    name = str(card.get("quest") or "")
    if name not in QUESTS:
        raise QuestPackError(name)
    stat, need, lte = QUESTS[name]
    nxt = dict(card)
    raw = state.get(stat, 0)
    have = int(raw) if not isinstance(raw, str) else (1 if raw else 0)
    nxt["done"] = have <= need if lte else have >= need
    nxt["stored_prose"] = 0
    return nxt


def run(name: str, seed: int, state: dict[str, Any]) -> dict[str, Any]:
    card = tick_quest(open_quest(name, seed), state)
    return {"kind": "quest_pack", "quest": name, "done": bool(card.get("done")), "stored_prose": 0}
