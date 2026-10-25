"""Deterministic source-grounded Epic inter-layer navigation assurance.

The existing Forge project is authoritative. This read-only reference auditor
validates declared transfer proposals and derives real four-neighbour travel
paths from live authored map palettes. Connector *proposals* are not native
transport events or proof of real Godot traversal.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
import math
import re
from typing import Any

from .game_frontier_studio import StudioProject, StudioError
from .game_frontier_studio_authoring import project_digest
from .game_frontier_studio_tile_navigation import _traversable

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_MODES = frozenset({"walk", "stairs", "elevator", "bridge", "ferry",
                    "shuttle", "portal"})
_NEIGHBOURS = ((1, 0), (0, 1), (-1, 0), (0, -1))
_MAX_LAYERS = 8
_MAX_CONNECTORS = 64
_MAX_ITINERARIES = 32
_MAX_NODES = 8 * 256 * 256
_SAMPLE = 128
Node = tuple[str, int, int]


def _hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf8")).hexdigest()


def _valid_id(value: Any, context: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise StudioError("Epic " + context + " requires a bounded original ID")
    return value


def _node(value: object, layers: dict[str, Any]) -> Node:
    if type(value) is not dict or set(value) != {"layer", "x", "y"}:
        raise StudioError("Epic travel endpoints need exact layer/x/y fields")
    layer_id = value["layer"]
    if type(layer_id) is not str or layer_id not in layers:
        raise StudioError("Epic route references a source layer outside its scope")
    x, y = value["x"], value["y"]
    layer = layers[layer_id]
    if (type(x) is not int or type(y) is not int
            or not 0 <= x < layer.width or not 0 <= y < layer.height):
        raise StudioError("Epic route endpoint lies outside the original source map")
    if not _traversable(layer, x, y):
        raise StudioError("Epic route endpoint is blocked in authoritative tile material")
    return (layer_id, x, y)


def _input(project: StudioProject, request: object):
    if not isinstance(project, StudioProject) or type(request) is not dict or (
            set(request) != {"layer_ids", "connectors", "itineraries"}):
        raise StudioError("Epic interlayer audit expects exact source-bound fields")
    ids = request["layer_ids"]
    connectors = request["connectors"]
    itineraries = request["itineraries"]
    if (type(ids) is not list or not 1 <= len(ids) <= _MAX_LAYERS
            or any(type(item) is not str for item in ids)
            or len(set(ids)) != len(ids)):
        raise StudioError("Epic interlayer audits allow 1..8 existing unique layers")
    known = {layer.layer_id: layer for layer in project.layers}
    if any(name not in known for name in ids):
        raise StudioError("Epic itinerary references a layer not owned by source")
    layers = {name: known[name] for name in ids}
    if (sum(layer.width * layer.height for layer in layers.values()) > _MAX_NODES
            or type(connectors) is not list
            or not 0 <= len(connectors) <= _MAX_CONNECTORS
            or type(itineraries) is not list
            or not 1 <= len(itineraries) <= _MAX_ITINERARIES):
        raise StudioError("Epic navigation exceeds bounded source replay budget")
    edges: dict[Node, list[tuple[Node, str]]] = {}
    seen: set[str] = set()
    normalized_connectors = []
    for raw in connectors:
        if (type(raw) is not dict or set(raw) != {
                "connector_id", "from", "to", "mode", "bidirectional"}):
            raise StudioError("Epic connectors require exact typed transfer fields")
        ident = _valid_id(raw["connector_id"], "connector")
        mode = raw["mode"]
        if (ident in seen or type(mode) is not str or mode not in _MODES
                or type(raw["bidirectional"]) is not bool):
            raise StudioError("duplicate or unsupported Epic transport proposal")
        seen.add(ident)
        start, end = _node(raw["from"], layers), _node(raw["to"], layers)
        if start == end:
            raise StudioError("Epic transfers must join distinct actual tiles")
        source, destination = layers[start[0]], layers[end[0]]
        distance = math.dist(
            (start[1], start[2], float(source.elevation_m)),
            (end[1], end[2], float(destination.elevation_m)),
        )
        altitude = abs(source.elevation_m - destination.elevation_m)
        if (mode in {"walk", "bridge"} and (altitude > 6 or distance > 32)
                or mode == "stairs" and altitude > 120):
            raise StudioError("Epic physically linked path exceeds asserted traversal mode")
        if start[0] != end[0] or abs(start[1]-end[1]) + abs(start[2]-end[2]) != 1:
            if mode == "walk":
                raise StudioError("Epic walk connector must be one same-layer adjacent tile")
        normalized_connectors.append({
            "connector_id": ident, "from": list(start), "to": list(end),
            "mode": mode, "bidirectional": raw["bidirectional"],
            "distance_m": round(distance, 5),
            "reference_transfer_only": True,
        })
        edges.setdefault(start, []).append((end, ident))
        if raw["bidirectional"]:
            edges.setdefault(end, []).append((start, ident))
    cases = []
    seen.clear()
    for raw in itineraries:
        if type(raw) is not dict or set(raw) != {
                "journey_id", "start", "goal", "require_alternate"}:
            raise StudioError("Epic itineraries require exact bounded source fields")
        ident = _valid_id(raw["journey_id"], "journey")
        if ident in seen or type(raw["require_alternate"]) is not bool:
            raise StudioError("duplicate or malformed Epic journey")
        seen.add(ident)
        start, goal = _node(raw["start"], layers), _node(raw["goal"], layers)
        if start == goal:
            raise StudioError("Epic journey must move between distinct source tiles")
        cases.append((ident, start, goal, raw["require_alternate"]))
    return layers, tuple(normalized_connectors), edges, tuple(cases)


def _neighbors(node: Node, layers: Mapping[str, Any],
               transfers: Mapping[Node, Sequence[tuple[Node, str]]]):
    layer_id, x, y = node
    layer = layers[layer_id]
    for dx, dy in _NEIGHBOURS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < layer.width and 0 <= ny < layer.height and _traversable(layer, nx, ny):
            yield (layer_id, nx, ny), None
    yield from transfers.get(node, ())


def _path(start: Node, goal: Node, layers: Mapping[str, Any],
          transfers: Mapping[Node, Sequence[tuple[Node, str]]],
          forbidden: frozenset[Node] = frozenset()
          ) -> tuple[tuple[Node, ...], tuple[str, ...]]:
    if start in forbidden or goal in forbidden:
        return (), ()
    queue = deque([start])
    parents: dict[Node, tuple[Node, str | None] | None] = {start: None}
    while queue:
        node = queue.popleft()
        if node == goal:
            result: list[Node] = []
            connector_ids: list[str] = []
            at = goal
            while True:
                result.append(at)
                parent = parents[at]
                if parent is None:
                    break
                at, connector = parent
                if connector is not None:
                    connector_ids.append(connector)
            return tuple(reversed(result)), tuple(reversed(connector_ids))
        for nxt, connector in _neighbors(node, layers, transfers):
            if nxt not in forbidden and nxt not in parents:
                parents[nxt] = (node, connector)
                queue.append(nxt)
    return (), ()


def _witness(nodes: tuple[Node, ...], connectors: tuple[str, ...]) -> dict[str, Any]:
    if not nodes:
        return {
            "reachable": False, "steps": None, "transfers": 0,
            "connector_ids": [], "path_sha256": None,
            "sample": [], "sample_truncated": False,
        }
    steps = [list(v) for v in nodes]
    sample = (steps[:_SAMPLE // 2] + steps[-_SAMPLE // 2:]
              if len(steps) > _SAMPLE else steps)
    return {
        "reachable": True, "steps": len(steps)-1,
        "transfers": len(connectors), "connector_ids": list(connectors),
        "path_sha256": _hash(steps), "sample": sample,
        "sample_truncated": len(steps) > _SAMPLE,
    }


def audit_epic_interlayer_routes(project: StudioProject, request: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct native-safe-source references, 1..32 journeys, no mutation.

    Alternate witness requires interior-vertex disjointness. Traversal cannot
    claim an actual native portal, physics or seamless streaming transition.
    """
    layers, connectors, transitions, cases = _input(project, request)
    evidence = []
    passed = 0
    for journey_id, start, goal, alternate_required in cases:
        first, first_edges = _path(start, goal, layers, transitions)
        alternate, alternate_edges = (
            _path(start, goal, layers, transitions, frozenset(first[1:-1]))
            if alternate_required and first else ((), ())
        )
        good = bool(first) and (not alternate_required or bool(alternate))
        passed += int(good)
        evidence.append({
            "journey_id": journey_id,
            "start": list(start), "goal": list(goal),
            "require_alternate": alternate_required,
            "primary": _witness(first, first_edges),
            "alternate": _witness(alternate, alternate_edges) if alternate_required else None,
            "passed": good,
            "failure": None if good else (
                "no_source_tile_path" if not first
                else "no_vertex_disjoint_alternative"),
        })
    receipt = {
        "schema": "skeleton.forge.epic_interlayer_reference.v1",
        "project_id": project.project_id,
        "project_sha256": project_digest(project),
        "layer_ids": list(layers),
        "layer_source_sha256": {
            key: _hash({
                "palette": layer.palette, "data": layer.data,
                "width": layer.width, "height": layer.height,
                "elevation_m": layer.elevation_m,
            }) for key, layer in layers.items()
        },
        "connectors": list(connectors),
        "journey_count": len(cases), "passed_count": passed,
        "failed_count": len(cases)-passed, "journeys": evidence,
        "native_engine_executed": False, "source_reference_only": True,
        "transport_actions_applied": False, "release_certified": False,
    }
    return {**receipt, "receipt_sha256": _hash(receipt)}


def verify_epic_interlayer_routes(project: StudioProject, request: Mapping[str, Any],
                                  expected: Mapping[str, Any]) -> bool:
    """Independent deterministic replay against a claimed full signed report."""
    if type(expected) is not dict:
        return False
    try:
        actual = audit_epic_interlayer_routes(project, request)
    except (StudioError, TypeError, ValueError):
        return False
    return actual == expected and _hash(actual) == _hash(expected)


def compare_epic_interlayer_routes(before: Mapping[str, Any],
                                   after: Mapping[str, Any]) -> dict[str, Any]:
    """Objectively compare identical itinerary proposals across two project SHA."""
    for report in (before, after):
        if type(report) is not dict or report.get("schema") != "skeleton.forge.epic_interlayer_reference.v1":
            raise StudioError("Epic route comparison needs exact full source reports")
        payload = {k: v for k, v in report.items() if k != "receipt_sha256"}
        if report.get("receipt_sha256") != _hash(payload):
            raise StudioError("Epic route comparison receipt was modified")
    def context(report):
        return (
            report["project_id"], report["layer_ids"], report["connectors"],
            [(r["journey_id"], r["start"], r["goal"], r["require_alternate"])
             for r in report["journeys"]],
        )
    if context(before) != context(after):
        raise StudioError("Epic source navigation comparisons require identical journeys")
    improved = [n["journey_id"] for o, n in zip(before["journeys"], after["journeys"])
                if not o["passed"] and n["passed"]]
    regressed = [n["journey_id"] for o, n in zip(before["journeys"], after["journeys"])
                 if o["passed"] and not n["passed"]]
    outcome = {
        "schema": "skeleton.forge.epic_interlayer_comparison.v1",
        "baseline_sha256": before["project_sha256"],
        "candidate_sha256": after["project_sha256"],
        "improved": improved, "regressed": regressed,
        "strict_improvement": bool(improved) and not regressed,
        "native_engine_executed": False, "release_certified": False,
    }
    return {**outcome, "receipt_sha256": _hash(outcome)}
