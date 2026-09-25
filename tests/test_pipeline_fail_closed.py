"""A failed or cyclic pipeline must not run the stages behind it."""

import pytest

from skeleton.intelligence.pipeline_orchestrator import (
    PipelineError,
    PipelineOrchestrator,
    PipelineStage,
)


def test_a_failed_dependency_blocks_the_rest() -> None:
    orch = PipelineOrchestrator("build")
    orch.add_stage(PipelineStage("fail", lambda _value: (_ for _ in ()).throw(ValueError("boom"))))
    orch.add_stage(PipelineStage("next", lambda _inputs: (_ for _ in ()).throw(AssertionError("ran")), dependencies=["fail"]))
    card = orch.execute(1)
    assert card["failed"] == 1
    assert card["blocked"] == ["next"]
    assert "next" not in card["stages"]
    assert card["stages"]["fail"]["error"] == "ValueError"
    assert "boom" not in str(card)


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def flaky(value: int) -> int:
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("temporary")
        return value + 1

    orch = PipelineOrchestrator("build")
    orch.add_stage(PipelineStage("work", flaky, retries=1))
    card = orch.execute(5)
    assert card["successful"] == 1
    assert card["stages"]["work"]["output"] == 6
    assert card["stages"]["work"]["attempts"] == 2


def test_cycles_and_unknown_dependencies_do_not_run() -> None:
    cycle = PipelineOrchestrator("cycle")
    cycle.add_stage(PipelineStage("a", lambda value: value, dependencies=["b"]))
    cycle.add_stage(PipelineStage("b", lambda value: value, dependencies=["a"]))
    with pytest.raises(PipelineError, match="cycle"):
        cycle.execute(1)

    missing = PipelineOrchestrator("missing")
    missing.add_stage(PipelineStage("a", lambda value: value, dependencies=["nope"]))
    with pytest.raises(PipelineError, match="unknown dependency"):
        missing.execute(1)

    duplicate = PipelineOrchestrator("dup")
    duplicate.add_stage(PipelineStage("a", lambda value: value))
    with pytest.raises(PipelineError):
        duplicate.add_stage(PipelineStage("a", lambda value: value))
