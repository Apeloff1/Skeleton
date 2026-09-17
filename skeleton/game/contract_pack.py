"""Named contracts."""

from __future__ import annotations

from typing import Any


class ContractPackError(ValueError):
    pass


CTS: dict[str, tuple[str, int]] = {
    f"ct_{i:02d}": (("heat", "sleep", "key", "coil", "xp", "scrap", "alert", "floor")[i % 8], 1 + (i % 8))
    for i in range(20)
}


def open_ct(name: str, seed: int) -> dict[str, Any]:
    if name not in CTS:
        raise ContractPackError(name)
    stat, need = CTS[name]
    return {"ct": name, "stat": stat, "need": need, "done": False, "seed": int(seed), "stored_prose": 0}


def tick_ct(card: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    name = str(card.get("ct") or "")
    if name not in CTS:
        raise ContractPackError(name)
    nxt = dict(card)
    nxt["done"] = int(state.get(nxt.get("stat") or "heat", 0)) >= int(nxt.get("need") or 1)
    nxt["stored_prose"] = 0
    return nxt
