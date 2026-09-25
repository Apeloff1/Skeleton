"""One sample is not agreement, and no evaluations are not a rate of zero."""

import pytest

from skeleton.intelligence.entropy_gate import Decision, UncertaintyGate, semantic_entropy


def test_one_sample_abstains() -> None:
    with pytest.raises(ValueError):
        semantic_entropy(["only this"])
    gate = UncertaintyGate()
    assert gate.stats()["abstention_rate"] is None
    verdict = gate.evaluate(["only this"])
    assert verdict.decision is Decision.ABSTAIN
    assert verdict.entropy == float("inf")
    agreed = gate.evaluate(["the same answer", "the same answer"])
    assert agreed.decision is Decision.ANSWER
    assert agreed.entropy == 0.0
    with pytest.raises(ValueError):
        UncertaintyGate(cluster_threshold=True)
