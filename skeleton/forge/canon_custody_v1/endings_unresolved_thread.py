"""endings_unresolved_thread: deterministic, bounded narrative-canon custody.

An append-only record validator for authored story worlds. Every accepted
record is tied to its world, causal predecessor, revision, and opaque proof.
The trusted story runtime must authenticate evidence and persist the ledger.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

POLICY = "endings_unresolved_thread"
DOMAIN = "endings"
TOPIC = "unresolved_thread"
EVIDENCE_KIND = "source"
MAX_RECORDS = 80
MAX_GAP = 7
MAX_TICK = 2 ** 53 - 1
ACTIONS = ("establish", "amend", "reconcile")


@dataclass(frozen=True, slots=True)
class CanonRecord:
    identity: str
    entity: str
    action: str
    value: str
    predecessor: str
    evidence: str
    world: str
    tick: int
    revision: int

    def __post_init__(self) -> None:
        for attr in ("identity", "entity", "value", "evidence", "world"):
            value = getattr(self, attr)
            if type(value) is not str or not 1 <= len(value) <= 128:
                raise ValueError("invalid-" + attr)
        if type(self.predecessor) is not str or len(self.predecessor) > 128:
            raise ValueError("invalid-predecessor")
        if self.action not in ACTIONS or type(self.action) is not str:
            raise ValueError("invalid-action")
        if type(self.tick) is not int or not 0 <= self.tick <= MAX_TICK:
            raise ValueError("invalid-tick")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("invalid-revision")


@dataclass(frozen=True, slots=True)
class CanonLedger:
    world: str = "primary"
    revision: int = 0
    tick: int = 0
    entries: tuple[CanonRecord, ...] = ()

    def __post_init__(self) -> None:
        if type(self.world) is not str or not 1 <= len(self.world) <= 128:
            raise ValueError("invalid-world")
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("invalid-revision")
        if type(self.tick) is not int or not 0 <= self.tick <= MAX_TICK:
            raise ValueError("invalid-tick")
        if type(self.entries) is not tuple or len(self.entries) > MAX_RECORDS:
            raise ValueError("invalid-entries")
        identities = set()
        previous_tick = 0
        for index, entry in enumerate(self.entries):
            if type(entry) is not CanonRecord or entry.world != self.world:
                raise ValueError("world-boundary")
            if entry.identity in identities:
                raise ValueError("duplicate-canon-id")
            if entry.revision != index + 1 or entry.tick <= previous_tick:
                raise ValueError("noncanonical-record-order")
            if entry.predecessor and entry.predecessor not in identities:
                raise ValueError("unresolved-predecessor")
            identities.add(entry.identity)
            previous_tick = entry.tick
        if self.entries and (self.revision != len(self.entries) or self.tick != previous_tick):
            raise ValueError("ledger-head-mismatch")
        if not self.entries and (self.revision != 0 or self.tick != 0):
            raise ValueError("nonempty-head-without-records")


@dataclass(frozen=True, slots=True)
class CanonDecision:
    identity: str
    accepted: bool
    reason: str
    previous_revision: int
    new_revision: int
    retained_records: int


def _parse(raw: dict[str, Any]) -> tuple[str, str, str, str, str, str, str, int, int]:
    if type(raw) is not dict or set(raw) != {
        "id", "entity", "action", "value", "predecessor",
        "evidence", "world", "tick", "expected_revision"
    }:
        raise ValueError("invalid-command-shape")
    identity, entity, action, value, parent, proof, world, tick, revision = (
        raw[k] for k in (
            "id", "entity", "action", "value", "predecessor",
            "evidence", "world", "tick", "expected_revision"
        )
    )
    for key, text in (("id", identity), ("entity", entity), ("value", value),
                      ("evidence", proof), ("world", world)):
        if type(text) is not str or not 1 <= len(text) <= 128:
            raise ValueError("invalid-" + key)
    if type(parent) is not str or len(parent) > 128:
        raise ValueError("invalid-predecessor")
    if type(action) is not str or action not in ACTIONS:
        raise ValueError("invalid-action")
    if type(tick) is not int or not 0 <= tick <= MAX_TICK:
        raise ValueError("invalid-tick")
    if type(revision) is not int or revision < 0:
        raise ValueError("invalid-revision")
    return identity, entity, action, value, parent, proof, world, tick, revision


def append(ledger: CanonLedger, command: dict[str, Any]) -> tuple[CanonLedger, CanonDecision]:
    if type(ledger) is not CanonLedger:
        raise TypeError("invalid-ledger")
    identity, entity, action, value, parent, proof, world, tick, expected = _parse(command)

    def reject(reason: str) -> tuple[CanonLedger, CanonDecision]:
        return ledger, CanonDecision(
            identity, False, reason, ledger.revision,
            ledger.revision, len(ledger.entries)
        )

    if any(e.identity == identity for e in ledger.entries):
        return reject("duplicate-event")
    if world != ledger.world:
        return reject("cross-world-canon")
    if expected != ledger.revision:
        return reject("stale-revision")
    if tick <= ledger.tick:
        return reject("nonmonotonic-tick")
    if tick - ledger.tick > MAX_GAP and ledger.revision:
        return reject("unjustified-clock-gap")
    if len(ledger.entries) >= MAX_RECORDS:
        return reject("record-capacity")
    if not proof:
        return reject("evidence-required")
    prior = {r.identity: r for r in ledger.entries}
    if parent and parent not in prior:
        return reject("missing-predecessor")
    if parent == identity:
        return reject("self-dependency")
    if action == "establish" and parent:
        return reject("establishment-has-predecessor")
    if action != "establish" and not parent:
        return reject("amendment-missing-predecessor")
    if parent and prior[parent].entity != entity:
        return reject("entity-lineage-mismatch")
    if action == "establish" and any(r.entity == entity for r in ledger.entries):
        return reject("entity-already-established")
    if action != "establish" and not any(r.entity == entity for r in ledger.entries):
        return reject("entity-not-established")
    record = CanonRecord(
        identity, entity, action, value, parent, proof,
        world, tick, ledger.revision + 1
    )
    updated = CanonLedger(
        ledger.world, ledger.revision + 1, tick, ledger.entries + (record,)
    )
    return updated, CanonDecision(
        identity, True, "accepted", ledger.revision,
        updated.revision, len(updated.entries)
    )


def timeline(ledger: CanonLedger, entity: str) -> tuple[CanonRecord, ...]:
    if type(ledger) is not CanonLedger:
        raise TypeError("invalid-ledger")
    if type(entity) is not str or not 1 <= len(entity) <= 128:
        raise ValueError("invalid-entity")
    return tuple(record for record in ledger.entries if record.entity == entity)


def snapshot(ledger: CanonLedger) -> dict[str, Any]:
    if type(ledger) is not CanonLedger:
        raise TypeError("invalid-ledger")
    return {
        "schema": "skeleton.canon_custody.v1",
        "policy": POLICY, "domain": DOMAIN, "topic": TOPIC,
        "evidence_kind": EVIDENCE_KIND, "world": ledger.world,
        "revision": ledger.revision, "tick": ledger.tick,
        "record_count": len(ledger.entries), "record_capacity": MAX_RECORDS,
        "latest_id": ledger.entries[-1].identity if ledger.entries else None
    }


def replay(commands: list[dict[str, Any]], initial: CanonLedger | None = None):
    if type(commands) is not list or len(commands) > MAX_RECORDS:
        raise ValueError("invalid-batch")
    ledger = CanonLedger() if initial is None else initial
    decisions: list[CanonDecision] = []
    for command in commands:
        ledger, decision = append(ledger, command)
        decisions.append(decision)
    return ledger, tuple(decisions)
