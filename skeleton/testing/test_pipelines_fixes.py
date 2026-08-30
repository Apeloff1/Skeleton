"""Regression tests for the pipelines plane fixes (2026-08-30).

Found by reading, not by running:

- ``ResilientRunner`` constructed ``CircuitBreaker(policy=...)`` — a kwarg
  the kernel breaker never accepted — and never engaged the breaker in
  ``run()`` anyway. The wrapper now builds a correct breaker and routes
  every run through it.
- ``PipelineComposer`` recorded a ``TypeError`` when a stage returned a
  non-dict, hiding the real shape error; non-dict outputs are now
  rejected with a clear StageError before the context merge.
"""

from __future__ import annotations

import pytest

from skeleton.kernel.breaker import CircuitOpenError, CircuitState
from skeleton.kernel.errors import StageError
from skeleton.pipelines.composer import PipelineComposer, Stage
from skeleton.pipelines.core import PipelineRunner
from skeleton.pipelines.core import Stage as CoreStage
from skeleton.pipelines.resilience import ResilientRunner


# ── ResilientRunner ──────────────────────────────────────────────────────

def test_resilient_runner_constructs_and_runs():
    runner = PipelineRunner()
    runner.register(CoreStage(name="a", run=lambda ctx: 1))
    rr = ResilientRunner(runner, name="t", failure_threshold=2)
    results = rr.run()
    assert results[0].output == 1
    assert rr.breaker_state() is CircuitState.CLOSED
    assert rr.report()["breaker"] == "t"


def test_resilient_runner_trips_on_failures_then_fails_fast():
    runner = PipelineRunner()
    runner.register(CoreStage(name="a", run=lambda ctx: 1 / 0))
    rr = ResilientRunner(runner, name="t", failure_threshold=2)
    rr.run()
    rr.run()
    assert rr.breaker_state() is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        rr.run()


def test_resilient_runner_reset_recovers():
    runner = PipelineRunner()
    runner.register(CoreStage(name="a", run=lambda ctx: 1 / 0))
    rr = ResilientRunner(runner, name="t", failure_threshold=1)
    rr.run()
    assert rr.breaker_state() is CircuitState.OPEN
    rr.reset_breaker()
    assert rr.breaker_state() is CircuitState.CLOSED


# ── PipelineComposer non-dict guard ──────────────────────────────────────

def test_composer_rejects_non_dict_stage_output():
    composer = PipelineComposer()
    run = composer.execute("p", [Stage(name="bad", run=lambda ctx: [1, 2])])
    record = run.records[0]
    assert record.error is not None
    assert "StageError" in record.error
    assert "must return a dict" in record.error


def test_composer_happy_path_still_works():
    composer = PipelineComposer()
    run = composer.execute("p", [
        Stage(name="a", run=lambda ctx: {"x": 1}),
        Stage(name="b", run=lambda ctx: {"y": ctx["x"] + 1}),
    ])
    assert run.succeeded
    assert run.context == {"x": 1, "y": 2}
