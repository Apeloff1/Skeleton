import pytest

from skeleton.cortex.adversarial import (
    AdversarialContext,
    AdversarialEngine,
    GateStatus,
)


def test_judge_mutation_with_repair_is_rejected_without_leaking_state() -> None:
    candidate = {"items": [{"value": 1}]}
    repair_inputs = []

    def judge(ctx, batch):
        if any(spec.gate_id == 35 for spec in batch):
            ctx.candidate["items"][0]["value"] = 999
            return {35: {"status": GateStatus.REPAIR, "reason": "counterexample"}}
        return {}

    def repairer(ctx, repairs):
        repair_inputs.append(ctx.candidate)
        return ctx.candidate

    engine = AdversarialEngine(judge=judge, repairer=repairer)

    with pytest.raises(RuntimeError, match="judge mutated review context"):
        engine.evaluate(AdversarialContext(request="build", candidate=candidate))

    assert candidate == {"items": [{"value": 1}]}
    assert repair_inputs == []


def test_judge_context_isolation_failure_is_fail_closed() -> None:
    class RefusesDeepcopy:
        def __deepcopy__(self, memo):
            raise ValueError("sensitive implementation detail")

    engine = AdversarialEngine(judge=lambda ctx, batch: {})

    with pytest.raises(RuntimeError, match="judge review context isolation failed") as exc_info:
        engine.evaluate(
            AdversarialContext(request="build", candidate=RefusesDeepcopy())
        )

    assert "sensitive implementation detail" not in str(exc_info.value)
