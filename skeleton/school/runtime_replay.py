"""Deterministic runtime snapshots and semantic audit for Jeeves sessions."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence

from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger
from skeleton.school.session_runtime import SessionEvent, SessionPhase


@dataclass(frozen=True)
class RuntimeReplaySnapshot:
    session_id: str
    phase: str
    event_count: int
    events: tuple[tuple[int, str, str, tuple[tuple[str, str], ...]], ...]
    selected_policy: str
    rejected_policies: tuple[str, ...]
    ledger_head: str
    ledger_count: int
    runtime_digest: str

    @classmethod
    def capture(
        cls,
        *,
        session_id: str,
        phase: SessionPhase,
        events: Sequence[SessionEvent],
        selected_policy: str | None,
        rejected_policies: Sequence[str],
        ledger: DecisionLedger,
    ) -> "RuntimeReplaySnapshot":
        normalized = tuple((e.sequence, e.phase.value, e.event, tuple(e.payload)) for e in events)
        payload = {
            "session_id": session_id,
            "phase": phase.value,
            "events": normalized,
            "selected_policy": selected_policy or "",
            "rejected_policies": tuple(rejected_policies),
            "ledger_head": ledger.head_hash,
            "ledger_count": len(ledger.records),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        return cls(
            session_id,
            phase.value,
            len(normalized),
            normalized,
            selected_policy or "",
            tuple(rejected_policies),
            ledger.head_hash,
            len(ledger.records),
            digest,
        )


@dataclass(frozen=True)
class RuntimeAudit:
    valid: bool
    violations: tuple[str, ...]


def audit_runtime(snapshot: RuntimeReplaySnapshot, ledger: DecisionLedger) -> RuntimeAudit:
    violations: list[str] = []
    try:
        ledger.verify()
    except ValueError as exc:
        violations.append(f"ledger integrity: {exc}")
    if snapshot.ledger_head != ledger.head_hash:
        violations.append("runtime snapshot ledger head diverges from ledger")
    if snapshot.ledger_count != len(ledger.records):
        violations.append("runtime snapshot ledger count diverges from ledger")

    session_records = ledger.session(snapshot.session_id)
    by_id = {record.decision_id: record for record in ledger.records}
    actions = {record.action for record in session_records}
    rejected_records = {
        record.action
        for record in session_records
        if record.disposition is DecisionDisposition.REJECTED
    }
    accepted_records = {
        record.action
        for record in session_records
        if record.disposition is DecisionDisposition.ACCEPTED
    }

    if snapshot.event_count and not session_records:
        violations.append("runtime has events but ledger has no session decisions")
    if snapshot.selected_policy:
        if not session_records:
            violations.append("selected policy cannot be audited without session decisions")
        elif snapshot.selected_policy not in actions:
            violations.append("selected policy is absent from session ledger")
        elif snapshot.selected_policy in rejected_records:
            violations.append("selected policy is incorrectly recorded as rejected")
        elif snapshot.selected_policy not in accepted_records:
            violations.append("selected policy lacks an ACCEPTED ledger attribution")

    missing_rejections = set(snapshot.rejected_policies) - rejected_records
    for policy in sorted(missing_rejections):
        violations.append(f"rejected policy {policy!r} lacks a REJECTED ledger record")
    unlisted_rejections = rejected_records - set(snapshot.rejected_policies)
    for policy in sorted(unlisted_rejections):
        violations.append(f"ledger rejected policy {policy!r} is absent from runtime snapshot")

    event_sequences = [event[0] for event in snapshot.events]
    if event_sequences != list(range(1, snapshot.event_count + 1)):
        violations.append("runtime event sequence is not contiguous")
    if len(snapshot.events) != snapshot.event_count:
        violations.append("runtime event count does not match event payload")
    complete_events = [index for index, event in enumerate(snapshot.events) if event[1] == SessionPhase.COMPLETE.value]
    if complete_events:
        complete_index = complete_events[0]
        if complete_index != len(snapshot.events) - 1:
            violations.append("runtime contains events after COMPLETE")
        if snapshot.phase != SessionPhase.COMPLETE.value:
            violations.append("runtime snapshot phase diverges from terminal COMPLETE event")
    elif snapshot.phase == SessionPhase.COMPLETE.value:
        violations.append("runtime snapshot claims COMPLETE without a terminal COMPLETE event")

    for record in session_records:
        for predecessor in record.predecessors:
            prior = by_id.get(predecessor)
            if prior is None:
                violations.append(f"decision {record.decision_id!r} references missing predecessor")
            elif prior.sequence >= record.sequence:
                violations.append(f"decision {record.decision_id!r} has a non-causal predecessor")

    return RuntimeAudit(not violations, tuple(dict.fromkeys(violations)))


def replay_digest(snapshot: RuntimeReplaySnapshot) -> str:
    payload = {
        "session_id": snapshot.session_id,
        "phase": snapshot.phase,
        "events": snapshot.events,
        "selected_policy": snapshot.selected_policy,
        "rejected_policies": snapshot.rejected_policies,
        "ledger_head": snapshot.ledger_head,
        "ledger_count": snapshot.ledger_count,
        "runtime_digest": snapshot.runtime_digest,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
