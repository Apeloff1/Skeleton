"""B032 — Project memory planes.

Success criterion (game_creation_batches.json): "Design facts, ephemeral
context, evidence and long-lived decisions are separately governed and
retrievable."

Four planes, each with its own governance policy:

* ``DESIGN`` — design facts. Mutable only by explicit supersession; history kept.
* ``EPHEMERAL`` — session context. Bounded, TTL-expired on a logical clock, never
  promoted implicitly.
* ``EVIDENCE`` — append-only, digest-bound observations; cannot be superseded.
* ``DECISION`` — long-lived decisions. Must cite at least one evidence or design
  entry that exists, and supersession requires a recorded rationale.

All writes are scoped to one (tenant, project, trust_class) boundary, mirroring
:mod:`skeleton.ai.project_memory`; cross-boundary writes fail closed. Time is a
caller-supplied logical tick, so behaviour is deterministic and replayable.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

SCHEMA = "gameforge.b032.memory_planes.v1"
MAX_TEXT = 2048
MAX_TAGS = 16


class MemoryError_(ValueError):
    """A memory write or query violates a plane's governance policy."""


class MemoryPlane(str, Enum):
    DESIGN = "design"
    EPHEMERAL = "ephemeral"
    EVIDENCE = "evidence"
    DECISION = "decision"


@dataclass(frozen=True)
class PlanePolicy:
    plane: MemoryPlane
    supersedable: bool
    requires_citation: bool
    requires_digest: bool
    max_entries: int
    ttl_ticks: int | None  # None = never expires


PLANE_POLICIES: dict[MemoryPlane, PlanePolicy] = {
    MemoryPlane.DESIGN: PlanePolicy(MemoryPlane.DESIGN, True, False, False, 4096, None),
    MemoryPlane.EPHEMERAL: PlanePolicy(MemoryPlane.EPHEMERAL, True, False, False, 256, 64),
    MemoryPlane.EVIDENCE: PlanePolicy(MemoryPlane.EVIDENCE, False, False, True, 8192, None),
    MemoryPlane.DECISION: PlanePolicy(MemoryPlane.DECISION, True, True, False, 1024, None),
}


@dataclass(frozen=True)
class PlaneScope:
    tenant_id: str
    project_id: str
    trust_class: str

    def __post_init__(self) -> None:
        for name in ("tenant_id", "project_id", "trust_class"):
            v = getattr(self, name)
            if not isinstance(v, str) or not v or len(v) > 128:
                raise MemoryError_(f"{name} must be a non-empty string")


def _digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class MemoryEntry:
    entry_id: str
    plane: MemoryPlane
    key: str
    value: str
    source_id: str
    tick: int
    tags: tuple[str, ...] = ()
    cites: tuple[str, ...] = ()
    supersedes: str | None = None
    rationale: str = ""
    content_digest: str = ""

    def body(self) -> dict:
        return {"plane": self.plane.value, "key": self.key, "value": self.value, "source_id": self.source_id,
                "tick": self.tick, "tags": list(self.tags), "cites": list(self.cites),
                "supersedes": self.supersedes, "rationale": self.rationale}


@dataclass
class ProjectMemoryPlanes:
    """Governed, separately-retrievable memory planes for one project boundary."""
    scope: PlaneScope
    _entries: dict[str, MemoryEntry] = field(default_factory=dict)
    _order: list[str] = field(default_factory=list)
    _superseded: set[str] = field(default_factory=set)
    audit: list[tuple[int, str, str, str]] = field(default_factory=list)

    # -- writes -----------------------------------------------------------
    def write(self, scope: PlaneScope, plane: MemoryPlane, key: str, value: str, *, source_id: str, tick: int,
              tags: Iterable[str] = (), cites: Iterable[str] = (), supersedes: str | None = None,
              rationale: str = "", content_digest: str = "") -> MemoryEntry:
        try:
            entry = self._admit(scope, MemoryPlane(plane), key, value, source_id, tick, tuple(tags), tuple(cites),
                                supersedes, rationale, content_digest)
        except MemoryError_ as exc:
            self.audit.append((tick if isinstance(tick, int) else -1, "deny", str(plane), str(exc)))
            raise
        self._entries[entry.entry_id] = entry
        self._order.append(entry.entry_id)
        if supersedes:
            self._superseded.add(supersedes)
        self.audit.append((tick, "admit", entry.plane.value, entry.entry_id))
        return entry

    def _admit(self, scope, plane, key, value, source_id, tick, tags, cites, supersedes, rationale, cdigest):
        if scope != self.scope:
            raise MemoryError_("cross-boundary memory write")
        pol = PLANE_POLICIES[plane]
        for name, v in (("key", key), ("value", value), ("source_id", source_id)):
            if not isinstance(v, str) or not v or len(v) > MAX_TEXT or "\x00" in v:
                raise MemoryError_(f"{name} must be a non-empty string")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise MemoryError_("tick must be a non-negative int")
        if self._order and tick < self._entries[self._order[-1]].tick:
            raise MemoryError_("tick must be monotonic")
        if len(tags) > MAX_TAGS or not all(isinstance(t, str) and t for t in tags):
            raise MemoryError_("invalid tags")
        if len(self.live(plane, tick=tick)) >= pol.max_entries:
            raise MemoryError_(f"{plane.value} plane is full")
        if pol.requires_digest:
            expected = hashlib.sha256(value.encode()).hexdigest()
            if cdigest != expected:
                raise MemoryError_("evidence must be bound to sha256(value)")
        if pol.requires_citation:
            if not cites:
                raise MemoryError_("decisions must cite evidence or design entries")
            for c in cites:
                ref = self._entries.get(c)
                if ref is None or ref.plane not in (MemoryPlane.EVIDENCE, MemoryPlane.DESIGN):
                    raise MemoryError_(f"citation {c!r} is not a known evidence/design entry")
        elif cites:
            for c in cites:
                if c not in self._entries:
                    raise MemoryError_(f"unknown citation {c!r}")
        if supersedes is not None:
            if not pol.supersedable:
                raise MemoryError_(f"{plane.value} plane is append-only")
            prev = self._entries.get(supersedes)
            if prev is None or prev.plane is not plane:
                raise MemoryError_("supersedes must name an entry in the same plane")
            if supersedes in self._superseded:
                raise MemoryError_("entry already superseded")
            if prev.key != key:
                raise MemoryError_("supersession must keep the key")
            if plane is MemoryPlane.DECISION and not rationale:
                raise MemoryError_("superseding a decision requires a rationale")
        else:
            current = self.get(plane, key, tick=tick)
            if current is not None:
                raise MemoryError_("key already has a live entry; supersede it explicitly")
        entry = MemoryEntry("", plane, key, value, source_id, tick, tags, cites, supersedes, rationale, cdigest)
        eid = _digest({"schema": SCHEMA, "scope": [scope.tenant_id, scope.project_id, scope.trust_class],
                       **entry.body()})[:24]
        return MemoryEntry(eid, plane, key, value, source_id, tick, tags, cites, supersedes, rationale, cdigest)

    # -- reads ------------------------------------------------------------
    def _alive(self, e: MemoryEntry, tick: int | None) -> bool:
        if e.entry_id in self._superseded:
            return False
        ttl = PLANE_POLICIES[e.plane].ttl_ticks
        return not (ttl is not None and tick is not None and tick - e.tick >= ttl)

    def live(self, plane: MemoryPlane, *, tick: int | None = None) -> list[MemoryEntry]:
        plane = MemoryPlane(plane)
        return [self._entries[i] for i in self._order
                if self._entries[i].plane is plane and self._alive(self._entries[i], tick)]

    def get(self, plane: MemoryPlane, key: str, *, tick: int | None = None) -> MemoryEntry | None:
        for e in self.live(plane, tick=tick):
            if e.key == key:
                return e
        return None

    def history(self, entry_id: str) -> list[MemoryEntry]:
        """Supersession chain, oldest first, ending at ``entry_id``."""
        chain: list[MemoryEntry] = []
        cur = self._entries.get(entry_id)
        while cur is not None:
            chain.append(cur)
            cur = self._entries.get(cur.supersedes) if cur.supersedes else None
        return list(reversed(chain))

    def search(self, plane: MemoryPlane, *, tag: str | None = None, text: str | None = None,
               tick: int | None = None, limit: int = 50) -> list[MemoryEntry]:
        out = []
        for e in self.live(plane, tick=tick):
            if tag is not None and tag not in e.tags:
                continue
            if text is not None and text.lower() not in (e.key + " " + e.value).lower():
                continue
            out.append(e)
        return out[: max(0, limit)]

    def decision_support(self, decision_id: str) -> list[MemoryEntry]:
        d = self._entries.get(decision_id)
        if d is None or d.plane is not MemoryPlane.DECISION:
            raise MemoryError_("not a decision")
        return [self._entries[c] for c in d.cites]

    def stale_decisions(self, *, tick: int | None = None) -> list[MemoryEntry]:
        """Live decisions citing a design fact that has since been superseded."""
        return [d for d in self.live(MemoryPlane.DECISION, tick=tick)
                if any(c in self._superseded for c in d.cites)]

    def expire(self, tick: int) -> int:
        """Drop expired ephemeral entries; returns how many were dropped."""
        dead = [i for i in self._order if self._entries[i].plane is MemoryPlane.EPHEMERAL
                and not self._alive(self._entries[i], tick) and i not in self._superseded]
        for i in dead:
            self._superseded.add(i)
            self.audit.append((tick, "expire", MemoryPlane.EPHEMERAL.value, i))
        return len(dead)

    def snapshot_digest(self) -> str:
        return _digest({"schema": SCHEMA, "order": self._order, "superseded": sorted(self._superseded)})
