from __future__ import annotations

import pytest

from skeleton.cortex.adversarial import AdversarialContext
from skeleton.cortex.tri_adversarial import TriAdversarialEngine, TriLane


def test_judge_cannot_mutate_candidate_outside_bounded_repair_path() -> None:
    candidate = {"nested": {"value": "original"}}

    def judge(ctx, batch):
        if (
            ctx.metadata["tri_lane"] == TriLane.QUALITY.value
            and batch[0].gate_id == 1
        ):
            ctx.candidate["nested"]["value"] = "mutated-by-judge"
        return {}

    engine = TriAdversarialEngine(judge=judge)

    with pytest.raises(RuntimeError, match="mutated candidate outside repairer"):
        engine.evaluate(
            AdversarialContext(
                request="Create a deterministic artifact",
                candidate=candidate,
            )
        )

    assert candidate == {"nested": {"value": "original"}}
