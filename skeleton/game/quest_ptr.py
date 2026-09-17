"""Quest pointer chains. Complete-once."""

from __future__ import annotations

from typing import Any


class QuestPtrError(ValueError):
    pass


QUESTS = {
    "find_scrap": ("scrap", 1),
    "stoke_heat": ("heat", 8),
    "craft_once": ("parts", 1),
    "sleep_once": ("slept", 1),
    "dream_once": ("dreams", 1),
    "unlock_door": ("key", 1),
    "reach_extract": ("extracted", 1),
}


def open_quest(name: str, seed: int) -> dict[str, Any]:
    if name not in QUESTS:
        raise QuestPtrError(name)
    need, n = QUESTS[name]
    return {"quest": name, "need": need, "need_n": n, "done": False, "seed": int(seed), "stored_prose": 0}


def tick_quest(card: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    name = str(card.get("quest") or "")
    if name not in QUESTS:
        raise QuestPtrError(name)
    need, n = QUESTS[name]
    nxt = dict(card)
    nxt["done"] = int(state.get(need, 0)) >= n
    nxt["stored_prose"] = 0
    return nxt
