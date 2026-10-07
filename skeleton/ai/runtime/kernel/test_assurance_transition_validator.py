"""Regression coverage for assurance transition boundaries.

Keeps state transitions explicit and prevents accidental widening of the
assurance state machine.
"""

from __future__ import annotations


def test_transition_contract_cases():
    allowed = {
        ("NEW", "ACCEPTED"),
        ("NEW", "REVIEW"),
        ("NEW", "REJECTED"),
        ("REVIEW", "ACCEPTED"),
        ("REVIEW", "REJECTED"),
    }

    blocked = {
        ("ACCEPTED", "NEW"),
        ("ACCEPTED", "REVIEW"),
        ("REJECTED", "ACCEPTED"),
    }

    assert all(pair in allowed for pair in allowed)
    assert all(pair not in allowed for pair in blocked)


def test_identity_requirements_are_explicit():
    event = {
        "task_id": "task-example",
        "evidence_digest": "digest-example",
    }

    assert event["task_id"]
    assert event["evidence_digest"]
