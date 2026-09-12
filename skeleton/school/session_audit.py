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
        ledger.verify()
        checks.append("hash-chain")
    except ValueError as exc:
        failures.append(f"hash-chain: {exc}")

    by_id = {record.decision_id: record for record in ledger.records}
    expected_sequence = [record.sequence for record in records]
    if expected_sequence != sorted(expected_sequence) or len(set(expected_sequence)) != len(expected_sequence):
        failures.append("session decision sequence is not ordered")

    for record in records:
        for predecessor in record.predecessors:
            prior = by_id.get(predecessor)
            if prior is None:
                failures.append(f"missing predecessor for {record.decision_id}")
            elif prior.sequence >= record.sequence:
                failures.append(f"causal predecessor is not earlier: {record.decision_id}")
    checks.append("causal-ancestry" if records[0].predecessors else "causal-root")

    rejected = tuple(record for record in records if record.disposition is DecisionDisposition.REJECTED)
    if rejected:
        checks.append("counterfactual-audit")
        for record in rejected:
            if "counterfactual alternative" not in record.rationale or "not executed" not in record.rationale:
                failures.append(f"rejected alternative lacks audit rationale: {record.decision_id}")

    # Supersession is a first-class causal edge on the replacement record.
    replacements = tuple(record for record in records if record.supersedes is not None)
    if replacements:
        checks.append("supersession-audit")
    seen_targets: set[str] = set()
    for replacement in replacements:
        target_id = replacement.supersedes
        assert target_id is not None
        target = by_id.get(target_id)
        if target is None:
            failures.append(f"superseded target is missing: {replacement.decision_id}")
            continue
        if target.sequence >= replacement.sequence:
            failures.append(f"superseded target is not earlier: {replacement.decision_id}")
        if replacement.disposition is not DecisionDisposition.ACCEPTED:
            failures.append(f"superseding replacement must be accepted: {replacement.decision_id}")
        if len(replacement.predecessors) != 1 or replacement.predecessors[0] != target_id:
            failures.append(f"supersession predecessor must name target: {replacement.decision_id}")
        if target_id in seen_targets:
            failures.append(f"decision {target_id} is superseded more than once")
        seen_targets.add(target_id)

    superseded = tuple(record for record in records if record.disposition is DecisionDisposition.SUPERSEDED)
    if superseded:
        checks.append("legacy-superseded-disposition")
        for record in superseded:
            if len(record.predecessors) != 1:
                failures.append(f"legacy supersession must name exactly one predecessor: {record.decision_id}")

    superseded_ids = ledger.superseded_ids()
    active = ledger.active_records(session_id)
    expected_active = tuple(
        record
        for record in records
        if record.decision_id not in superseded_ids and record.disposition is not DecisionDisposition.SUPERSEDED
    )
    if tuple(record.decision_id for record in active) == tuple(record.decision_id for record in expected_active):
        checks.append("active-record-filter")
    else:
        failures.append("active-record filter diverges from supersession semantics")

    if any(record.policy_digest for record in records):
        checks.append("policy-provenance")
    if not failures:
        checks.append("session-audit-clean")
    return SessionAudit(session_id, not failures, tuple(checks), tuple(failures), replay_digest(records))


def policy_chain(records: Sequence[DecisionRecord]) -> tuple[str, ...]:
    return tuple(
        record.action
        for record in records
        if record.disposition is not DecisionDisposition.REJECTED and record.policy_digest
    )
