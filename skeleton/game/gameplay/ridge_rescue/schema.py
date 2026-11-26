"""Strict, bounded source contract for an original grid-based rescue game."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import json

MAX_DIM = 24
MAX_OBJECTS = 96
MAX_SOURCE_BYTES = 96_000
ITEMS = frozenset({"wood", "ore", "herb", "torch", "bandage", "signal"})
RECIPES = {"torch": {"wood": 2, "ore": 1}, "bandage": {"herb": 2}, "signal": {"ore": 2, "wood": 1}}
TERRAIN = frozenset({".", "#", "~", "^"})
class WorldError(ValueError):
    pass

def _obj(value: Any, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise WorldError(f"{label}: invalid fields")
    return value

def _text(value: Any, label: str, maxlen: int = 64) -> str:
    if not isinstance(value, str) or not value or len(value) > maxlen or not value.isascii():
        raise WorldError(f"{label}: invalid text")
    if any(ord(c) < 32 for c in value):
        raise WorldError(f"{label}: control character")
    return value

def _point(value: Any, width: int, height: int, label: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2 or any(type(n) is not int for n in value):
        raise WorldError(f"{label}: invalid coordinates")
    x, y = value
    if not (0 <= x < width and 0 <= y < height):
        raise WorldError(f"{label}: out of bounds")
    return x, y

@dataclass(frozen=True)
class World:
    name: str
    rows: tuple[str, ...]
    start: tuple[int, int]
    shelter: tuple[int, int]
    civilians: tuple[tuple[str, tuple[int, int]], ...]
    raiders: tuple[tuple[str, tuple[int, int]], ...]
    resources: tuple[tuple[str, str, tuple[int, int], int], ...]
    max_turns: int
    @property
    def width(self) -> int:
        return len(self.rows[0])
    @property
    def height(self) -> int:
        return len(self.rows)
    def tile(self, p: tuple[int, int]) -> str:
        return self.rows[p[1]][p[0]]
    def walkable(self, p: tuple[int, int]) -> bool:
        x, y = p
        return 0 <= x < self.width and 0 <= y < self.height and self.tile(p) != "#"

def parse_world(source: dict[str, Any] | str | bytes) -> World:
    if isinstance(source, bytes):
        if len(source) > MAX_SOURCE_BYTES:
            raise WorldError("source too large")
        try:
            source = source.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorldError("source not utf8") from exc
    if isinstance(source, str):
        if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise WorldError("source too large")
        try:
            source = json.loads(source)
        except (ValueError, TypeError) as exc:
            raise WorldError("invalid JSON") from exc
    data = _obj(source, {"schema", "name", "rows", "start", "shelter", "civilians", "raiders", "resources", "max_turns"}, "world")
    if data["schema"] != "ridge.rescue.world.v1":
        raise WorldError("unsupported world schema")
    rows = data["rows"]
    if not isinstance(rows, list) or not rows or len(rows) > MAX_DIM or not all(isinstance(row, str) for row in rows):
        raise WorldError("invalid rows")
    width = len(rows[0])
    if not (3 <= width <= MAX_DIM) or any(len(row) != width or set(row) - TERRAIN for row in rows):
        raise WorldError("nonrectangular or invalid terrain")
    height = len(rows)
    name = _text(data["name"], "name")
    start = _point(data["start"], width, height, "start")
    shelter = _point(data["shelter"], width, height, "shelter")
    def walk(p: tuple[int, int], label: str) -> None:
        if rows[p[1]][p[0]] in {"#", "~"}:
            raise WorldError(f"{label}: impassable tile")
    walk(start, "start")
    walk(shelter, "shelter")
    if start == shelter:
        raise WorldError("start and shelter must differ")
    occupied: set[tuple[int, int]] = {start, shelter}
    ids: set[str] = set()
    def actors(key: str) -> tuple[tuple[str, tuple[int, int]], ...]:
        values = data[key]
        if not isinstance(values, list) or len(values) > MAX_OBJECTS:
            raise WorldError(f"{key}: invalid count")
        result = []
        for value in values:
            entry = _obj(value, {"id", "at"}, key)
            ident = _text(entry["id"], f"{key}.id")
            at = _point(entry["at"], width, height, key)
            walk(at, key)
            if ident in ids or at in occupied:
                raise WorldError(f"{key}: duplicate id or position")
            ids.add(ident)
            occupied.add(at)
            result.append((ident, at))
        return tuple(sorted(result))
    civilians = actors("civilians")
    if not civilians:
        raise WorldError("world needs civilians")
    raiders = actors("raiders")
    resources = data["resources"]
    if not isinstance(resources, list) or len(resources) > MAX_OBJECTS:
        raise WorldError("resources: invalid count")
    nodes = []
    for entry in resources:
        e = _obj(entry, {"id", "kind", "at", "count"}, "resource")
        ident = _text(e["id"], "resource.id")
        kind = e["kind"]
        at = _point(e["at"], width, height, "resource")
        count = e["count"]
        if not isinstance(kind, str) or kind not in {"wood", "ore", "herb"} or type(count) is not int or not 1 <= count <= 12:
            raise WorldError("resource: invalid kind or quantity")
        walk(at, "resource")
        if ident in ids or at in occupied:
            raise WorldError("resource: duplicate id or position")
        ids.add(ident)
        occupied.add(at)
        nodes.append((ident, kind, at, count))
    turns = data["max_turns"]
    if type(turns) is not int or not 8 <= turns <= 256:
        raise WorldError("max_turns out of bounds")
    return World(name, tuple(rows), start, shelter, civilians, raiders, tuple(sorted(nodes)), turns)

def world_dict(world: World) -> dict:
    return {
        "schema": "ridge.rescue.world.v1", "name": world.name, "rows": list(world.rows),
        "start": list(world.start), "shelter": list(world.shelter),
        "civilians": [{"id": ident, "at": list(at)} for ident, at in world.civilians],
        "raiders": [{"id": ident, "at": list(at)} for ident, at in world.raiders],
        "resources": [{"id": ident, "kind": kind, "at": list(at), "count": count} for ident, kind, at, count in world.resources],
        "max_turns": world.max_turns,
    }
