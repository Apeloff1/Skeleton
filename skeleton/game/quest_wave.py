"""Wave-4 pointer quests."""

from __future__ import annotations

from typing import Any


class QuestWaveError(ValueError):
    pass


QUESTS: dict[str, tuple[str, int]] = {
    f"q_{i:02d}": (("heat", "sleep", "key", "coil", "xp", "scrap", "alert", "floor")[i % 8], 1 + (i % 8))
    for i in range(28)
}


def open_quest(name: str, seed: int) -> dict[str, Any]:
    if name not in QUESTS:
        raise QuestWaveError(name)
    stat, need = QUESTS[name]
    return {"quest": name, "stat": stat, "need": need, "done": False, "seed": int(seed), "stored_prose": 0}


def tick_quest(card: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    name = str(card.get("quest") or "")
    if name not in QUESTS:
        raise QuestWaveError(name)
    stat, need = QUESTS[name]
    nxt = dict(card)
    nxt["done"] = int(state.get(stat, 0)) >= need
    nxt["stored_prose"] = 0
    return nxt
