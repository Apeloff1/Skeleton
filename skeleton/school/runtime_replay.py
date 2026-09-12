"""Deterministic runtime snapshots and semantic audit for Jeeves sessions."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence

from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger
from skeleton.school.session_runtime import SessionEvent, SessionPhase


def _runtime_payload(
    *,
    session_id: str,
    phase: str,
    events: tuple[tuple[int, str, str, tuple[tuple[str, str], ...]], ...],
    selected_policy: str,
    selected_policy_decision_id: str,
    rejected_policies: tuple[str, ...],
    rejected_policy_decision_ids: tuple[str, ...],
    ledger_head: str,
    ledger_count: int,
    pipeline_contract_digest: str,
    provenance_digest: str,
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "phase": phase,
        "events": events,
        "selected_policy": selected_policy,
        "selected_policy_decision_id": selected_policy_decision_id,
        "rejected_policies": rejected_policies,
        "rejected_policy_decision_ids": rejected_policy_decision_ids,
        "ledger_head": ledger_head,
        "ledger_count": ledger_count,
        "pipeline_contract_digest": pipeline_contract_digest,
        "provenance_digest": provenance_digest,
    }


def _runtime_digest(
    *,
    session_id: str,
    phase: str,
    events: tuple[tuple[int, str, str, tuple[tuple[str, str], ...]], ...],
    selected_policy: str,
    selected_policy_decision_id: str,
    rejected_policies: tuple[str, ...],
    rejected_policy_decision_ids: tuple[str, ...],
    ledger_head: str,
    ledger_count: int,
    pipeline_contract_digest: str,
    provenance_digest: str,
) -> str:
    payload = _runtime_payload(
        session_id=session_id,
        phase=phase,
        events=events,
        selected_policy=selected_policy,
        selected_policy_decision_id=selected_policy_decision_id,
        rejected_policies=rejected_policies,
        rejected_policy_decision_ids=rejected_policy_decision_ids,
        ledger_head=ledger_head,
        ledger_count=ledger_count,
        pipeline_contract_digest=pipeline_contract_digest,
        provenance_digest=provenance_digest,
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class RuntimeReplaySnapshot:
    session_id: str
    phase: str
    event_count: int
    events: tuple[tuple[int, str, str, tuple[tuple[str, str], ...]], ...]
    selected_policy: str
    selected_policy_decision_id: str
    rejected_policies: tuple[str, ...]
    rejected_policy_decision_ids: tuple[str, ...]
    ledger_head: str
    ledger_count: int
    pipeline_contract_digest: str
    provenance_digest: str
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
        pipeline_contract_digest: str = "",
        provenance_digest: str = "",
    ) -> "RuntimeReplaySnapshot":
        normalized = tuple((e.sequence, e.phase.value, e.event, tuple(e.payload)) for e in events)
        selected = selected_policy or ""
        rejected = tuple(rejected_policies)
        session_records = ledger.session(session_id)
        selected_records = tuple(
            record for record in session_records
            if selected and record.action == selected and record.disposition is DecisionDisposition.ACCEPTED
        )
        selected_id = selected_records[0].decision_id if len(selected_records) == 1 else ""
        rejected_records = tuple(
            record for record in session_records
            if record.action in rejected and record.disposition is DecisionDisposition.REJECTED
        )
        rejected_ids = tuple(record.decision_id for record in rejected_records)
        digest = _runtime_digest(
            session_id=session_id,
            phase=phase.value,
            events=normalized,
            selected_policy=selected,
            selected_policy_decision_id=selected_id,
            rejected_policies=rejected,
            rejected_policy_decision_ids=rejected_ids,
            ledger_head=ledger.head_hash,
            ledger_count=len(ledger.records),
            pipeline_contract_digest=pipeline_contract_digest,
            provenance_digest=provenance_digest,
        )
        return cls(
            session_id,
            phase.value,
            len(normalized),
            normalized,
            selected,
            selected_id,
            rejected,
            rejected_ids,
            ledger.head_hash,
            len(ledger.records),
            pipeline_contract_digest,
            provenance_digest,
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

    expected_runtime_digest = _runtime_digest(
        session_id=snapshot.session_id,
        phase=snapshot.phase,
        events=snapshot.events,
        selected_policy=snapshot.selected_policy,
        selected_policy_decision_id=snapshot.selected_policy_decision_id,
        rejected_policies=snapshot.rejected_policies,
        rejected_policy_decision_ids=snapshot.rejected_policy_decision_ids,
        ledger_head=snapshot.ledger_head,
        ledger_count=snapshot.ledger_count,
        pipeline_contract_digest=snapshot.pipeline_contract_digest,
        provenance_digest=snapshot.provenance_digest,
    )
    if snapshot.runtime_digest != expected_runtime_digest:
        violations.append("runtime-integrity divergence: runtime digest does not match snapshot payload")

    session_records = ledger.session(snapshot.session_id)
    by_id = {record.decision_id: record for record in ledger.records}
    actions = {record.action for record in session_records}
    rejected_records = tuple(record for record in session_records if record.disposition is DecisionDisposition.REJECTED)
    accepted_records = tuple(record for record in session_records if record.disposition is DecisionDisposition.ACCEPTED)

    if snapshot.event_count and not session_records:
        violations.append("runtime has events but ledger has no session decisions")
    if snapshot.selected_policy:
        selected_matches = tuple(
            record for record in accepted_records if record.action == snapshot.selected_policy
        )
        if not session_records:
            violations.append("selected policy cannot be audited without session decisions")
        elif snapshot.selected_policy not in actions:
            violations.append("selected policy is absent from session ledger")
        elif any(record.action == snapshot.selected_policy for record in rejected_records):
            violations.append("selected policy is incorrectly recorded as rejected")
        elif len(selected_matches) != 1:
            violations.append("selected policy does not have a unique ACCEPTED ledger attribution")
        if not snapshot.selected_policy_decision_id:
            violations.append("selected policy is missing a decision identity")
        else:
            selected_record = by_id.get(snapshot.selected_policy_decision_id)
            if selected_record is None:
                violations.append("selected policy decision identity is absent from ledger")
            elif selected_record.session_id != snapshot.session_id:
                violations.append("selected policy decision identity crosses session boundary")
            elif selected_record.action != snapshot.selected_policy:
                violations.append("selected policy decision identity does not match selected action")
            elif selected_record.disposition is not DecisionDisposition.ACCEPTED:
                violations.append("selected policy decision identity is not ACCEPTED")

    expected_rejected_ids = tuple(record.decision_id for record in rejected_records if record.action in snapshot.rejected_policies)
    if set(snapshot.rejected_policy_decision_ids) != set(expected_rejected_ids):
        violations.append("rejected policy decision identities diverge from ledger")
    if len(snapshot.rejected_policy_decision_ids) != len(set(snapshot.rejected_policy_decision_ids)):
        violations.append("rejected policy decision identities are not unique")
    for decision_id in snapshot.rejected_policy_decision_ids:
        record = by_id.get(decision_id)
        if record is None:
            violations.append(f"rejected policy decision {decision_id!r} is absent from ledger")
        elif record.session_id != snapshot.session_id:
            violations.append(f"rejected policy decision {decision_id!r} crosses session boundary")
        elif record.disposition is not DecisionDisposition.REJECTED:
            violations.append(f"rejected policy decision {decision_id!r} is not REJECTED")
        elif record.action not in snapshot.rejected_policies:
            violations.append(f"rejected policy decision {decision_id!r} is not listed in rejected policies")

    for policy in sorted(set(snapshot.rejected_policies) - {record.action for record in rejected_records}):
        violations.append(f"rejected policy {policy!r} lacks a REJECTED ledger record")
    for policy in sorted({record.action for record in rejected_records} - set(snapshot.rejected_policies)):
        violations.append(f"ledger rejected policy {policy!r} is absent from runtime snapshot")

    pipeline = snapshot.pipeline_contract_digest
    provenance = snapshot.provenance_digest
    if bool(pipeline) != bool(provenance):
        violations.append("runtime provenance is incomplete: pipeline and plan digests must be paired")
    for name, value in (("pipeline contract", pipeline), ("runtime provenance", provenance)):
        if value and (len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower())):
            violations.append(f"{name} digest is not a valid SHA-256 identity")

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
        "selected_policy_decision_id": snapshot.selected_policy_decision_id,
        "rejected_policies": snapshot.rejected_policies,
        "rejected_policy_decision_ids": snapshot.rejected_policy_decision_ids,
        "ledger_head": snapshot.ledger_head,
        "ledger_count": snapshot.ledger_count,
        "pipeline_contract_digest": snapshot.pipeline_contract_digest,
        "provenance_digest": snapshot.provenance_digest,
        "runtime_digest": snapshot.runtime_digest,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
