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


def route_edges(proof: RouteProof) -> tuple[Edge, ...]:
    """Expose each actual move, preserving chronology and directed geometry."""
    if not isinstance(proof, RouteProof) or len(proof.positions) != len(proof.actions) + 1:
        raise MultipathError("invalid route proof structure")
    return tuple(zip(proof.positions, proof.positions[1:]))



def route_revisits(proof: RouteProof) -> int:
    """Count revisited tiles, including deliberate collectible backtracks."""
    if not isinstance(proof, RouteProof):
        raise MultipathError("typed RouteProof required")
    seen: set[Position] = set()
    repeated = 0
    for position in proof.positions:
        if position in seen:
            repeated += 1
        seen.add(position)
    return repeated



def route_turns(proof: RouteProof) -> int:
    """Count directional changes, a device-independent navigation signal."""
    if not isinstance(proof, RouteProof):
        raise MultipathError("typed RouteProof required")
    if not proof.actions:
        return 0
    return sum(a != b for a, b in zip(proof.actions, proof.actions[1:]))



def route_overlap_ppm(left: RouteProof, right: RouteProof) -> int:
    """Integer Jaccard intersection of traversed undirected corridors."""
    if (not isinstance(left, RouteProof) or not isinstance(right, RouteProof)
            or left.problem_digest != right.problem_digest):
        raise MultipathError("route overlap requires the same verified world")
    def edges(route: RouteProof) -> set[tuple[Position, Position]]:
        return {tuple(sorted((a, b))) for a, b in route_edges(route)}
    a = edges(left)
    b = edges(right)
    union = len(a | b)
    return 1_000_000 if union == 0 else len(a & b) * 1_000_000 // union



def route_diversity_ppm(left: RouteProof, right: RouteProof) -> int:
    """Cross-route novelty; 0 means the same corridors were traversed."""
    return 1_000_000 - route_overlap_ppm(left, right)



def route_portfolio(
    problem: RouteProblem, *, max_routes: int = 5,
    penalty_per_use: int = 10, max_expansions: int = _MAX_STATES,
) -> tuple[RouteProof, ...]:
    """Search for distinct playable routes rather than fabricate path variety.

    Each later route pays progressively larger penalties for previously used
    directed transitions. A single-path map returns only proven actual routes.
    """
    if (type(max_routes) is not int or not 1 <= max_routes <= 8
            or type(penalty_per_use) is not int
            or not 1 <= penalty_per_use <= 100_000):
        raise MultipathError("invalid alternative solver portfolio limits")
    found: list[RouteProof] = []
    seen: set[tuple[str, ...]] = set()
    penalties: dict[Edge, int] = {}
    for _ in range(max_routes * 3):
        candidate = solve_route(problem, algorithm="dijkstra",
                                edge_penalties=penalties,
                                max_expansions=max_expansions)
        # Search penalties encourage diversity; they are NOT charges or
        # gameplay costs incurred by the player. Re-admit exact actions
        # with physical unit-cost replay before storing the receipt.
        proof = evaluate_route(
            problem, candidate.actions, solver="diversity_dijkstra",
            expanded_states=candidate.expanded_states,
        )
        if proof.actions not in seen:
            seen.add(proof.actions)
            found.append(proof)
            if len(found) >= max_routes:
                break
        for edge in route_edges(proof):
            penalties[edge] = min(1_000_000, penalties.get(edge, 0) + penalty_per_use)
    return tuple(found)



def walkable_cells(problem: RouteProblem, *, include_hazards: bool = False) -> tuple[Position, ...]:
    """Return all actual traversable coordinates in stable reading order."""
    if not isinstance(problem, RouteProblem) or type(include_hazards) is not bool:
        raise MultipathError("invalid walkable-cell query")
    return tuple((x, y) for y, row in enumerate(problem.rows)
                 for x, tile in enumerate(row)
                 if tile != "#" and (include_hazards or tile != "H"))



def flood_fill(
    problem: RouteProblem, start: Position, *,
    allow_hazards: bool = False,
) -> frozenset[Position]:
    """Enumerate a physically reachable region with a deterministic BFS."""
    if (not isinstance(problem, RouteProblem) or not isinstance(start, tuple)
            or len(start) != 2 or any(type(v) is not int for v in start)
            or type(allow_hazards) is not bool):
        raise MultipathError("invalid flood-fill parameters")
    if problem.tile(start) == "#" or (start in problem.hazards and not allow_hazards):
        raise MultipathError("flood-fill origin is not traversable")
    seen = {start}
    pending = deque([start])
    while pending:
        point = pending.popleft()
        for _, nxt in problem.neighbors(point, allow_hazards=allow_hazards):
            if nxt not in seen:
                seen.add(nxt)
                pending.append(nxt)
        if len(seen) > MAX_DIMENSION * MAX_DIMENSION:
            raise MultipathError("flood-fill state budget exceeded")
    return frozenset(seen)



def connected_regions(
    problem: RouteProblem, *, allow_hazards: bool = False,
) -> tuple[frozenset[Position], ...]:
    """Partition all open cells, keeping even unreachable design pockets."""
    remaining = set(walkable_cells(problem, include_hazards=allow_hazards))
    regions: list[frozenset[Position]] = []
    while remaining:
        origin = min(remaining, key=lambda p: (p[1], p[0]))
        region = flood_fill(problem, origin, allow_hazards=allow_hazards)
        regions.append(region)
        remaining.difference_update(region)
    return tuple(regions)



def objective_reachability(problem: RouteProblem) -> dict[str, object]:
    """Explain why collectible-exit search is impossible before state BFS."""
    if not isinstance(problem, RouteProblem):
        raise MultipathError("typed problem required for reachability")
    reachable = flood_fill(problem, problem.start)
    missing = tuple(p for p in problem.collectibles if p not in reachable)
    return {
        "problem_digest": problem.digest,
        "all_collectibles_reachable": not missing,
        "exit_reachable": problem.goal in reachable,
        "missing_collectibles": missing,
        "reachable_tiles": len(reachable),
    }



def degree_histogram(problem: RouteProblem) -> dict[int, int]:
    """Count safe physical cells by number of meaningful cardinal exits."""
    if not isinstance(problem, RouteProblem):
        raise MultipathError("typed problem required for branching report")
    counts = {i: 0 for i in range(5)}
    for cell in walkable_cells(problem):
        degree = len(problem.neighbors(cell, allow_hazards=False))
        counts[degree] += 1
    return counts



def dead_end_cells(
    problem: RouteProblem, *, include_objectives: bool = False,
) -> tuple[Position, ...]:
    """Detect structural cul-de-sacs, with opt-in endpoints for diagnostics."""
    if type(include_objectives) is not bool:
        raise MultipathError("invalid dead-end reporting policy")
    objectives = {problem.start, problem.goal, *problem.collectibles}
    return tuple(
        cell for cell in walkable_cells(problem)
        if len(problem.neighbors(cell, allow_hazards=False)) <= 1
        and (include_objectives or cell not in objectives)
    )



def _lowlink_report(problem: RouteProblem) -> tuple[tuple[Position, ...], tuple[Edge, ...]]:
    """Find articulation vertices and bridges without recursion-depth risk."""
    if not isinstance(problem, RouteProblem):
        raise MultipathError("typed RouteProblem required")
    discovery: dict[Position, int] = {}
    low: dict[Position, int] = {}
    parent: dict[Position, Position | None] = {}
    child_counts: dict[Position, int] = {}
    cuts: set[Position] = set()
    bridges: set[Edge] = set()
    tick = 0
    for root in walkable_cells(problem):
        if root in discovery:
            continue
        parent[root] = None
        discovery[root] = low[root] = tick
        tick += 1
        child_counts[root] = 0
        stack: list[tuple[Position, object]] = [
            (root, iter(n for _, n in problem.neighbors(root, allow_hazards=False)))
        ]
        while stack:
            here, iterator = stack[-1]
            next_cell = next(iterator, None)
            if next_cell is not None:
                if next_cell not in discovery:
                    parent[next_cell] = here
                    child_counts[here] = child_counts.get(here, 0) + 1
                    child_counts[next_cell] = 0
                    discovery[next_cell] = low[next_cell] = tick
                    tick += 1
                    stack.append((
                        next_cell, iter(n for _, n in problem.neighbors(next_cell, allow_hazards=False))
                    ))
                elif next_cell != parent[here]:
                    low[here] = min(low[here], discovery[next_cell])
                continue
            stack.pop()
            ancestor = parent[here]
            if ancestor is None:
                if child_counts[here] >= 2:
                    cuts.add(here)
            else:
                low[ancestor] = min(low[ancestor], low[here])
                if parent[ancestor] is not None and low[here] >= discovery[ancestor]:
                    cuts.add(ancestor)
                if low[here] > discovery[ancestor]:
                    bridges.add(tuple(sorted((ancestor, here))))
    return (
        tuple(sorted(cuts, key=lambda p: (p[1], p[0]))),
        tuple(sorted(bridges, key=lambda e: (e[0][1], e[0][0], e[1][1], e[1][0]))),
    )


def articulation_cells(problem: RouteProblem) -> tuple[Position, ...]:
    """Identify tiles whose removal splits a safe connected region."""
    return _lowlink_report(problem)[0]



def bridge_corridors(problem: RouteProblem) -> tuple[Edge, ...]:
    """Identify physical edges whose closure disconnects a safe region."""
    return _lowlink_report(problem)[1]



def cycle_rank(problem: RouteProblem) -> int:
    """Compute E - V + C, the topological number of independent loops."""
    cells = walkable_cells(problem)
    edges = sum(len(problem.neighbors(p, allow_hazards=False)) for p in cells) // 2
    return edges - len(cells) + len(connected_regions(problem))



def tile_distances(
    problem: RouteProblem, origin: Position, *, allow_hazards: bool = False,
) -> dict[Position, int]:
    """Shortest cardinal distances for game pacing and objective placement."""
    if not isinstance(problem, RouteProblem):
        raise MultipathError("typed RouteProblem required")
    if (not isinstance(origin, tuple) or len(origin) != 2
            or any(type(k) is not int for k in origin)
            or problem.tile(origin) == "#"
            or (origin in problem.hazards and not allow_hazards)):
        raise MultipathError("invalid distance origin")
    out = {origin: 0}
    pending = deque([origin])
    while pending:
        at = pending.popleft()
        for _, nxt in problem.neighbors(at, allow_hazards=allow_hazards):
            if nxt in out:
                continue
            out[nxt] = out[at] + 1
            pending.append(nxt)
    return out



def route_branch_choices(problem: RouteProblem, proof: RouteProof) -> tuple[int, ...]:
    """Return action choices at each visited route cell, excluding terminal."""
    if not isinstance(proof, RouteProof) or proof.problem_digest != problem.digest:
        raise MultipathError("route choice analysis needs current world proof")
    evaluate_route(problem, proof.actions, allow_hazards=proof.hazard_visits > 0)
    return tuple(len(problem.neighbors(pos, allow_hazards=False))
                 for pos in proof.positions[:-1])



def hazard_proximity(
    problem: RouteProblem, *, radius: int = 2,
) -> dict[Position, int]:
    """For each safe tile count hazards within Manhattan awareness radius."""
    if not isinstance(problem, RouteProblem) or type(radius) is not int or not 1 <= radius <= 6:
        raise MultipathError("invalid hazard awareness radius")
    return {
        p: sum(abs(p[0] - h[0]) + abs(p[1] - h[1]) <= radius
               for h in problem.hazards)
        for p in walkable_cells(problem)
    }



def route_exposure_score(
    problem: RouteProblem, proof: RouteProof, *, radius: int = 2,
) -> int:
    """Count risk-adjacent frames without treating proximity as direct damage."""
    if not isinstance(proof, RouteProof) or proof.problem_digest != problem.digest:
        raise MultipathError("hazard exposure must bind the source world")
    replayed = evaluate_route(problem, proof.actions, allow_hazards=proof.hazard_visits > 0)
    if replayed.positions != proof.positions:
        raise MultipathError("route geometry does not replay")
    exposures = hazard_proximity(problem, radius=radius)
    return sum(exposures.get(p, len(problem.hazards)) for p in proof.positions)



def route_friction_ppm(
    problem: RouteProblem, proof: RouteProof,
    *, turn_weight: int = 100_000,
    revisit_weight: int = 200_000,
) -> int:
    """Bounded navigation friction; not an unvalidated human fun predictor."""
    if (type(turn_weight) is not int or type(revisit_weight) is not int
            or not 0 <= turn_weight <= 1_000_000
            or not 0 <= revisit_weight <= 1_000_000):
        raise MultipathError("invalid friction weights")
    if proof.problem_digest != problem.digest:
        raise MultipathError("friction report needs current source world")
    evaluate_route(problem, proof.actions, allow_hazards=proof.hazard_visits > 0)
    denominator = max(1, proof.steps)
    numerator = route_turns(proof) * turn_weight + route_revisits(proof) * revisit_weight
    return min(1_000_000, numerator // denominator)



def route_coverage_ppm(problem: RouteProblem, proof: RouteProof) -> int:
    """Fraction of safe traversable cells the actual route discovers."""
    if proof.problem_digest != problem.digest:
        raise MultipathError("coverage report must bind current world")
    replay = evaluate_route(problem, proof.actions, allow_hazards=proof.hazard_visits > 0)
    if replay.positions != proof.positions:
        raise MultipathError("route positions disagree with replay")
    allowed = set(walkable_cells(problem))
    visited = set(proof.positions) & allowed
    return len(visited) * 1_000_000 // max(1, len(allowed))



def objective_dispersion(problem: RouteProblem) -> dict[str, int]:
    """Exact shortest-path distribution between collectibles and endpoints."""
    if not isinstance(problem, RouteProblem):
        raise MultipathError("typed problem required for collectible dispersion")
    points = (problem.start, *problem.collectibles, problem.goal)
    pair_distances: list[int] = []
    for i, start in enumerate(points):
        distances = tile_distances(problem, start)
        for goal in points[i+1:]:
            if goal not in distances:
                raise MultipathError("objective components are disconnected")
            pair_distances.append(distances[goal])
    return {
        "minimum_steps": min(pair_distances),
        "maximum_steps": max(pair_distances),
        "mean_steps_ppm": sum(pair_distances) * 1_000_000 // len(pair_distances),
        "pairs": len(pair_distances),
    }



def route_chokepoint_ppm(problem: RouteProblem, proof: RouteProof) -> int:
    """Share of unique route positions that are articulation vertices."""
    if proof.problem_digest != problem.digest:
        raise MultipathError("chokepoint analysis needs matching world")
    replay = evaluate_route(problem, proof.actions, allow_hazards=proof.hazard_visits > 0)
    if replay.positions != proof.positions:
        raise MultipathError("route positions cannot be verified")
    visited = set(proof.positions)
    return len(visited & set(articulation_cells(problem))) * 1_000_000 // max(1, len(visited))



def route_overrun_ppm(problem: RouteProblem, proof: RouteProof) -> int:
    """Relative extra traversal against the same hazard accessibility policy."""
    if proof.problem_digest != problem.digest:
        raise MultipathError("route optimization needs same source world")
    verified = evaluate_route(
        problem, proof.actions, allow_hazards=proof.hazard_visits > 0,
    )
    if verified.positions != proof.positions:
        raise MultipathError("route replay geometry differs")
    if proof.hazard_visits:
        minimum = solve_route(problem, algorithm="dijkstra",
                              allow_hazards=True, hazard_cost=0).steps
    else:
        minimum = solve_route(problem).steps
    if proof.steps < minimum:
        raise MultipathError("route shorter than claimed optimal safe baseline")
    return (proof.steps - minimum) * 1_000_000 // max(1, minimum)



def verify_route_proof(
    problem: RouteProblem, proof: RouteProof, *, hazard_cost: int = 8,
    edge_penalties: Mapping[Edge, int] | None = None,
) -> bool:
    """Recompute every material field, including cost and ordered objectives."""
    if not isinstance(proof, RouteProof) or proof.problem_digest != problem.digest:
        raise MultipathError("route proof refers to another level")
    replay = evaluate_route(
        problem, proof.actions, allow_hazards=proof.hazard_visits > 0,
        hazard_cost=hazard_cost, edge_penalties=edge_penalties,
        solver=proof.solver, expanded_states=proof.expanded_states,
    )
    if replay != proof:
        raise MultipathError("route proof does not match deterministic replay")
    return True



def portfolio_diversity_ppm(portfolio: Sequence[RouteProof]) -> int:
    """Mean pairwise corridor novelty; a single route yields zero diversity."""
    if (not isinstance(portfolio, (list, tuple)) or not portfolio
            or len(portfolio) > 16
            or any(not isinstance(p, RouteProof) for p in portfolio)
            or len({p.problem_digest for p in portfolio}) != 1):
        raise MultipathError("portfolio needs 1–16 proofs for the same level")
    if len(portfolio) == 1:
        return 0
    values = [route_diversity_ppm(a, b)
              for index, a in enumerate(portfolio) for b in portfolio[index+1:]]
    return sum(values) // len(values)



def route_exclusive_edges(
    route: RouteProof, others: Sequence[RouteProof],
) -> tuple[Edge, ...]:
    """Identify steps that are absent from all other portfolio members."""
    if not isinstance(route, RouteProof) or not isinstance(others, (tuple, list)) or len(others) > 16:
        raise MultipathError("invalid route comparison portfolio")
    if any(not isinstance(other, RouteProof) or other.problem_digest != route.problem_digest
           for other in others):
        raise MultipathError("exclusive route edges require same level")
    occupied = {tuple(sorted(edge)) for other in others for edge in route_edges(other)}
    return tuple(edge for edge in route_edges(route)
                 if tuple(sorted(edge)) not in occupied)



def portfolio_profile(problem: RouteProblem, routes: Sequence[RouteProof]) -> dict[str, object]:
    """Stable game-design indicators, never a fabricated player satisfaction score."""
    if not isinstance(routes, (list, tuple)) or not routes or len(routes) > 8:
        raise MultipathError("bounded non-empty portfolio required")
    for proof in routes:
        if not verify_route_proof(problem, proof):
            raise MultipathError("unverified route in portfolio")
    return {
        "schema": "skeleton.game_builder.route_portfolio_profile.v1",
        "world_digest": problem.digest,
        "route_count": len(routes),
        "distinct_action_sequences": len({p.actions for p in routes}),
        "min_steps": min(p.steps for p in routes),
        "max_steps": max(p.steps for p in routes),
        "objective_orders": len({p.collectible_order for p in routes}),
        "corridor_diversity_ppm": portfolio_diversity_ppm(routes),
        "has_structural_loops": cycle_rank(problem) > 0,
        "route_digests": [p.digest for p in routes],
        "human_playtest_verified": False,
    }



def rank_routes(
    problem: RouteProblem, routes: Sequence[RouteProof],
    *, preference: str = "shortest",
) -> tuple[RouteProof, ...]:
    """Choose understandable route rankings without equating length with fun."""
    if preference not in {"shortest", "exploration", "low_friction", "low_exposure"}:
        raise MultipathError("unknown route ranking preference")
    if not isinstance(routes, (list, tuple)) or len(routes) > 16:
        raise MultipathError("invalid route ranking portfolio")
    for p in routes:
        verify_route_proof(problem, p)
    if preference == "shortest":
        key = lambda p: (p.steps, p.hazard_visits, p.digest)
    elif preference == "exploration":
        key = lambda p: (-route_coverage_ppm(problem, p), p.steps, p.digest)
    elif preference == "low_friction":
        key = lambda p: (route_friction_ppm(problem, p), p.steps, p.digest)
    else:
        key = lambda p: (route_exposure_score(problem, p), p.steps, p.digest)
    return tuple(sorted(routes, key=key))



def challenge_route_selection(
    problem: RouteProblem, routes: Sequence[RouteProof],
) -> dict[str, object]:
    """Return fast, exploratory and friction-rich routes with honest qualifiers."""
    if not isinstance(routes, (list, tuple)) or not routes or len(routes) > 8:
        raise MultipathError("bounded route choices required")
    for proof in routes:
        verify_route_proof(problem, proof)
    shortest = rank_routes(problem, routes, preference="shortest")[0]
    explore = rank_routes(problem, routes, preference="exploration")[0]
    highest_friction = max(routes, key=lambda proof: (
        route_friction_ppm(problem, proof), proof.steps, proof.digest))
    return {
        "schema": "skeleton.game_builder.route_challenge_selection.v1",
        "world_digest": problem.digest,
        "fastest_digest": shortest.digest,
        "explorer_digest": explore.digest,
        "high_friction_digest": highest_friction.digest,
        "route_options_verified": len({p.actions for p in routes}),
        "player_enjoyment_proven": False,
        "requires_playtesting": True,
    }



def solve_route_astar(
    problem: RouteProblem, *, heuristic_weight_ppm: int = 1_000_000,
    max_expansions: int = _MAX_STATES,
) -> RouteProof:
    """A* on (position, objectives), with optimal mode at weight 1.0.

    Weighted mode is useful to study throughput but DOES NOT promise an optimal
    path. Manhattan-to-next-objective never overstates unavoidable safe steps.
    """
    if (not isinstance(problem, RouteProblem) or type(heuristic_weight_ppm) is not int
            or not 1_000_000 <= heuristic_weight_ppm <= 2_000_000
            or type(max_expansions) is not int or not 1 <= max_expansions <= _MAX_STATES):
        raise MultipathError("invalid bounded A* configuration")
    bits = {p: 1 << index for index, p in enumerate(problem.collectibles)}
    full = (1 << len(bits)) - 1

    def heuristic(state: State) -> int:
        x, y, mask = state
        remaining = [pos for pos, bit in bits.items() if not (mask & bit)]
        goals = remaining if remaining else [problem.goal]
        return min(abs(x - p[0]) + abs(y - p[1]) for p in goals)

    initial: State = (*problem.start, 0)
    costs = {initial: 0}
    parents: dict[State, tuple[State, str] | None] = {initial: None}
    priority: list[tuple[int, int, int, State]] = [
        (heuristic(initial) * heuristic_weight_ppm, 0, 0, initial),
    ]
    serial = 0
    expanded = 0
    endpoint = None
    while priority:
        _, current, _, state = heappop(priority)
        if current != costs.get(state):
            continue
        expanded += 1
        if expanded > max_expansions:
            raise MultipathError("A* expansion budget exceeded")
        if state[:2] == problem.goal and state[2] == full:
            endpoint = state
            break
        for action, next_pos in problem.neighbors(state[:2], allow_hazards=False):
            nxt: State = (*next_pos, state[2] | bits.get(next_pos, 0))
            proposed = current + 1
            if proposed >= costs.get(nxt, 2**63):
                continue
            costs[nxt] = proposed
            parents[nxt] = (state, action)
            serial += 1
            priority_score = (
                proposed * 1_000_000 + heuristic(nxt) * heuristic_weight_ppm
            )
            heappush(priority, (priority_score, proposed, serial, nxt))
        if len(costs) > _MAX_STATES:
            raise MultipathError("A* state limit exceeded")
    if endpoint is None:
        raise MultipathError("no safe A* route meets all objectives")
    actions: list[str] = []
    state = endpoint
    while parents[state] is not None:
        state, action = parents[state]
        actions.append(action)
        if len(actions) > _MAX_PATH_STEPS:
            raise MultipathError("A* path length budget exceeded")
    actions.reverse()
    return evaluate_route(
        problem, actions, solver=("astar" if heuristic_weight_ppm == 1_000_000
                                  else "weighted_astar"), expanded_states=expanded,
    )



def solve_avoid_cells(
    problem: RouteProblem, forbidden: Sequence[Position],
    *, max_expansions: int = _MAX_STATES,
) -> RouteProof:
    """Re-solve after excluding designer-controlled tiles; preserve source grid."""
    if (not isinstance(problem, RouteProblem) or not isinstance(forbidden, (tuple, list))
            or len(forbidden) > 128 or type(max_expansions) is not int
            or not 1 <= max_expansions <= _MAX_STATES):
        raise MultipathError("invalid bounded forbidden-tile constraints")
    blocked = set()
    objectives = {problem.start, problem.goal, *problem.collectibles}
    for cell in forbidden:
        if (not isinstance(cell, tuple) or len(cell) != 2
                or any(type(c) is not int for c in cell)
                or cell in objectives or problem.tile(cell) == "#"):
            raise MultipathError("cannot forbid an objective or invalid tile")
        blocked.add(cell)
    bits = {p: 1 << i for i, p in enumerate(problem.collectibles)}
    end_mask = (1 << len(bits)) - 1
    initial: State = (*problem.start, 0)
    queue = deque([initial])
    parents: dict[State, tuple[State, str] | None] = {initial: None}
    expanded = 0
    terminal = None
    while queue:
        state = queue.popleft()
        expanded += 1
        if expanded > max_expansions:
            raise MultipathError("restricted search expansion budget exceeded")
        if state[:2] == problem.goal and state[2] == end_mask:
            terminal = state
            break
        for action, pos in problem.neighbors(state[:2], allow_hazards=False):
            if pos in blocked:
                continue
            nxt: State = (*pos, state[2] | bits.get(pos, 0))
            if nxt not in parents:
                parents[nxt] = (state, action)
                queue.append(nxt)
    if terminal is None:
        raise MultipathError("blocked corridor makes objective route impossible")
    actions: list[str] = []
    while parents[terminal] is not None:
        terminal, action = parents[terminal]
        actions.append(action)
    return evaluate_route(problem, tuple(reversed(actions)),
                          solver="forbidden_cells", expanded_states=expanded)



def solve_hazard_budget(
    problem: RouteProblem, *, max_hazard_visits: int = 0,
    max_expansions: int = 250_000,
) -> RouteProof:
    """Find fewest steps subject to a strict count of entered hazard tiles."""
    if (not isinstance(problem, RouteProblem)
            or type(max_hazard_visits) is not int
            or not 0 <= max_hazard_visits <= 12
            or type(max_expansions) is not int or not 1 <= max_expansions <= 250_000):
        raise MultipathError("invalid bounded hazard-exposure budget")
    bits = {p: 1 << i for i, p in enumerate(problem.collectibles)}
    target = (1 << len(bits)) - 1
    initial = (*problem.start, 0, 0)
    queue = deque([initial])
    parents: dict[tuple[int, int, int, int],
                  tuple[tuple[int, int, int, int], str] | None] = {initial: None}
    expanded = 0
    terminal = None
    while queue:
        state = queue.popleft()
        expanded += 1
        if expanded > max_expansions:
            raise MultipathError("hazard-budget search expansion limit exceeded")
        x, y, mask, exposure = state
        if (x, y) == problem.goal and mask == target:
            terminal = state
            break
        for action, pos in problem.neighbors((x, y), allow_hazards=True):
            used = exposure + int(pos in problem.hazards)
            if used > max_hazard_visits:
                continue
            nxt = (*pos, mask | bits.get(pos, 0), used)
            if nxt not in parents:
                parents[nxt] = (state, action)
                queue.append(nxt)
    if terminal is None:
        raise MultipathError("no route satisfies the strict hazard exposure budget")
    steps = []
    while parents[terminal] is not None:
        terminal, action = parents[terminal]
        steps.append(action)
    return evaluate_route(problem, tuple(reversed(steps)),
                          allow_hazards=max_hazard_visits > 0,
                          solver="hazard_budget", expanded_states=expanded)



def pareto_hazard_routes(problem: RouteProblem) -> tuple[RouteProof, ...]:
    """Return actual nondominated (steps, hazard visits) replay paths."""
    if not isinstance(problem, RouteProblem):
        raise MultipathError("typed RouteProblem required")
    candidates = []
    for budget in range(min(12, len(problem.hazards)) + 1):
        try:
            candidate = solve_hazard_budget(problem, max_hazard_visits=budget)
        except MultipathError as exc:
            if "no route satisfies" in str(exc):
                continue
            raise
        if (candidate.steps, candidate.hazard_visits) not in {
            (r.steps, r.hazard_visits) for r in candidates
        }:
            candidates.append(candidate)
    frontier = [
        p for p in candidates
        if not any(q is not p
                   and q.steps <= p.steps and q.hazard_visits <= p.hazard_visits
                   and (q.steps < p.steps or q.hazard_visits < p.hazard_visits)
                   for q in candidates)
    ]
    return tuple(sorted(frontier, key=lambda p: (p.hazard_visits, p.steps, p.digest)))



def enumerate_shortest_routes(
    problem: RouteProblem, *, limit: int = 8,
    max_expansions: int = _MAX_STATES,
) -> tuple[RouteProof, ...]:
    """Walk the shortest-path DAG; do not substitute longer diversity detours."""
    if (not isinstance(problem, RouteProblem) or type(limit) is not int
            or not 1 <= limit <= 32 or type(max_expansions) is not int
            or not 1 <= max_expansions <= _MAX_STATES):
        raise MultipathError("invalid shortest-path enumeration bounds")
    bits = {p: 1 << i for i, p in enumerate(problem.collectibles)}
    full = (1 << len(bits)) - 1
    origin: State = (*problem.start, 0)
    queue = deque([origin])
    distance = {origin: 0}
    parents: dict[State, list[tuple[State, str]]] = {origin: []}
    endpoint = None
    expanded = 0
    while queue:
        state = queue.popleft()
        expanded += 1
        if expanded > max_expansions:
            raise MultipathError("shortest-path enumeration expansion budget exceeded")
        if endpoint is not None and distance[state] > distance[endpoint]:
            break
        if state[:2] == problem.goal and state[2] == full:
            endpoint = state
            continue
        for action, p in problem.neighbors(state[:2], allow_hazards=False):
            nxt: State = (*p, state[2] | bits.get(p, 0))
            proposed = distance[state] + 1
            if nxt not in distance:
                distance[nxt] = proposed
                parents[nxt] = [(state, action)]
                queue.append(nxt)
            elif distance[nxt] == proposed:
                parents[nxt].append((state, action))
    if endpoint is None:
        raise MultipathError("no shortest collectible-complete route")
    results: list[RouteProof] = []
    stack: list[tuple[State, tuple[str, ...]]] = [(endpoint, ())]
    while stack and len(results) < limit:
        state, suffix = stack.pop()
        if state == origin:
            results.append(evaluate_route(problem, suffix, solver="shortest_dag",
                                          expanded_states=expanded))
            continue
        for previous, action in reversed(parents[state]):
            stack.append((previous, (action,) + suffix))
    return tuple(results)



def route_progress_trace(
    problem: RouteProblem, proof: RouteProof,
) -> tuple[tuple[int, Position, int], ...]:
    """Replay step-wise objective counts for tutorial pacing and quest cues."""
    if proof.problem_digest != problem.digest:
        raise MultipathError("progress trace requires current game world")
    result = evaluate_route(problem, proof.actions,
                            allow_hazards=proof.hazard_visits > 0)
    if result.positions != proof.positions:
        raise MultipathError("route progress does not replay")
    seen: set[Position] = set()
    out = []
    for step, p in enumerate(proof.positions):
        if p in problem.collectibles:
            seen.add(p)
        out.append((step, p, len(seen)))
    return tuple(out)



@dataclass(frozen=True, slots=True)
class MapEditReceipt:
    operation: str
    before_digest: str
    after: RouteProblem
    changes: tuple[tuple[Position, str, str], ...]
    safe_proof: RouteProof

    @property
    def digest(self) -> str:
        return canonical_digest({
            "schema": "skeleton.game_builder.map_edit.v1",
            "operation": self.operation, "before": self.before_digest,
            "after": self.after.digest,
            "changes": [[list(p), old, new] for p, old, new in self.changes],
            "proof": self.safe_proof.digest,
        })


def make_level_edit(
    problem: RouteProblem, changes: Mapping[Position, str], *,
    operation: str, authorized: bool,
) -> MapEditReceipt:
    """Apply bounded tile mutations atomically, proving all objectives survive."""
    if authorized is not True:
        raise PermissionError("game map mutation requires designer authorization")
    if (not isinstance(problem, RouteProblem)
            or not isinstance(changes, Mapping) or not 1 <= len(changes) <= 12
            or not isinstance(operation, str)
            or not 1 <= len(operation) <= 64
            or not all(c.islower() or c == "_" for c in operation)):
        raise MultipathError("invalid bounded map edit request")
    rows = [list(row) for row in problem.rows]
    recorded: list[tuple[Position, str, str]] = []
    for p, new in sorted(changes.items(), key=lambda item: (item[0][1], item[0][0])):
        if (not isinstance(p, tuple) or len(p) != 2
                or any(type(v) is not int for v in p)
                or not 0 < p[0] < problem.width-1
                or not 0 < p[1] < problem.height-1
                or type(new) is not str or len(new) != 1 or new not in "#.SGCH"):
            raise MultipathError("invalid in-bounds tile mutation")
        old = problem.tile(p)
        if old == new:
            raise MultipathError("no-op map mutations are not admissible")
        rows[p[1]][p[0]] = new
        recorded.append((p, old, new))
    revised = RouteProblem.from_rows(tuple("".join(row) for row in rows))
    if len(revised.collectibles) != len(problem.collectibles):
        raise MultipathError("map edit cannot silently change objective count")
    proof = solve_route(revised)
    return MapEditReceipt(operation, problem.digest, revised, tuple(recorded), proof)



__all__ = ["MultipathError", "RouteProblem", "RouteProof", "solve_route", "evaluate_route", "route_edges", "route_revisits", "route_turns", "route_overlap_ppm", "route_diversity_ppm", "route_portfolio", "walkable_cells", "flood_fill", "connected_regions", "objective_reachability", "degree_histogram", "dead_end_cells", "articulation_cells", "bridge_corridors", "cycle_rank", "tile_distances", "route_branch_choices", "hazard_proximity", "route_exposure_score", "route_friction_ppm", "route_coverage_ppm", "objective_dispersion", "route_chokepoint_ppm", "route_overrun_ppm", "verify_route_proof", "portfolio_diversity_ppm", "route_exclusive_edges", "portfolio_profile", "rank_routes", "challenge_route_selection", "solve_route_astar", "solve_avoid_cells", "solve_hazard_budget", "pareto_hazard_routes", "enumerate_shortest_routes", "route_progress_trace", "make_level_edit"]
