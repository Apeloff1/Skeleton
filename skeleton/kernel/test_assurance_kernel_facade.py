"""Regression checks for the assurance kernel facade boundary."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AssuranceInput:
    task_id: str
    evidence_digest: str
    state: str


def evaluate_assurance(value: AssuranceInput) -> bool:
    return bool(value.task_id and value.evidence_digest and value.state)


def test_facade_requires_bound_identity():
    assert evaluate_assurance(
        AssuranceInput("task-1", "digest-1", "ACCEPTED")
    )


def test_facade_rejects_missing_identity():
    assert not evaluate_assurance(
        AssuranceInput("", "digest-1", "ACCEPTED")
    )


def test_facade_rejects_missing_evidence():
    assert not evaluate_assurance(
        AssuranceInput("task-1", "", "ACCEPTED")
    )
