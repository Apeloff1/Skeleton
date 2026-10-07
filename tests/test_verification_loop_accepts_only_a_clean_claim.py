"""A high score does not accept a rewrite or a claim that still has issues."""

import pytest

from skeleton.intelligence.verification import VerificationLoop, VerificationVerdict


def test_a_revision_is_checked_again_and_issues_block_acceptance() -> None:
    seen = []

    def verifier(claim, context):
        seen.append(claim)
        if claim == "draft":
            return VerificationVerdict(0.99, (), "final answer")
        return VerificationVerdict(0.95, ())

    final, trace = VerificationLoop(max_rounds=3, accept_threshold=0.9).run("draft", verifier)
    assert seen == ["draft", "final answer"]
    assert final == "final answer"
    assert trace.stopped_reason == "accepted"
    assert trace.rounds == 2

    def flagged(claim, context):
        return VerificationVerdict(0.99, ("unsafe",))

    final, trace = VerificationLoop(max_rounds=2, accept_threshold=0.9).run("draft", flagged)
    assert trace.stopped_reason != "accepted"
    assert final == "draft"

    with pytest.raises(ValueError):
        VerificationLoop(accept_threshold=0)
    with pytest.raises(ValueError):
        VerificationLoop().run("   ", flagged)
