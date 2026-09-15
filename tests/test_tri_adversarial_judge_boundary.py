from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.cortex.adversarial import AdversarialContext
from skeleton.cortex.tri_adversarial import TriAdversarialEngine, TriLane


def test_judge_mutation_with_repair_never_reaches_repairer() -> None:
    candidate = {"nested": {"value": "original"}}
    evidence = ({"nested": {"value": "trusted"}},)
    repair_inputs = []

    def judge(ctx, batch):
        if (
            ctx.metadata["tri_lane"] == TriLane.QUALITY.value
            and batch[0].gate_id == 1
        ):
            ctx.candidate["nested"]["value"] = "mutated-by-judge"
            ctx.evidence[0]["nested"]["value"] = "mutated-evidence"
            return {2: {"status": "repair", "reason": "force bounded repair"}}
        return {}

    def repairer(ctx, repairs):
        repair_inputs.append(deepcopy(ctx.candidate))
        return ctx.candidate

    engine = TriAdversarialEngine(judge=judge, repairer=repairer)

    with pytest.raises(RuntimeError, match="judge mutated review context"):
        engine.evaluate(
            AdversarialContext(
                request="Create a deterministic artifact",
                candidate=candidate,
                evidence=evidence,
            )
        )

    assert repair_inputs == []
    assert candidate == {"nested": {"value": "original"}}
    assert evidence == ({"nested": {"value": "trusted"}},)
