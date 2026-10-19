"""Verifier-of-verifiers cannot clear the release when its verifiers go soft."""

import pytest

from skeleton.jeeves.agent.adversarial_verifier_review import (
    AdversarialVerifierReviewer, VerifierAdversarialFailure,
)
from skeleton.jeeves.agent.types import Goal, ToolObservation
from skeleton.jeeves.agent.working_context_cycle import WorkingContextCycle


def subject(with_miss=True):
    goal = Goal("g1", "Investigate code quality and build failures")
    results = (
        ToolObservation(
            "miss1", "lookup", True,
            payload={"status": "no_results", "path": "unused/dead.py"},
        ),
        ToolObservation(
            "hit1", "lookup", True,
            payload={"status": "ok", "path": "src/engine.py", "found": True},
        ),
    ) if with_miss else (
        ToolObservation("hit1", "lookup", True,
                        payload={"status": "ok", "found": True}),
    )
    return goal, results, WorkingContextCycle().prepare(goal, results)


@pytest.mark.parametrize("with_miss", [True, False])
def test_adversarial_review_attacks_both_real_verifiers(with_miss):
    goal, observations, prepared = subject(with_miss)
    report = AdversarialVerifierReviewer().review(
        prepared, goal, observations, answer="This scoped query found no matches."
    )
    assert report.passed
    assert report.integrity_attacks >= 3
    assert report.scope_attacks >= 2
    assert all(x.rejected for x in report.attacks)
    assert len(report.digest) == 64


def test_adversarial_reviewer_rejects_permissive_integrity_verifier():
    goal, observations, prepared = subject(True)
    with pytest.raises(VerifierAdversarialFailure, match="unsafe acceptance"):
        AdversarialVerifierReviewer(
            integrity=lambda *_args: None
        ).review(prepared, goal, observations)


def test_adversarial_reviewer_rejects_permissive_scope_verifier():
    goal, observations, prepared = subject(True)
    with pytest.raises(VerifierAdversarialFailure, match="unsafe acceptance"):
        AdversarialVerifierReviewer(
            scope=lambda *_args, **_kwargs: None
        ).review(prepared, goal, observations)


def test_adversarial_reviewer_does_not_accept_unsafe_original():
    goal, observations, prepared = subject(True)
    with pytest.raises(ValueError, match="nonexistence"):
        AdversarialVerifierReviewer().review(
            prepared, goal, observations, answer="It never existed."
        )
