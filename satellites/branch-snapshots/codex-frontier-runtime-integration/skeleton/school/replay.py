"""Deterministic replay and audit comparisons for Jeeves decisions."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from typing import Sequence
from skeleton.school.decision_ledger import DecisionDisposition, DecisionRecord


@dataclass(frozen=True)
class ReplayMismatch:
    sequence: int
    expected: str
    actual: str
    reason: str


@dataclass(frozen=True)
class ReplayReport:
    session_id: str
    matches: int
    mismatches: tuple[ReplayMismatch, ...]

    @property
    def identical(self) -> bool:
        return not self.mismatches


@dataclass(frozen=True)
class ReplaySnapshot:
    """Stable semantic projection used to compare two Jeeves executions."""

    session_id: str
    decision_ids: tuple[str, ...]
    predecessors: tuple[tuple[str, ...], ...]
    record_hashes: tuple[str, ...]
    selected_actions: tuple[str, ...]
    rejected_actions: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    policy_digests: tuple[str, ...]
    state_digests: tuple[str, ...]
    dispositions: tuple[str, ...]

    @classmethod
    def from_records(cls, records: Sequence[DecisionRecord]) -> "ReplaySnapshot":
        ordered = tuple(records)
        return cls(
            session_id=ordered[0].session_id if ordered else "",
            decision_ids=tuple(r.decision_id for r in ordered),
            predecessors=tuple(r.predecessors for r in ordered),
            record_hashes=tuple(r.record_hash for r in ordered),
            selected_actions=tuple(r.action for r in ordered if r.disposition != DecisionDisposition.REJECTED),
            rejected_actions=tuple(r.action for r in ordered if r.disposition == DecisionDisposition.REJECTED),
            evidence_ids=tuple(e for r in ordered for e in r.evidence),
            policy_digests=tuple(r.policy_digest for r in ordered),
            state_digests=tuple(r.state_digest for r in ordered),
            dispositions=tuple(r.disposition.value for r in ordered),
        )


class JeevesReplay:
    def session(self, records: Sequence[DecisionRecord], session_id: str) -> tuple[DecisionRecord, ...]:
        return tuple(r for r in records if r.session_id == session_id)

    def compare_actions(self, expected: Sequence[DecisionRecord], actual: Sequence[DecisionRecord]) -> ReplayReport:
        """Compare full causal decision semantics, not only the chosen action."""
        mismatches: list[ReplayMismatch] = []
        pairs = zip(expected, actual)
        for index, (left, right) in enumerate(pairs, 1):
            checks = (
                (left.decision_id, right.decision_id, "decision-identity divergence"),
                (left.action, right.action, "action divergence"),
                (left.evidence, right.evidence, "evidence-reference divergence"),
                (left.predecessors, right.predecessors, "causal-predecessor divergence"),
                (left.policy_digest, right.policy_digest, "policy-state divergence"),
                (left.state_digest, right.state_digest, "learner-state divergence"),
                (left.disposition.value, right.disposition.value, "disposition divergence"),
                (left.record_hash, right.record_hash, "record-integrity divergence"),
            )
            for exp, act, reason in checks:
                if exp != act:
                    mismatches.append(ReplayMismatch(index, str(exp), str(act), reason))
        if len(expected) != len(actual):
            mismatches.append(ReplayMismatch(min(len(expected), len(actual)) + 1, str(len(expected)), str(len(actual)), "record count divergence"))
        compared = min(len(expected), len(actual))
        divergent_positions = {m.sequence for m in mismatches if m.sequence <= compared}
        matches = compared - len(divergent_positions)
        session_id = expected[0].session_id if expected else (actual[0].session_id if actual else "")
        return ReplayReport(session_id, matches, tuple(mismatches))

    def compare_snapshots(self, expected: ReplaySnapshot, actual: ReplaySnapshot) -> ReplayReport:
        """Compare semantic execution projections, including causal identity."""
        mismatches: list[ReplayMismatch] = []
        if expected.session_id != actual.session_id:
            mismatches.append(ReplayMismatch(0, expected.session_id, actual.session_id, "session identity divergence"))
        checks = (
            (expected.decision_ids, actual.decision_ids, "decision-identity divergence"),
            (expected.predecessors, actual.predecessors, "causal-predecessor divergence"),
            (expected.record_hashes, actual.record_hashes, "record-integrity divergence"),
            (expected.selected_actions, actual.selected_actions, "selected-policy divergence"),
            (expected.rejected_actions, actual.rejected_actions, "rejected-policy divergence"),
            (expected.evidence_ids, actual.evidence_ids, "evidence-attribution divergence"),
            (expected.policy_digests, actual.policy_digests, "policy-provenance divergence"),
            (expected.state_digests, actual.state_digests, "state-provenance divergence"),
            (expected.dispositions, actual.dispositions, "decision-disposition divergence"),
        )
        for index, (exp, act, reason) in enumerate(checks, 1):
            if exp != act:
                mismatches.append(ReplayMismatch(index, str(exp), str(act), reason))
        compared = len(checks) + (1 if expected.session_id == actual.session_id else 0)
        return ReplayReport(expected.session_id or actual.session_id, compared - len(mismatches), tuple(mismatches))

    def causal_path(self, ledger, decision_id: str) -> tuple[DecisionRecord, ...]:
        return ledger.explain(decision_id)


def replay_digest(records: Sequence[DecisionRecord]) -> str:
    """Hash the complete deterministic replay surface, including causal metadata."""
    payload = [{"sequence": r.sequence, "decision_id": r.decision_id, "session_id": r.session_id, "action": r.action, "rationale": r.rationale, "evidence": r.evidence, "predecessors": r.predecessors, "state_digest": r.state_digest, "policy_digest": r.policy_digest, "disposition": r.disposition.value, "record_hash": r.record_hash} for r in records]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
