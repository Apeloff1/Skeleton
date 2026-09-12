"""Deterministic reconstruction utilities for Jeeves session decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from skeleton.school.decision_ledger import DecisionLedger, DecisionRecord


@dataclass(frozen=True)
class ReplayMismatch:
    decision_id: str
    field: str
    expected: str
    observed: str


@dataclass(frozen=True)
class ReplayReport:
    session_id: str
    records: tuple[DecisionRecord, ...]
    mismatches: tuple[ReplayMismatch, ...]
    valid: bool


class JeevesReplay:
    """Compare an observed ledger against an independently reconstructed ledger."""

    def __init__(self, ledger: DecisionLedger) -> None:
        ledger.verify()
        self.ledger = ledger

    def session(self, session_id: str) -> tuple[DecisionRecord, ...]:
        return self.ledger.session(session_id)

    def compare_actions(self, session_id: str, expected: Mapping[str, str]) -> ReplayReport:
        records = self.session(session_id)
        mismatches: list[ReplayMismatch] = []
        observed_ids = {record.decision_id for record in records}
        for decision_id, expected_action in expected.items():
            if decision_id not in observed_ids:
                mismatches.append(ReplayMismatch(decision_id, "presence", "present", "missing"))
                continue
            actual = next(record for record in records if record.decision_id == decision_id)
            if actual.action != expected_action:
                mismatches.append(ReplayMismatch(decision_id, "action", expected_action, actual.action))
        return ReplayReport(session_id, records, tuple(mismatches), not mismatches)

    def causal_path(self, decision_id: str) -> tuple[DecisionRecord, ...]:
        return self.ledger.explain(decision_id)


def replay_digest(records: Sequence[DecisionRecord]) -> str:
    """Produce a stable digest over a replay slice without mutating the ledger."""
    if not records:
        return ""
    return records[-1].record_hash
