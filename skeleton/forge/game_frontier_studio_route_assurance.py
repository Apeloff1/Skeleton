"""Source-bound walkable navigation witnesses for canonical Forge Studio.

This is a deterministic reference playthrough audit, not a native Godot
playthrough or release certification. It evaluates real authored tile sources
using the same material policy as the canonical tile navigation bridge. No
external model, filesystem writer, provider, or new state owner is introduced.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
import re
from typing import Any

from .game_frontier_studio import StudioError, StudioProject
from .game_frontier_studio_authoring import project_digest
from .game_frontier_studio_tile_navigation import _traversable

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_MAX_SCENARIOS = 100
_MAX_CELLS = 256 * 256
_WITNESS_LIMIT = 256
_NEIGHBORS = ((0, -1), (-1, 0), (1, 0), (0, 1))


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _coordinate(value: object, name: str, width: int, height: int) -> tuple[int, int]:
    if (type(value) not in (list, tuple) or len(value) != 2
        or any(type(x) is not int for x in value)):
        raise StudioError(name + " needs two integer tile coordinates")
    x, y = value
    if not 0 <= x < width or not 0 <= y < height:
        raise StudioError(name + " lies outside authored tile bounds")
    return x, y


def _scenarios(project: StudioProject, scenarios: object) -> tuple[dict[str, Any], ...]:
    if (not isinstance(project, StudioProject)
        or type(scenarios) not in (list, tuple)
        or not 1 <= len(scenarios) <= _MAX_SCENARIOS):
        raise StudioError("route replay requires 1..100 typed scenarios")
    layers = {layer.layer_id: layer for layer in project.layers}
    seen: set[str] = set()
    accepted = []
    for raw in scenarios:
        if (type(raw) is not dict or set(raw) !=
            {"scenario_id", "layer", "start", "goal", "require_alternate"}):
            raise StudioError("route scenario accepts exact source-bound fields only")
        ident, layer_id = raw["scenario_id"], raw["layer"]
        if (type(ident) is not str or not _ID.fullmatch(ident)
            or ident in seen or type(layer_id) is not str
            or layer_id not in layers or
            type(raw["require_alternate"]) is not bool):
            raise StudioError("duplicate, unowned, or malformed route scenario")
        seen.add(ident)
        layer = layers[layer_id]
        if layer.width * layer.height > _MAX_CELLS:
            raise StudioError("authored map exceeds route replay budget")
        start = _coordinate(raw["start"], "start", layer.width, layer.height)
        goal = _coordinate(raw["goal"], "goal", layer.width, layer.height)
        if start == goal:
            raise StudioError("a route must traverse between distinct source tiles")
        accepted.append({"scenario_id": ident, "layer": layer_id,
                         "start": list(start), "goal": list(goal),
                         "require_alternate": raw["require_alternate"]})
    return tuple(accepted)


def _find_path(layer: Any, start: tuple[int, int], goal: tuple[int, int],
               forbidden: frozenset[tuple[int, int]] = frozenset()
               ) -> tuple[tuple[int, int], ...]:
    if (start in forbidden or goal in forbidden
        or not _traversable(layer, *start)
        or not _traversable(layer, *goal)):
        return ()
    queue = deque([start])
    parents: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            chain: list[tuple[int, int]] = []
            at: tuple[int, int] | None = goal
            while at is not None:
                chain.append(at)
                at = parents[at]
            return tuple(reversed(chain))
        for dx, dy in _NEIGHBORS:
            nx, ny = x + dx, y + dy
            candidate = (nx, ny)
            if (0 <= nx < layer.width and 0 <= ny < layer.height
                and candidate not in forbidden and candidate not in parents
                and _traversable(layer, nx, ny)):
                parents[candidate] = (x, y)
                queue.append(candidate)
    return ()


def _witness(path: tuple[tuple[int, int], ...]) -> dict[str, Any]:
    if not path:
        return {"reachable": False, "steps": None,
                "path_sha256": None, "path_sample": [],
                "sample_truncated": False}
    coords = [list(node) for node in path]
    if len(coords) > _WITNESS_LIMIT:
        sample = coords[:_WITNESS_LIMIT // 2] + coords[-_WITNESS_LIMIT // 2:]
    else:
        sample = coords
    return {"reachable": True, "steps": len(path) - 1,
            "path_sha256": _digest(coords),
            "path_sample": sample,
            "sample_truncated": len(coords) > _WITNESS_LIMIT}


def audit_route_playthroughs(project: StudioProject,
                             scenarios: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Run 1..100 deterministic *reference* routes over live authored tile bytes.

    Required alternatives are internally vertex-disjoint from the primary
    path, except for shared endpoints. This conservative test is not a proof of
    maximum network flow or of native movement controller performance.
    """
    cases = _scenarios(project, scenarios)
    layers = {layer.layer_id: layer for layer in project.layers}
    results = []
    passed = 0
    for scenario in cases:
        layer = layers[scenario["layer"]]
        start, goal = tuple(scenario["start"]), tuple(scenario["goal"])
        route = _find_path(layer, start, goal)
        secondary = (_find_path(layer, start, goal, frozenset(route[1:-1]))
                     if route and scenario["require_alternate"] else ())
        good = bool(route) and (not scenario["require_alternate"] or bool(secondary))
        passed += int(good)
        result = {
            **scenario, "source_layer_sha256": _digest({
                "size": [layer.width, layer.height],
                "palette": layer.palette, "data": layer.data,
                "elevation_m": layer.elevation_m,
            }),
            "primary": _witness(route),
            "alternate": _witness(secondary) if scenario["require_alternate"] else None,
            "passed": good,
            "failure": None if good else (
                "unreachable_in_authored_tiles" if not route
                else "no_vertex_disjoint_alternative"),
        }
        results.append(result)
    report = {
        "schema": "skeleton.forge.route_playthrough_assurance.v1",
        "project_id": project.project_id,
        "project_sha256": project_digest(project),
        "scenario_count": len(cases), "passed_count": passed,
        "failed_count": len(cases) - passed,
        "scenarios": results,
        "reference_source_replay": True,
        "native_engine_executed": False,
        "release_certified": False,
    }
    return {**report, "receipt_sha256": _digest(report)}


def verify_route_playthroughs(project: StudioProject,
                              scenarios: Sequence[Mapping[str, Any]],
                              claimed: Mapping[str, Any]) -> bool:
    """Source-replay and canonical receipt comparison; reject forged summaries."""
    if type(claimed) is not dict:
        return False
    try:
        replayed = audit_route_playthroughs(project, scenarios)
    except (StudioError, TypeError, ValueError):
        return False
    return _digest(claimed) == _digest(replayed) and claimed == replayed


def compare_route_playthroughs(before: Mapping[str, Any],
                               after: Mapping[str, Any]) -> dict[str, Any]:
    """Source-aware objective regression comparison; not a release override."""
    if type(before) is not dict or type(after) is not dict:
        raise StudioError("route comparison needs two complete reports")
    for value in (before, after):
        payload = {k: v for k, v in value.items() if k != "receipt_sha256"}
        if (value.get("schema") != "skeleton.forge.route_playthrough_assurance.v1"
            or value.get("receipt_sha256") != _digest(payload)):
            raise StudioError("route comparison report checksum mismatch")
    old = before["scenarios"]
    new = after["scenarios"]
    if (before["project_id"] != after["project_id"] or
        [(r["scenario_id"], r["layer"], r["start"], r["goal"],
          r["require_alternate"]) for r in old] !=
        [(r["scenario_id"], r["layer"], r["start"], r["goal"],
          r["require_alternate"]) for r in new]):
        raise StudioError("only identical source scenarios may be compared")
    degraded = [n["scenario_id"] for o, n in zip(old, new)
                if o["passed"] and not n["passed"]]
    improved = [n["scenario_id"] for o, n in zip(old, new)
                if not o["passed"] and n["passed"]]
    return {
        "schema": "skeleton.forge.route_comparison.v1",
        "baseline_sha256": before["project_sha256"],
        "candidate_sha256": after["project_sha256"],
        "improved": improved, "regressed": degraded,
        "strict_improvement": bool(improved) and not degraded,
        "native_engine_executed": False,
        "release_certified": False,
    }
