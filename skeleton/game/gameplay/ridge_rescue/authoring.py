"""Immutable source revisions with optimistic CAS and static reachability checks."""
from __future__ import annotations
from copy import deepcopy
from typing import Any
from .schema import World, WorldError, parse_world, world_dict
from .custody import digest
from .guidance import route

class AuthoringError(ValueError):
    pass

def validate_reachability(world: World) -> None:
    if route(world, world.start, world.shelter) is None:
        raise AuthoringError("shelter unreachable from spawn")
    for ident, at in world.civilians:
        if not any(route(world, world.start, (at[0] + dx, at[1] + dy)) is not None for dx, dy in ((1,0),(-1,0),(0,1),(0,-1))):
            raise AuthoringError(f"civilian unreachable: {ident}")
    for ident, _, at, _ in world.resources:
        if not any(route(world, world.start, (at[0] + dx, at[1] + dy)) is not None for dx, dy in ((1,0),(-1,0),(0,1),(0,-1))):
            raise AuthoringError(f"resource unreachable: {ident}")

def revise(world: World, *, expected_sha256: str, operation: dict[str, Any]) -> dict:
    before = world_dict(world)
    if digest(before) != expected_sha256:
        raise AuthoringError("source revision conflict")
    if not isinstance(operation, dict) or set(operation) != {"kind", "target", "value"}:
        raise AuthoringError("malformed authoring operation")
    data = deepcopy(before)
    kind, target, value = operation["kind"], operation["target"], operation["value"]
    if not isinstance(kind, str):
        raise AuthoringError("invalid operation kind")
    if kind == "rename":
        if target != "world" or not isinstance(value, str):
            raise AuthoringError("invalid rename")
        data["name"] = value
    elif kind == "set-turn-budget":
        if target != "world":
            raise AuthoringError("invalid budget target")
        data["max_turns"] = value
    elif kind in {"move-civilian", "move-raider", "move-resource", "set-resource-count"}:
        collection = {"move-civilian": "civilians", "move-raider": "raiders", "move-resource": "resources", "set-resource-count": "resources"}[kind]
        matches = [entry for entry in data[collection] if entry["id"] == target]
        if len(matches) != 1:
            raise AuthoringError("unknown or duplicate target")
        matches[0]["count" if kind == "set-resource-count" else "at"] = value
    elif kind == "set-tile":
        if not isinstance(target, list) or len(target) != 2 or any(type(n) is not int for n in target):
            raise AuthoringError("invalid tile target")
        x, y = target
        if not (0 <= y < len(data["rows"]) and 0 <= x < len(data["rows"][0])):
            raise AuthoringError("tile out of bounds")
        if not isinstance(value, str) or value not in {".", "#", "~", "^"}:
            raise AuthoringError("invalid terrain")
        row = data["rows"][y]
        data["rows"][y] = row[:x] + value + row[x + 1:]
    else:
        raise AuthoringError("unsupported authoring operation")
    try:
        after = parse_world(data)
        validate_reachability(after)
    except WorldError as exc:
        raise AuthoringError(str(exc)) from exc
    return {"schema": "ridge.rescue.revision.v1", "previous_sha256": expected_sha256, "sha256": digest(world_dict(after)), "world": world_dict(after)}

def verify_revision(before: World, revision: dict, operation: dict) -> bool:
    if not isinstance(revision, dict) or set(revision) != {"schema", "previous_sha256", "sha256", "world"}:
        raise AuthoringError("invalid revision")
    if revision["schema"] != "ridge.rescue.revision.v1":
        raise AuthoringError("invalid revision schema")
    expected = revise(before, expected_sha256=digest(world_dict(before)), operation=operation)
    if expected != revision:
        raise AuthoringError("revision does not replay")
    return True
