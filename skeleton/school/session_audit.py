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
    records = tuple(r for r in ledger.records if r.session_id == session_id)
    checks: list[str] = []
    failures: list[str] = []

    if not records:
        return SessionAudit(session_id, False, (), ("session has no ledger records",), replay_digest(()))

    try:
        ledger.verify()
        checks.append("hash-chain")
    except ValueError as exc:
        failures.append(f"hash-chain: {exc}")

    expected = 1
    ids = {record.decision_id for record in records}
    for record in records:
        if record.sequence != expected:
            failures.append(f"sequence gap at {record.decision_id}: expected {expected}, got {record.sequence}")
        expected += 1
        if any(predecessor not in ids for predecessor in record.predecessors):
            failures.append(f"missing predecessor for {record.decision_id}")

    if records and records[0].predecessors:
        failures.append("session root has predecessors")
    else:
        checks.append("causal-root")

    rejected = tuple(r for r in records if r.disposition is DecisionDisposition.REJECTED)
    if rejected:
        checks.append("counterfactual-audit")
        for record in rejected:
            if "counterfactual alternative" not in record.rationale:
                failures.append(f"rejected alternative lacks rationale: {record.decision_id}")

    policy_records = tuple(r for r in records if r.policy_digest)
    if policy_records:
        checks.append("policy-provenance")

    if expected - 1 == len(records):
        checks.append("sequence-contiguous")

    digest = replay_digest(records)
    return SessionAudit(session_id, not failures, tuple(checks), tuple(failures), digest)


def policy_chain(records: Sequence[DecisionRecord]) -> tuple[str, ...]:
    """Return the executed policy lineage in deterministic ledger order."""
    return tuple(
        record.action
        for record in records
        if record.disposition is not DecisionDisposition.REJECTED
        and ("selected_policy" in record.policy_digest or "executed_policy" in record.policy_digest)
    )
