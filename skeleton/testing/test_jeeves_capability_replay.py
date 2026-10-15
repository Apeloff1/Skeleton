"""Measured game/AI/coding rehearsal scheduling; no generated teaching data."""
from __future__ import annotations

import math
import pytest

from skeleton.ai.training.jeeves_capability_replay import (
    CapabilityReplayError, schedule_capability_replay,
)


class EvidenceOnlyModel:
    def __init__(self):
        self.reads = []

    def logprob(self, prompt):
        self.reads.append(prompt)
        # Deterministic synthetic scorer for the pure scheduling contract.
        # Production trainer calls actual parent-derived model.logprob.
        return -float(1 + (len(prompt) % 19) / 100.0)


def _records():
    return tuple(
        "Jeeves module jeeves."
        + domain + "." + topic + "." + lens
        + ". Objective: " + ("Test original difficult production engineering contexts. " * 2)
        + "Lens: adversarial validation. Constraints: game world code correctness. "
        + "User: Construct distinct original scenario " + str(i)
        + " Jeeves: Provide traceable proof, bounded execution, and reversible design "
        + ("variant" * (i + 1))
        for domain in ("gaming", "ai", "coding")
        for i, (topic, lens) in enumerate((
            ("world", "construct"), ("world", "repair"),
            ("evaluation", "counterexample"), ("testing", "verification"),
            ("inference", "resource"), ("security", "edge_cases"),
            ("cutscene_timing", "construct"), ("saves", "repair"),
        ))
    )


def test_hard_and_retention_samples_cover_all_capabilities():
    model = EvidenceOnlyModel()
    selected, report = schedule_capability_replay(
        model, _records(), max_examples=12, max_scored_examples=24)
    assert len(model.reads) == 24
    assert len(selected) == 12
    assert report["selected_examples"] == 12
    assert report["excluded_examples"] == 12
    assert set(report["selected_domains"]) == {"gaming", "ai", "coding"}
    assert all(n >= 2 for n in report["selected_domains"].values())
    assert report["heldout_read_by_scheduler"] is False
    assert report["weights_modified_by_scheduler"] is False
    assert report["mean_selected_training_loss"] > 0


def test_deterministic_training_selection_and_no_hidden_repetitions():
    a, receipt_a = schedule_capability_replay(
        EvidenceOnlyModel(), _records(), max_examples=15, max_scored_examples=24)
    b, receipt_b = schedule_capability_replay(
        EvidenceOnlyModel(), _records(), max_examples=15, max_scored_examples=24)
    assert a == b
    assert receipt_a == receipt_b
    assert len(set(a)) == len(a)
    assert len(receipt_a["selected_example_sha256"]) == len(a)


def test_bounded_approval_and_source_failures_are_rejected():
    with pytest.raises(CapabilityReplayError, match="budget|limits"):
        schedule_capability_replay(EvidenceOnlyModel(), _records(),
                                   max_examples=100, max_scored_examples=24)
    with pytest.raises(CapabilityReplayError, match="scoring admission"):
        schedule_capability_replay(EvidenceOnlyModel(), _records(),
                                   max_examples=6, max_scored_examples=8)
    with pytest.raises(CapabilityReplayError, match="duplicate"):
        schedule_capability_replay(EvidenceOnlyModel(), _records()[:8]*3,
                                   max_examples=6, max_scored_examples=24)
    with pytest.raises(CapabilityReplayError, match="specialist"):
        schedule_capability_replay(EvidenceOnlyModel(), ("unreviewed arbitrary text",)*6)


def test_nonfinite_model_loss_refuses_rehearsal():
    class FakeNaN:
        def logprob(self, _):
            return float("nan")
    with pytest.raises(CapabilityReplayError, match="nonfinite"):
        schedule_capability_replay(FakeNaN(), _records(), max_examples=12,
                                   max_scored_examples=24)
