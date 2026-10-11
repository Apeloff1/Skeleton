"""Actual-cost and phase-aware route planning over ten spatial worlds.

Dijkstra expands real game movement transitions. Routes cannot ignore fuel,
oxygen, danger or adjacency; executing a route refuses stale receipts and
won't partially apply a route that cannot fit the current action budget.
"""
from __future__ import annotations
from dataclasses import dataclass
import heapq

from .original_foundation_compiler import FoundationError
from .original_world_tenfold_runtime import (
    TenfoldAction, TenfoldState, _navigation, passages,
    step_tenfold, validate_tenfold,
)

MODES = ("balanced", "fastest", "safest", "fuel-frugal")
MAX_SEARCH = 4096


@dataclass(frozen=True)
class RoutePlan:
    start: int
    destination: int
    nodes: tuple[int, ...]
    energy: int
    fuel: int
    oxygen: int
    danger: int
    moves: int
    immediate: bool
    priority: str
    snapshot_tick: int
    snapshot_head: str
    search_states: int

    def as_dict(self) -> dict:
        return {
            "start": self.start, "destination": self.destination,
            "nodes": list(self.nodes),
            "energy_cost": self.energy, "fuel_cost": self.fuel,
            "oxygen_cost": self.oxygen, "added_hazard": self.danger,
            "movement_actions": self.moves,
            "can_finish_this_turn": self.immediate,
            "priority": self.priority, "snapshot_tick": self.snapshot_tick,
            "snapshot_head": self.snapshot_head,
            "search_states": self.search_states,
            "note": "Current-phase topology; changes invalidate this route.",
        }


def _priority_cost(priority: str, energy: int, fuel: int,
                   oxygen: int, danger: int, hops: int) -> int:
    if priority == "fastest":
        return hops * 100 + energy + fuel + oxygen + danger
    if priority == "safest":
        return hops + danger * 100 + oxygen * 10 + fuel * 3 + energy
    if priority == "fuel-frugal":
        return hops + fuel * 100 + oxygen * 10 + energy * 3 + danger * 5
    return hops * 4 + energy * 5 + fuel * 8 + oxygen * 8 + danger * 12


def plan_tenfold_route(
    state: TenfoldState, destination: int, *, priority: str = "balanced",
) -> RoutePlan:
    validate_tenfold(state)
    if priority not in MODES:
        raise FoundationError("invalid route optimization objective")
    if type(destination) is not int or not 0 <= destination < 24:
        raise FoundationError("destination outside world graph")
    if state.position == destination:
        return RoutePlan(state.position, destination, (state.position,),
                         0, 0, 0, 0, 0, True, priority,
                         state.tick, state.event_head, 0)
    counter = 0
    start = state
    queue = [(0, 0, counter, (start.position,), start)]
    best = {}
    while queue:
        cost, hops, _, path, cursor = heapq.heappop(queue)
        label = (cursor.position, cursor.game.causal.energy,
                 cursor.fuel, cursor.oxygen, cursor.danger)
        if best.get(label, cost) < cost:
            continue
        if cursor.position == destination:
            return RoutePlan(
                start.position, destination, path,
                start.game.causal.energy - cursor.game.causal.energy,
                start.fuel - cursor.fuel,
                start.oxygen - cursor.oxygen,
                cursor.danger - start.danger, hops,
                hops <= start.game.causal.action_points,
                priority, start.tick, start.event_head, counter,
            )
        if counter >= MAX_SEARCH:
            raise FoundationError("route search budget exhausted")
        for adjacent in passages(cursor):
            if adjacent in path:
                continue
            try:
                candidate, _ = _navigation(cursor, adjacent)
            except FoundationError:
                continue
            new_path = path + (adjacent,)
            energy = start.game.causal.energy - candidate.game.causal.energy
            fuel = start.fuel - candidate.fuel
            oxygen = start.oxygen - candidate.oxygen
            danger = candidate.danger - start.danger
            new_cost = _priority_cost(priority, energy, fuel, oxygen, danger,
                                      len(new_path) - 1)
            key = (candidate.position, candidate.game.causal.energy,
                   candidate.fuel, candidate.oxygen, candidate.danger)
            if new_cost >= best.get(key, 10**15):
                continue
            best[key] = new_cost
            counter += 1
            heapq.heappush(queue, (new_cost, len(new_path) - 1,
                                   counter, new_path, candidate))
    raise FoundationError("no route within current physical resource budget")


def execute_tenfold_route(
    state: TenfoldState, plan: RoutePlan,
) -> tuple[TenfoldState, tuple[str, ...]]:
    validate_tenfold(state)
    if not isinstance(plan, RoutePlan):
        raise FoundationError("route receipt is missing")
    if (plan.start != state.position or plan.snapshot_tick != state.tick
            or plan.snapshot_head != state.event_head):
        raise FoundationError("stale route plan; recompute after state changes")
    if not plan.immediate or plan.moves > state.game.causal.action_points:
        raise FoundationError("route needs extra turns; refuse partial execution")
    if (not plan.nodes or plan.nodes[0] != state.position
            or plan.nodes[-1] != plan.destination):
        raise FoundationError("route endpoints do not match receipt")
    candidate, receipts = state, []
    for next_room in plan.nodes[1:]:
        candidate, event = step_tenfold(
            candidate, TenfoldAction("spatial", "travel", target=next_room))
        receipts.append(event.event_id)
    if (state.game.causal.energy - candidate.game.causal.energy != plan.energy
            or state.fuel - candidate.fuel != plan.fuel
            or state.oxygen - candidate.oxygen != plan.oxygen
            or candidate.danger - state.danger != plan.danger):
        raise FoundationError("executed route differs from verified physical budget")
    return candidate, tuple(receipts)
