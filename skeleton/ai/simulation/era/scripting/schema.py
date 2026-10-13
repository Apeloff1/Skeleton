"""Canonical schema for era and room data (STU-ERAS slice 1).

Every spec is an immutable dataclass. Validation is fail-closed: anything
unknown, malformed, or dangling raises :class:`SchemaError` with a stable,
machine-readable ``code`` and a dotted ``path`` to the offending field.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "stu-eras/1"

IDENT = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
DIRECTIONS = (
    "north",
    "south",
    "east",
    "west",
    "up",
    "down",
    "in",
    "out",
)
OPPOSITE = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "up": "down",
    "down": "up",
    "in": "out",
    "out": "in",
}
ROOM_KINDS = ("hub", "corridor", "chamber", "arena", "safe", "boss", "secret")
MAX_ROOMS = 4096
MAX_TAGS = 32


class SchemaError(ValueError):
    """Raised when era/room data fails validation."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code} at {path}: {detail}")

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


def _ident(value: Any, path: str) -> str:
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise SchemaError("bad-ident", path, f"expected lowercase identifier, got {value!r}")
    return value


def _text(value: Any, path: str, *, required: bool = True, limit: int = 200) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise SchemaError("bad-text", path, "expected non-empty string")
    if len(value) > limit:
        raise SchemaError("text-too-long", path, f"max {limit} chars")
    return value


def _int(value: Any, path: str, *, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError("bad-int", path, f"expected int, got {type(value).__name__}")
    if not lo <= value <= hi:
        raise SchemaError("out-of-range", path, f"expected {lo}..{hi}, got {value}")
    return value


def _tags(value: Any, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise SchemaError("bad-tags", path, "expected list of identifiers")
    if len(value) > MAX_TAGS:
        raise SchemaError("too-many-tags", path, f"max {MAX_TAGS}")
    out = tuple(_ident(tag, f"{path}[{i}]") for i, tag in enumerate(value))
    if len(set(out)) != len(out):
        raise SchemaError("duplicate-tag", path, "tags must be unique")
    return out


def _only(data: dict[str, Any], allowed: set[str], path: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise SchemaError("unknown-field", f"{path}.{extra[0]}", f"allowed: {sorted(allowed)}")


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError("bad-type", path, f"expected object, got {type(value).__name__}")
    return value


@dataclass(frozen=True)
class ExitSpec:
    direction: str
    target: str
    locked: bool = False
    key: str = ""

    @classmethod
    def from_dict(cls, data: Any, path: str) -> "ExitSpec":
        data = _mapping(data, path)
        _only(data, {"direction", "target", "locked", "key"}, path)
        direction = data.get("direction")
        if direction not in DIRECTIONS:
            raise SchemaError("bad-direction", f"{path}.direction", f"one of {list(DIRECTIONS)}")
        locked = data.get("locked", False)
        if not isinstance(locked, bool):
            raise SchemaError("bad-bool", f"{path}.locked", "expected bool")
        key = data.get("key", "")
        if key:
            key = _ident(key, f"{path}.key")
        if locked and not key:
            raise SchemaError("locked-without-key", f"{path}.key", "locked exits need a key")
        return cls(
            direction=direction,
            target=_ident(data.get("target"), f"{path}.target"),
            locked=locked,
            key=key,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"direction": self.direction, "target": self.target}
        if self.locked:
            out["locked"] = True
        if self.key:
            out["key"] = self.key
        return out


@dataclass(frozen=True)
class RoomSpec:
    id: str
    name: str
    kind: str = "chamber"
    depth: int = 0
    tags: tuple[str, ...] = ()
    exits: tuple[ExitSpec, ...] = ()

    @classmethod
    def from_dict(cls, data: Any, path: str) -> "RoomSpec":
        data = _mapping(data, path)
        _only(data, {"id", "name", "kind", "depth", "tags", "exits"}, path)
        kind = data.get("kind", "chamber")
        if kind not in ROOM_KINDS:
            raise SchemaError("bad-room-kind", f"{path}.kind", f"one of {list(ROOM_KINDS)}")
        raw_exits = data.get("exits", [])
        if not isinstance(raw_exits, (list, tuple)):
            raise SchemaError("bad-exits", f"{path}.exits", "expected list")
        exits = tuple(ExitSpec.from_dict(e, f"{path}.exits[{i}]") for i, e in enumerate(raw_exits))
        seen: set[str] = set()
        for i, ex in enumerate(exits):
            if ex.direction in seen:
                raise SchemaError(
                    "duplicate-exit", f"{path}.exits[{i}].direction", f"{ex.direction} repeated"
                )
            seen.add(ex.direction)
        return cls(
            id=_ident(data.get("id"), f"{path}.id"),
            name=_text(data.get("name"), f"{path}.name"),
            kind=kind,
            depth=_int(data.get("depth", 0), f"{path}.depth", lo=0, hi=255),
            tags=_tags(data.get("tags"), f"{path}.tags"),
            exits=exits,
        )

    def exit(self, direction: str) -> ExitSpec | None:
        return next((e for e in self.exits if e.direction == direction), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "depth": self.depth,
            "tags": list(self.tags),
            "exits": [e.to_dict() for e in self.exits],
        }


@dataclass(frozen=True)
class EraSpec:
    id: str
    title: str
    start: str
    rooms: tuple[RoomSpec, ...]
    citation: str
    order: int = 0
    tags: tuple[str, ...] = ()
    schema: str = SCHEMA_VERSION
    _index: dict[str, RoomSpec] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_dict(cls, data: Any, path: str = "era") -> "EraSpec":
        data = _mapping(data, path)
        _only(data, {"schema", "id", "title", "order", "start", "citation", "tags", "rooms"}, path)
        schema = data.get("schema", SCHEMA_VERSION)
        if schema != SCHEMA_VERSION:
            raise SchemaError("bad-schema", f"{path}.schema", f"expected {SCHEMA_VERSION!r}")
        citation = _text(data.get("citation"), f"{path}.citation")
        if " " in citation:
            # Mirrors era.admit: spaced citation text is refused.
            raise SchemaError("bad-citation", f"{path}.citation", "citation must be a token")
        raw_rooms = data.get("rooms")
        if not isinstance(raw_rooms, (list, tuple)) or not raw_rooms:
            raise SchemaError("no-rooms", f"{path}.rooms", "an era needs at least one room")
        if len(raw_rooms) > MAX_ROOMS:
            raise SchemaError("too-many-rooms", f"{path}.rooms", f"max {MAX_ROOMS}")
        rooms = tuple(RoomSpec.from_dict(r, f"{path}.rooms[{i}]") for i, r in enumerate(raw_rooms))
        index: dict[str, RoomSpec] = {}
        for i, room in enumerate(rooms):
            if room.id in index:
                raise SchemaError("duplicate-room", f"{path}.rooms[{i}].id", room.id)
            index[room.id] = room
        start = _ident(data.get("start"), f"{path}.start")
        if start not in index:
            raise SchemaError("dangling-start", f"{path}.start", f"no room {start!r}")
        for i, room in enumerate(rooms):
            for j, ex in enumerate(room.exits):
                if ex.target not in index:
                    raise SchemaError(
                        "dangling-exit",
                        f"{path}.rooms[{i}].exits[{j}].target",
                        f"no room {ex.target!r}",
                    )
        return cls(
            id=_ident(data.get("id"), f"{path}.id"),
            title=_text(data.get("title"), f"{path}.title"),
            start=start,
            rooms=rooms,
            citation=citation,
            order=_int(data.get("order", 0), f"{path}.order", lo=0, hi=9999),
            tags=_tags(data.get("tags"), f"{path}.tags"),
            schema=schema,
            _index=index,
        )

    def room(self, room_id: str) -> RoomSpec:
        try:
            return self._index[room_id]
        except KeyError:
            raise SchemaError("unknown-room", f"era.{self.id}", room_id) from None

    @property
    def room_ids(self) -> tuple[str, ...]:
        return tuple(r.id for r in self.rooms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "id": self.id,
            "title": self.title,
            "order": self.order,
            "start": self.start,
            "citation": self.citation,
            "tags": list(self.tags),
            "rooms": [r.to_dict() for r in self.rooms],
        }
