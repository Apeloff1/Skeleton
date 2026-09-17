"""Scrap/parts economy. Trading is barter. No currency network."""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.game.craft_graph import CraftGraphError, default_book, plan


class EconomySimError(ValueError):
    """Economy sim contract violation."""


def _bag(raw: Mapping[str, int] | None) -> dict[str, int]:
    bag = {"scrap": 0, "parts": 0, "coil": 0, "sink": 0, "extract_key": 0, "bait": 0}
    for key, value in dict(raw or {}).items():
        if key not in bag:
            raise EconomySimError(f"unknown good {key}")
        if int(value) < 0:
            raise EconomySimError("negative stock")
        bag[key] = int(value)
    return bag


def scavenge(bag: Mapping[str, int], heat: int) -> dict[str, int]:
    nxt = _bag(bag)
    nxt["scrap"] += 1 + max(0, int(heat)) // 20
    return nxt


def trade(bag: Mapping[str, int], give: str, take: str) -> dict[str, int]:
    nxt = _bag(bag)
    if give == take:
        raise EconomySimError("noop trade")
    if nxt.get(give, 0) < 1:
        raise EconomySimError("cannot afford trade")
    nxt[give] -= 1
    nxt[take] = nxt.get(take, 0) + 1
    return nxt


def craft(bag: Mapping[str, int], target: str) -> dict[str, Any]:
    nxt = _bag(bag)
    try:
        built = plan(default_book(), target, nxt)
    except CraftGraphError as exc:
        raise EconomySimError(str(exc)) from exc
    return {"bag": built["bag"], "order": built["order"], "stored_prose": 0}


def run(actions: list[Mapping[str, Any]], *, heat: int = 20) -> dict[str, Any]:
    bag = _bag(None)
    log: list[str] = []
    for raw in actions:
        verb = str(raw.get("verb") or "")
        if verb == "scavenge":
            bag = scavenge(bag, heat)
            log.append("scavenge")
        elif verb == "trade":
            bag = trade(bag, str(raw.get("give") or "scrap"), str(raw.get("take") or "parts"))
            log.append("trade")
        elif verb == "craft":
            built = craft(bag, str(raw.get("target") or "coil"))
            bag = _bag(built["bag"])
            log.append("craft")
        else:
            raise EconomySimError(f"unknown econ verb {verb}")
    return {
        "kind": "economy_sim",
        "bag": bag,
        "log": log,
        "key": bag.get("extract_key", 0) > 0,
        "stored_prose": 0,
    }
