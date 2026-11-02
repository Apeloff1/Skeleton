"""Bounded deterministic planner for real Lantern Quay gathering, NPC trade and delivery.

The solver uses the same collision and state transition code as the player.
It is not a symbolic success receipt: every proposed move and craft is
executed and the final replay is independently verified before publication.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any, Callable

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, canonical, digest, export_bundle,
    initial_state, step, validate_source, verify_bundle,
)

PLAN_SCHEMA = "skeleton.game.harbor.plan.v1"
MAX_ROUTE_NODES = 4096
MOVES = (
    {"op": "move", "direction": "north"},
    {"op": "move", "direction": "east"},
    {"op": "move", "direction": "south"},
    {"op": "move", "direction": "west"},
    {"op": "wait"},
)


def _distance(a: list[int], b: list[int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _route(
    source: dict[str, Any],
    start: dict[str, Any],
    reached: Callable[[dict[str, Any]], bool],
) -> list[dict[str, str]]:
    """Time-expanded BFS accounts for moving NPC collision and wait actions."""
    queue = deque([(start, [])])
    period = len(source["npc"]["route"])
    def key(state: dict[str, Any]) -> tuple[Any, ...]:
        return (tuple(state["pos"]), tuple(state["npc_pos"]), state["tick"] % period)
    seen: set[tuple[Any, ...]] = {key(start)}
    while queue:
        state, actions = queue.popleft()
        if reached(state):
            return actions
        if state["tick"] >= source["max_ticks"]:
            continue
        for action in MOVES:
            try:
                after = step(source, state, action)
            except HarborError:
                continue
            identity = key(after)
            if identity in seen:
                continue
            if len(seen) >= MAX_ROUTE_NODES:
                raise HarborError("bounded route solver state budget exhausted")
            seen.add(identity)
            queue.append((after, actions + [action]))
    raise HarborError("bounded route solver could not reach objective")


class _CampaignPlanner:
    def __init__(self, source: dict[str, Any]):
        self.source = validate_source(source)
        self.state = initial_state(self.source)
        self.actions: list[dict[str, str]] = []

    def emit(self, action: dict[str, str]) -> None:
        self.state = step(self.source, self.state, action)
        self.actions.append(deepcopy(action))

    def navigate(self, goal: Callable[[dict[str, Any]], bool]) -> None:
        for action in _route(self.source, self.state, goal):
            self.emit(action)

    def ensure(self, item: str, required: int, active: frozenset[str] = frozenset()) -> None:
        if item in active:
            raise HarborError("cyclic crafting dependency")
        if required > 64:
            raise HarborError("required inventory exceeds capacity")
        while self.state["inventory"].get(item, 0) < required:
            resource = next(
                (r for r in self.source["resources"]
                 if r["id"] == item and self.state["stock"][item] > 0),
                None,
            )
            if resource is not None:
                target = resource["at"]
                self.navigate(lambda state: state["pos"] == target)
                self.emit({"op": "gather"})
                continue
            if self.state["npc_stock"].get(item, 0) > 0:
                if self.state["coins"] < self.source["npc"]["price"]:
                    raise HarborError("merchant price exceeds remaining coins")
                self.navigate(
                    lambda state: _distance(state["pos"], state["npc_pos"]) == 1
                )
                self.emit({"op": "trade", "item": item})
                continue
            recipes = sorted(
                (r for r in self.source["recipes"] if item in r["output"]),
                key=lambda r: r["id"],
            )
            if not recipes:
                raise HarborError("no available source for required item")
            recipe = recipes[0]
            for material, quantity in sorted(recipe["inputs"].items()):
                self.ensure(
                    material,
                    self.state["inventory"].get(material, 0) + quantity,
                    active | {item},
                )
            self.emit({"op": "craft", "recipe": recipe["id"]})


def solve(source: Any, *, choice: str = "signal") -> dict[str, Any]:
    """Produce actual winning actions or fail with no fabricated completion."""
    if choice not in ("signal", "shelter") or type(choice) is not str:
        raise HarborError("unsupported victory choice")
    planner = _CampaignPlanner(source)
    for item, quantity in sorted(planner.source["delivery"].items()):
        planner.ensure(item, quantity)
    dock = planner.source["dock"]
    planner.navigate(lambda state: _distance(state["pos"], dock) == 1)
    planner.emit({"op": "deliver"})
    planner.emit({"op": "choose", "choice": choice})
    bundle = export_bundle(planner.source, planner.actions, require_win=True)
    if verify_bundle(bundle, require_win=True) != planner.state:
        raise HarborError("solver/replay state divergence")
    plan = {
        "schema": PLAN_SCHEMA,
        "choice": choice,
        "actions": deepcopy(planner.actions),
        "bundle": bundle,
        "source_digest": digest(planner.source),
    }
    plan["plan_digest"] = digest(plan)
    if len(canonical(plan)) > MAX_BUNDLE_BYTES:
        raise HarborError("solver output exceeds byte limit")
    return plan


def verify_plan(plan: Any) -> dict[str, Any]:
    """Re-run the solver, player transitions, and full portable event replay."""
    if not isinstance(plan, dict) or set(plan) != {
        "schema", "choice", "actions", "bundle", "source_digest", "plan_digest"
    }:
        raise HarborError("invalid solver plan fields")
    if plan["schema"] != PLAN_SCHEMA or len(canonical(plan)) > MAX_BUNDLE_BYTES:
        raise HarborError("invalid solver plan schema or size")
    if plan["plan_digest"] != digest({k: v for k, v in plan.items() if k != "plan_digest"}):
        raise HarborError("solver plan digest mismatch")
    bundle = plan["bundle"]
    state = verify_bundle(bundle, require_win=True)
    if plan["source_digest"] != bundle["source_digest"]:
        raise HarborError("solver source identity mismatch")
    if solve(bundle["source"], choice=plan["choice"]) != plan:
        raise HarborError("solver plan replay mismatch")
    return state
