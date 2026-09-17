"""Craft DAG. Cycle-closed. Scrap+parts in, item out. No coin."""

from __future__ import annotations

from typing import Any, Mapping


MAX_RECIPES = 64
MAX_DEPTH = 8


class CraftGraphError(ValueError):
    """Craft graph contract violation."""


def _norm(recipes: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if len(recipes) > MAX_RECIPES:
        raise CraftGraphError("too many recipes")
    out = []
    seen: set[str] = set()
    for raw in recipes:
        rid = str(raw.get("id") or "")
        inputs = tuple(str(item) for item in (raw.get("in") or ()))
        product = str(raw.get("out") or "")
        heat = int(raw.get("heat") or 0)
        if not rid or not product or not inputs:
            raise CraftGraphError("recipe missing id/in/out")
        if rid in seen:
            raise CraftGraphError("duplicate recipe")
        seen.add(rid)
        out.append({"id": rid, "inputs": inputs, "out": product, "heat": heat})
    return out


def cycles(recipes: list[Mapping[str, Any]]) -> list[str]:
    rows = _norm(recipes)
    produced = {row["out"]: row["id"] for row in rows}
    graph = {row["id"]: [produced[item] for item in row["inputs"] if item in produced] for row in rows}
    seen: set[str] = set()
    stack: set[str] = set()
    bad: list[str] = []

    def walk(node: str) -> None:
        if node in stack:
            bad.append(node)
            return
        if node in seen:
            return
        seen.add(node)
        stack.add(node)
        for nxt in graph.get(node, ()):
            walk(nxt)
        stack.discard(node)

    for node in graph:
        walk(node)
    return bad


def plan(recipes: list[Mapping[str, Any]], target: str, bag: Mapping[str, int]) -> dict[str, Any]:
    rows = _norm(recipes)
    looped = cycles(rows)
    if looped:
        raise CraftGraphError(f"cycle at {looped[0]}")
    by_out = {row["out"]: row for row in rows}
    need = dict(bag)
    order: list[str] = []

    def ensure(item: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise CraftGraphError("craft depth exceeded")
        if need.get(item, 0) > 0:
            return
        if item not in by_out:
            raise CraftGraphError(f"missing ingredient {item}")
        recipe = by_out[item]
        for ingredient in recipe["inputs"]:
            ensure(ingredient, depth + 1)
            have = need.get(ingredient, 0)
            if have < 1:
                raise CraftGraphError(f"cannot pay {ingredient}")
            need[ingredient] = have - 1
        need[item] = need.get(item, 0) + 1
        order.append(recipe["id"])

    ensure(target, 0)
    return {
        "kind": "craft_plan",
        "target": target,
        "order": order,
        "bag": need,
        "ok": True,
        "stored_prose": 0,
    }


def default_book() -> list[dict[str, Any]]:
    return [
        {"id": "r_coil", "in": ("scrap", "scrap"), "out": "coil", "heat": 2},
        {"id": "r_sink", "in": ("coil", "parts"), "out": "sink", "heat": 3},
        {"id": "r_key", "in": ("sink", "parts"), "out": "extract_key", "heat": 4},
        {"id": "r_bait", "in": ("scrap", "parts"), "out": "bait", "heat": 1},
    ]
