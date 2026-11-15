"""Compensation and request-local execution for the July PROOD surface."""
import asyncio

import pytest

from gameforge.prood.saga_orchestrator import SagaOrchestrator, SagaStep


@pytest.mark.asyncio
async def test_reverse_compensation_and_partial_failure():
    calls = []
    async def action(ctx):
        return {}
    async def undo_a(ctx):
        calls.append("a")
    async def undo_b(ctx):
        calls.append("b")
        raise RuntimeError("cannot undo")
    async def fail(ctx):
        raise RuntimeError("failed")
    saga = SagaOrchestrator()
    saga.register_saga("s", [SagaStep("a", action, undo_a), SagaStep("b", action, undo_b),
                             SagaStep("fail", fail)])
    result = await saga.execute_saga("s")
    assert calls == ["b", "a"]
    assert result.status == "compensation_incomplete"
    assert [x["status"] for x in result.compensation_trace] == ["compensation_failed", "compensated"]


@pytest.mark.asyncio
async def test_unknown_saga_and_missing_required_compensator():
    saga = SagaOrchestrator()
    assert (await saga.execute_saga("missing")).status == "failed"
    def fail(ctx):
        raise RuntimeError()
    saga.register_saga("s", [SagaStep("write", lambda ctx: {}, requires_compensation=True),
                             SagaStep("fail", fail)])
    assert (await saga.execute_saga("s")).status == "compensation_incomplete"


@pytest.mark.asyncio
async def test_cancelled_saga_compensates_completed_steps():
    started = asyncio.Event()
    undone = asyncio.Event()
    async def block(ctx):
        started.set()
        await asyncio.Event().wait()
    async def undo(ctx):
        undone.set()
    saga = SagaOrchestrator()
    saga.register_saga("s", [SagaStep("write", lambda ctx: {}, undo), SagaStep("block", block)])
    task = asyncio.create_task(saga.execute_saga("s"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert undone.is_set()


def test_invalid_saga_registration():
    saga = SagaOrchestrator()
    with pytest.raises(ValueError):
        saga.register_saga("s", [])
    with pytest.raises(ValueError):
        saga.register_saga("s", [SagaStep("x", lambda ctx: {}), SagaStep("x", lambda ctx: {})])
