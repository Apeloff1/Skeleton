"""Deterministic audit checks for the Jeeves session control loop."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger, DecisionRecord
from skeleton.school.replay import replay_digest

@dataclass(frozen=True)
class SessionAudit:
    session_id: str
    valid: bool
    checks: tuple[str, ...]
    failures: tuple[str, ...]
    digest: str

def audit_session(ledger: DecisionLedger, session_id: str) -> SessionAudit:
    records = ledger.session(session_id)
    checks: list[str] = []
    failures: list[str] = []
    if not records:
        return SessionAudit(session_id, False, (), ("session has no ledger records",), replay_digest(()))
    try:
        ledger.verify(); checks.append("hash-chain")
    except ValueError as exc:
        failures.append(f"hash-chain: {exc}")
    all_ids = {record.decision_id for record in ledger.records}
    expected_sequence = [r.sequence for r in records]
    if expected_sequence != sorted(expected_sequence) or len(set(expected_sequence)) != len(expected_sequence):
        failures.append("session decision sequence is not ordered")
    for record in records:
        if any(predecessor not in all_ids for predecessor in record.predecessors):
            failures.append(f"missing predecessor for {record.decision_id}")
    checks.append("causal-ancestry" if records[0].predecessors else "causal-root")
    rejected = tuple(r for r in records if r.disposition is DecisionDisposition.REJECTED)
    if rejected:
        checks.append("counterfactual-audit")
        for record in rejected:
            if "counterfactual alternative" not in record.rationale or "not executed" not in record.rationale:
                failures.append(f"rejected alternative lacks audit rationale: {record.decision_id}")
    superseded = tuple(r for r in records if r.disposition is DecisionDisposition.SUPERSEDED)
    if superseded:
        checks.append("supersession-audit")
        for record in superseded:
            if len(record.predecessors) != 1:
                failures.append(f"supersession must name exactly one predecessor: {record.decision_id}")
    if any(r.policy_digest for r in records): checks.append("policy-provenance")
    if tuple(r.sequence for r in ledger.active_records(session_id)) == tuple(r.sequence for r in records if r.decision_id not in ledger.superseded_ids() and r.disposition is not DecisionDisposition.SUPERSEDED):
        checks.append("active-record-filter")
    if not failures: checks.append("session-audit-clean")
    return SessionAudit(session_id, not failures, tuple(checks), tuple(failures), replay_digest(records))

def policy_chain(records: Sequence[DecisionRecord]) -> tuple[str, ...]:
    return tuple(record.action for record in records if record.disposition is not DecisionDisposition.REJECTED and record.policy_digest)
