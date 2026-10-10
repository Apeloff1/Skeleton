"""Deterministic multi-solver route laboratory for original homebrew levels.

This is an actual bounded puzzle solver, not a claim that randomly generated
mazes have multiple independent solutions. It models collectibles in the state,
distinguishes safe versus risky paths, and records inspectable route receipts.
Simulation/release qualification remains with the canonical game-builder.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from hashlib import sha256
from heapq import heappop, heappush
from typing import Mapping, Sequence

from .contracts import canonical_digest
from .playable_world import DIRECTIONS, MAX_COLLECTIBLES, MAX_DIMENSION

Position = tuple[int, int]
State = tuple[int, int, int]
Edge = tuple[Position, Position]
_STEP = {name: (dx, dy) for name, dx, dy in DIRECTIONS}
_MAX_STATES = MAX_DIMENSION * MAX_DIMENSION * (1 << MAX_COLLECTIBLES)
_MAX_PATH_STEPS = 20_000


class MultipathError(ValueError):
    """Invalid grid, solver parameters, or unproven route result."""


@dataclass(frozen=True, slots=True)
class RouteProblem:
    """Bounded source of truth: one start, one goal, 1–6 collectible goals."""

    rows: tuple[str, ...]
    start: Position
    goal: Position
    collectibles: tuple[Position, ...]
    hazards: frozenset[Position]

    @classmethod
    def from_rows(cls, rows: Sequence[str]) -> "RouteProblem":
        if (not isinstance(rows, (list, tuple))
                or not 9 <= len(rows) <= MAX_DIMENSION
                or any(type(row) is not str for row in rows)):
            raise MultipathError("bounded original tile rows required")
        lines = tuple(rows)
        width = len(lines[0])
        if (not 9 <= width <= MAX_DIMENSION or width % 2 == 0
                or len(lines) % 2 == 0
                or any(len(row) != width or set(row) - set("#.SGCH")
                       for row in lines)):
            raise MultipathError("invalid rectangular original tile map")
        if (any(ch != "#" for ch in lines[0] + lines[-1])
                or any(row[0] != "#" or row[-1] != "#" for row in lines)):
            raise MultipathError("sealed map boundaries required")
        markers = {
            tile: [(x, y) for y, row in enumerate(lines)
                   for x, value in enumerate(row) if value == tile]
            for tile in "SGCH"
        }
        if (len(markers["S"]) != 1 or len(markers["G"]) != 1
                or not 1 <= len(markers["C"]) <= MAX_COLLECTIBLES
                or len(markers["H"]) > 24):
            raise MultipathError("map requires unique start/goal and bounded objectives")
        return cls(lines, markers["S"][0], markers["G"][0],
                   tuple(sorted(markers["C"])), frozenset(markers["H"]))

    @property
    def width(self) -> int:
        return len(self.rows[0])

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def digest(self) -> str:
        return canonical_digest({
            "schema": "skeleton.game_builder.route_problem.v1",
            "rows": list(self.rows),
        })

    def tile(self, p: Position) -> str:
        x, y = p
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.rows[y][x]
        return "#"

    def neighbors(self, p: Position, *, allow_hazards: bool) -> tuple[tuple[str, Position], ...]:
        x, y = p
        return tuple(
            (name, (x + dx, y + dy))
            for name, dx, dy in DIRECTIONS
            if self.tile((x + dx, y + dy)) != "#"
            and (allow_hazards or (x + dx, y + dy) not in self.hazards)
        )


@dataclass(frozen=True, slots=True)
class RouteProof:
    problem_digest: str
    solver: str
    actions: tuple[str, ...]
    positions: tuple[Position, ...]
    collectible_order: tuple[Position, ...]
    hazard_visits: int
    cost: int
    expanded_states: int

    @property
    def digest(self) -> str:
        return canonical_digest({
            "schema": "skeleton.game_builder.route_proof.v1",
            "problem": self.problem_digest,
            "solver": self.solver,
            "actions": list(self.actions),
            "positions": [list(p) for p in self.positions],
            "order": [list(p) for p in self.collectible_order],
            "hazard_visits": self.hazard_visits,
            "cost": self.cost,
            "expanded": self.expanded_states,
        })

    @property
    def steps(self) -> int:
        return len(self.actions)


def evaluate_route(
    problem: RouteProblem,
    actions: Sequence[str],
    *, allow_hazards: bool = False,
    hazard_cost: int = 8,
    edge_penalties: Mapping[Edge, int] | None = None,
    solver: str = "replay",
    expanded_states: int = 0,
) -> RouteProof:
    """Execute a complete route against the original grid, fail closed."""
    if (not isinstance(problem, RouteProblem) or not isinstance(actions, (list, tuple))
            or len(actions) > _MAX_PATH_STEPS or not type(hazard_cost) is int
            or not 0 <= hazard_cost <= 1_000_000):
        raise MultipathError("invalid bounded route verification request")
    penalties = _check_penalties(problem, edge_penalties)
    place = problem.start
    positions = [place]
    found: list[Position] = []
    seen: set[Position] = set()
    hazards = 0
    cost = 0
    for action in actions:
        if action not in _STEP:
            raise MultipathError("invalid player input in route")
        dx, dy = _STEP[action]
        next_pos = (place[0] + dx, place[1] + dy)
        tile = problem.tile(next_pos)
        if tile == "#" or (tile == "H" and not allow_hazards):
            raise MultipathError("route crosses an impassable or forbidden tile")
        if tile == "H":
            hazards += 1
        cost += 1 + (hazard_cost if tile == "H" else 0) + penalties.get((place, next_pos), 0)
        if tile == "C" and next_pos not in seen:
            seen.add(next_pos)
            found.append(next_pos)
        place = next_pos
        positions.append(place)
    if place != problem.goal or len(seen) != len(problem.collectibles):
        raise MultipathError("route does not collect all objectives and reach exit")
    return RouteProof(problem.digest, solver, tuple(actions), tuple(positions),
                      tuple(found), hazards, cost, expanded_states)


def _check_penalties(problem: RouteProblem, penalties: Mapping[Edge, int] | None) -> dict[Edge, int]:
    if penalties is None:
        return {}
    if not isinstance(penalties, Mapping) or len(penalties) > 50_000:
        raise MultipathError("invalid bounded edge penalty table")
    out = {}
    for edge, penalty in penalties.items():
        if (not isinstance(edge, tuple) or len(edge) != 2
                or any(not isinstance(p, tuple) or len(p) != 2
                       or any(type(q) is not int for q in p) for p in edge)
                or type(penalty) is not int or not 0 <= penalty <= 1_000_000):
            raise MultipathError("invalid edge penalty entry")
        p, q = edge
        if (problem.tile(p) == "#" or problem.tile(q) == "#"
                or abs(p[0]-q[0]) + abs(p[1]-q[1]) != 1):
            raise MultipathError("edge penalty references a non-walkable transition")
        out[edge] = penalty
    return out


def solve_route(
    problem: RouteProblem, *, algorithm: str = "bfs",
    allow_hazards: bool = False, hazard_cost: int = 8,
    edge_penalties: Mapping[Edge, int] | None = None,
    max_expansions: int = _MAX_STATES,
) -> RouteProof:
    """Shortest or minimum-cost complete collectible route.

    BFS is strictly unit-cost and hazard-free. Dijkstra supports explicit
    hazard penalties and path-diversity penalties, with a bounded state space.
    """
    if not isinstance(problem, RouteProblem):
        raise MultipathError("typed RouteProblem required")
    if algorithm not in ("bfs", "dijkstra") or type(allow_hazards) is not bool:
        raise MultipathError("unknown or invalid route solving policy")
    if type(max_expansions) is not int or not 1 <= max_expansions <= _MAX_STATES:
        raise MultipathError("invalid state expansion budget")
    if type(hazard_cost) is not int or not 0 <= hazard_cost <= 1_000_000:
        raise MultipathError("invalid hazard cost")
    penalties = _check_penalties(problem, edge_penalties)
    if algorithm == "bfs" and (allow_hazards or penalties):
        raise MultipathError("BFS admits only unit-cost hazard-free routes")
    item_bits = {pos: 1 << index for index, pos in enumerate(problem.collectibles)}
    target_mask = (1 << len(item_bits)) - 1
    initial: State = (*problem.start, 0)
    parents: dict[State, tuple[State, str] | None] = {initial: None}
    best = {initial: 0}
    sequence = 0
    priority: list[tuple[int, int, State]] = [(0, sequence, initial)]
    expanded = 0
    terminal: State | None = None
    while priority:
        dist, _, state = heappop(priority)
        if dist != best.get(state):
            continue
        expanded += 1
        if expanded > max_expansions:
            raise MultipathError("route search expansion budget exhausted")
        x, y, mask = state
        if (x, y) == problem.goal and mask == target_mask:
            terminal = state
            break
        for action, next_pos in problem.neighbors((x, y), allow_hazards=allow_hazards):
            new_mask = mask | item_bits.get(next_pos, 0)
            nxt: State = (*next_pos, new_mask)
            delta = 1 + (hazard_cost if next_pos in problem.hazards else 0)
            delta += penalties.get(((x, y), next_pos), 0)
            proposed = dist + delta
            if proposed >= best.get(nxt, 2**63):
                continue
            best[nxt] = proposed
            parents[nxt] = (state, action)
            sequence += 1
            heappush(priority, (proposed, sequence, nxt))
        if len(parents) > _MAX_STATES:
            raise MultipathError("route state budget exceeded")
    if terminal is None:
        raise MultipathError("no route satisfies the collectible and exit constraints")
    actions: list[str] = []
    state = terminal
    while parents[state] is not None:
        state, action = parents[state]
        actions.append(action)
        if len(actions) > _MAX_PATH_STEPS:
            raise MultipathError("route reconstruction exceeds action budget")
    actions.reverse()
    result = evaluate_route(
        problem, actions, allow_hazards=allow_hazards,
        hazard_cost=hazard_cost, edge_penalties=penalties,
        solver=algorithm, expanded_states=expanded,
    )
    if result.cost != best[terminal]:
        raise MultipathError("solver and replay cost disagree")
    return result


__all__ = ["MultipathError", "RouteProblem", "RouteProof", "solve_route", "evaluate_route"]
