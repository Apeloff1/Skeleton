"""Named work orders."""

from __future__ import annotations

from typing import Any


class WorkorderPackError(ValueError):
    pass


WO: dict[str, tuple[str, int]] = {
    f"wo_{i:02d}": (("heat", "xp", "parts", "scrap", "coil", "key")[i % 6], 1 + (i % 6))
    for i in range(28)
}


def open_wo(name: str, seed: int) -> dict[str, Any]:
    if name not in WO:
        raise WorkorderPackError(name)
    stat, need = WO[name]
    return {"wo": name, "stat": stat, "need": need, "done": False, "seed": int(seed), "stored_prose": 0}


def tick_wo(card: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    nxt = dict(card)
    nxt["done"] = int(state.get(nxt.get("stat") or "heat", 0)) >= int(nxt.get("need") or 1)
    nxt["stored_prose"] = 0
    return nxt
