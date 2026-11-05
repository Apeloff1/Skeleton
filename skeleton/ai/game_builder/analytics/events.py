"""Typed gameplay event schema (``skeleton.game_builder.analytics.event.v1``)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

SCHEMA = "skeleton.game_builder.analytics.event.v1"
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")
MAX_ATTRS = 8
MAX_STR = 64
# Attribute names that suggest personal data are refused outright.
PII_KEYS = re.compile(
    r"(^|_)(e-?mail|phone|name|address|ip|ip_?addr|device|imei|idfa|gaid|mac|location|lat|lon|gps|"
    r"birth|age|gender|user(_?id)?|account|token|password|ssn)$", re.I)
_PII_VALUE = re.compile(
    r"[^@\s]+@[^@\s]+\.[^@\s]+|\b\d{1,3}(?:\.\d{1,3}){3}\b|\+?\d[\d\s().-]{7,}\d|[0-9a-f]{2}(?::[0-9a-f]{2}){5}", re.I)


class EventError(ValueError):
    """Event does not match the schema or carries personal data."""


class EventType(str, Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    LEVEL_START = "level_start"
    LEVEL_COMPLETE = "level_complete"
    LEVEL_FAIL = "level_fail"
    ENCOUNTER_START = "encounter_start"
    ENCOUNTER_COMPLETE = "encounter_complete"
    ENCOUNTER_FAIL = "encounter_fail"
    DEATH = "death"
    CHECKPOINT = "checkpoint"
    ITEM = "item"
    QUIT = "quit"


LEVEL_TYPES = frozenset({EventType.LEVEL_START, EventType.LEVEL_COMPLETE, EventType.LEVEL_FAIL})
ENCOUNTER_TYPES = frozenset({EventType.ENCOUNTER_START, EventType.ENCOUNTER_COMPLETE, EventType.ENCOUNTER_FAIL})


def _id(v: Any, name: str, *, optional: bool = False) -> str | None:
    if v is None and optional:
        return None
    if not isinstance(v, str) or not _ID.fullmatch(v):
        raise EventError(f"{name} must match {_ID.pattern}")
    return v


def _num(v: Any, name: str, *, optional: bool = False) -> float | None:
    if v is None and optional:
        return None
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise EventError(f"{name} must be a finite number")
    return float(v)


def clean_attrs(attrs: Mapping[str, Any] | None) -> tuple[tuple[str, Any], ...]:
    if not attrs:
        return ()
    if not isinstance(attrs, Mapping) or len(attrs) > MAX_ATTRS:
        raise EventError(f"attrs must be a mapping of at most {MAX_ATTRS} entries")
    out = []
    for k, v in sorted(attrs.items()):
        if not isinstance(k, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", k):
            raise EventError(f"bad attr key {k!r}")
        if PII_KEYS.search(k):
            raise EventError(f"attr {k!r} looks like personal data")
        if isinstance(v, str):
            if len(v) > MAX_STR or _PII_VALUE.search(v):
                raise EventError(f"attr {k!r} value too long or looks like personal data")
        elif v is not None and not isinstance(v, bool):
            _num(v, f"attr {k}")
        out.append((k, v))
    return tuple(out)


@dataclass(frozen=True)
class GameplayEvent:
    """One gameplay event. ``player`` is always a pseudonym, never a raw account id.

    ``t`` is seconds since session start; ``day`` is the coarse UTC day number
    (days since epoch) used only for retention cohorts.
    """

    player: str
    session_id: str
    seq: int
    t: float
    type: EventType
    day: int = 0
    level_id: str | None = None
    encounter_id: str | None = None
    x: float | None = None
    y: float | None = None
    attrs: tuple[tuple[str, Any], ...] = field(default=())

    def __post_init__(self) -> None:
        _id(self.player, "player")
        _id(self.session_id, "session_id")
        if isinstance(self.seq, bool) or not isinstance(self.seq, int) or self.seq < 0:
            raise EventError("seq must be a non-negative int")
        if _num(self.t, "t") < 0:
            raise EventError("t must be >= 0")
        if isinstance(self.day, bool) or not isinstance(self.day, int) or self.day < 0:
            raise EventError("day must be a non-negative int")
        try:
            object.__setattr__(self, "type", EventType(self.type))
        except ValueError as exc:
            raise EventError(f"unknown event type {self.type!r}") from exc
        _id(self.level_id, "level_id", optional=True)
        _id(self.encounter_id, "encounter_id", optional=True)
        if self.type in LEVEL_TYPES and self.level_id is None:
            raise EventError(f"{self.type.value} needs level_id")
        if self.type in ENCOUNTER_TYPES and (self.level_id is None or self.encounter_id is None):
            raise EventError(f"{self.type.value} needs level_id and encounter_id")
        _num(self.x, "x", optional=True)
        _num(self.y, "y", optional=True)
        object.__setattr__(self, "attrs", clean_attrs(dict(self.attrs)))

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> GameplayEvent:
        if d.get("schema", SCHEMA) != SCHEMA:
            raise EventError("unsupported event schema")
        known = {"player", "session_id", "seq", "t", "type", "day", "level_id", "encounter_id", "x", "y", "attrs"}
        extra = set(d) - known - {"schema"}
        if extra:
            raise EventError(f"unknown event fields {sorted(extra)}")
        kw = {k: d[k] for k in known if k in d}
        kw["attrs"] = tuple(clean_attrs(d.get("attrs")))
        return cls(**kw)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"schema": SCHEMA, "player": self.player, "session_id": self.session_id,
                             "seq": self.seq, "t": self.t, "type": self.type.value, "day": self.day}
        for k in ("level_id", "encounter_id", "x", "y"):
            if getattr(self, k) is not None:
                d[k] = getattr(self, k)
        if self.attrs:
            d["attrs"] = dict(self.attrs)
        return d
