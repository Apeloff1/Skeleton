"""B035 — Narrative planner and canon graph.

Success criterion (game_creation_batches.json): "Narrative generation
preserves canon, arcs, constraints and consequences across edits."

* :class:`CanonGraph` — typed entities, attribute facts and relations. Seeded
  from B032's ``DESIGN`` plane via :func:`canon_from_memory`.
* :class:`Beat` — one story step: which entities take part, preconditions on
  canon state, and :class:`Effect` consequences it applies.
* :class:`NarrativePlan` — ordered arcs of beats. :meth:`NarrativePlan.validate`
  replays every beat over a copy of canon and reports each violation: unknown
  entities, dead/absent participants, failed preconditions, broken arc order,
  and hard constraints (``never`` facts). Edits (insert/replace/remove) return
  a new plan and are rejected if they introduce violations, so canon, arcs and
  downstream consequences stay consistent across edits.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

SCHEMA = "gameforge.b035.canon.v1"


class CanonError(ValueError):
    pass


@dataclass(frozen=True)
class Effect:
    entity: str
    attr: str
    value: str


@dataclass(frozen=True)
class Beat:
    beat_id: str
    arc: str
    participants: tuple[str, ...]
    requires: tuple[Effect, ...] = ()  # entity.attr must equal value before the beat
    effects: tuple[Effect, ...] = ()
    summary: str = ""


@dataclass(frozen=True)
class Arc:
    arc_id: str
    milestones: tuple[str, ...]  # beat ids that must appear in this order


@dataclass(frozen=True)
class Violation:
    beat_id: str
    code: str
    detail: str


@dataclass
class CanonGraph:
    entities: dict[str, str] = field(default_factory=dict)  # id -> kind
    facts: dict[tuple[str, str], str] = field(default_factory=dict)
    relations: set[tuple[str, str, str]] = field(default_factory=set)
    never: set[tuple[str, str, str]] = field(default_factory=set)  # forbidden (entity, attr, value)
    locked: set[tuple[str, str]] = field(default_factory=set)  # immutable canon facts

    def add_entity(self, eid: str, kind: str, **attrs: str) -> None:
        if not eid or not kind:
            raise CanonError("entity id and kind required")
        if eid in self.entities:
            raise CanonError(f"duplicate entity {eid!r}")
        self.entities[eid] = kind
        self.facts[(eid, "status")] = attrs.pop("status", "alive")
        for k, v in attrs.items():
            self.facts[(eid, k)] = v

    def relate(self, a: str, rel: str, b: str) -> None:
        for e in (a, b):
            if e not in self.entities:
                raise CanonError(f"unknown entity {e!r}")
        self.relations.add((a, rel, b))

    def forbid(self, entity: str, attr: str, value: str) -> None:
        self.never.add((entity, attr, value))

    def lock(self, entity: str, attr: str) -> None:
        if (entity, attr) not in self.facts:
            raise CanonError("can only lock an existing fact")
        self.locked.add((entity, attr))

    def copy(self) -> CanonGraph:
        return CanonGraph(dict(self.entities), dict(self.facts), set(self.relations), set(self.never),
                          set(self.locked))

    def digest(self) -> str:
        body = {"s": SCHEMA, "e": sorted(self.entities.items()), "f": sorted([*k, v] for k, v in self.facts.items()),
                "r": sorted(self.relations), "n": sorted(self.never), "l": sorted(self.locked)}
        return hashlib.sha256(json.dumps(body).encode()).hexdigest()[:16]


def canon_from_memory(planes, *, tick: int | None = None) -> CanonGraph:
    """Build canon from B032 ``DESIGN`` entries keyed ``entity:<id>`` (value = kind)
    and ``fact:<id>.<attr>`` (value = fact). Facts tagged ``canon`` are locked."""
    from skeleton.gameforge.batch_b032 import MemoryPlane

    g = CanonGraph()
    design = planes.live(MemoryPlane.DESIGN, tick=tick)
    for e in design:
        if e.key.startswith("entity:"):
            g.add_entity(e.key[len("entity:"):], e.value)
    for e in design:
        if e.key.startswith("fact:"):
            ent, _, attr = e.key[len("fact:"):].partition(".")
            if ent not in g.entities or not attr:
                raise CanonError(f"fact {e.key!r} references unknown entity")
            g.facts[(ent, attr)] = e.value
            if "canon" in e.tags:
                g.locked.add((ent, attr))
    return g


@dataclass(frozen=True)
class NarrativePlan:
    beats: tuple[Beat, ...]
    arcs: tuple[Arc, ...] = ()

    # -- validation -------------------------------------------------------
    def replay(self, canon: CanonGraph) -> tuple[CanonGraph, list[Violation]]:
        state = canon.copy()
        out: list[Violation] = []
        seen: set[str] = set()
        for b in self.beats:
            if b.beat_id in seen:
                out.append(Violation(b.beat_id, "duplicate_beat", b.beat_id))
            seen.add(b.beat_id)
            for p in b.participants:
                if p not in state.entities:
                    out.append(Violation(b.beat_id, "unknown_entity", p))
                elif state.facts.get((p, "status")) == "dead":
                    out.append(Violation(b.beat_id, "dead_participant", p))
            for r in b.requires:
                have = state.facts.get((r.entity, r.attr))
                if have != r.value:
                    out.append(Violation(b.beat_id, "precondition", f"{r.entity}.{r.attr}={have!r}, need {r.value!r}"))
            for ef in b.effects:
                if ef.entity not in state.entities:
                    out.append(Violation(b.beat_id, "unknown_entity", ef.entity))
                    continue
                if (ef.entity, ef.attr) in state.locked:
                    out.append(Violation(b.beat_id, "locked_fact", f"{ef.entity}.{ef.attr}"))
                    continue
                if (ef.entity, ef.attr, ef.value) in state.never:
                    out.append(Violation(b.beat_id, "forbidden", f"{ef.entity}.{ef.attr}={ef.value}"))
                    continue
                state.facts[(ef.entity, ef.attr)] = ef.value
        order = [b.beat_id for b in self.beats]
        for arc in self.arcs:
            pos = []
            for m in arc.milestones:
                if m not in order:
                    out.append(Violation(m, "missing_milestone", arc.arc_id))
                else:
                    pos.append(order.index(m))
            if pos != sorted(pos):
                out.append(Violation(arc.arc_id, "arc_order", ",".join(arc.milestones)))
        return state, out

    def validate(self, canon: CanonGraph) -> list[Violation]:
        return self.replay(canon)[1]

    def consequences(self, canon: CanonGraph) -> dict[tuple[str, str], str]:
        end, _ = self.replay(canon)
        return {k: v for k, v in end.facts.items() if canon.facts.get(k) != v}

    # -- edits ------------------------------------------------------------
    def _checked(self, plan: NarrativePlan, canon: CanonGraph) -> NarrativePlan:
        before = {(v.beat_id, v.code, v.detail) for v in self.validate(canon)}
        new = [v for v in plan.validate(canon) if (v.beat_id, v.code, v.detail) not in before]
        if new:
            raise CanonError("edit breaks canon: " + "; ".join(f"{v.code}@{v.beat_id}: {v.detail}" for v in new))
        return plan

    def _index(self, beat_id: str) -> int:
        for i, b in enumerate(self.beats):
            if b.beat_id == beat_id:
                return i
        raise CanonError(f"unknown beat {beat_id!r}")

    def insert_after(self, anchor: str | None, beat: Beat, canon: CanonGraph) -> NarrativePlan:
        i = -1 if anchor is None else self._index(anchor)
        beats = self.beats[: i + 1] + (beat,) + self.beats[i + 1:]
        return self._checked(replace(self, beats=beats), canon)

    def replace_beat(self, beat: Beat, canon: CanonGraph) -> NarrativePlan:
        i = self._index(beat.beat_id)
        return self._checked(replace(self, beats=self.beats[:i] + (beat,) + self.beats[i + 1:]), canon)

    def remove(self, beat_id: str, canon: CanonGraph) -> NarrativePlan:
        i = self._index(beat_id)
        return self._checked(replace(self, beats=self.beats[:i] + self.beats[i + 1:]), canon)

    def beats_for(self, entity: str) -> list[str]:
        return [b.beat_id for b in self.beats if entity in b.participants]


def plan(beats: Iterable[Beat], arcs: Iterable[Arc] = ()) -> NarrativePlan:
    return NarrativePlan(tuple(beats), tuple(arcs))
