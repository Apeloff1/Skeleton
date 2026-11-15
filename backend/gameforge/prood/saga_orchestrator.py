"""
PROOD SagaOrchestrator — distributed-transaction pattern with REAL compensation.

Upgrade over the shipped stub (which just ran steps forward with no recovery):
each step has an `action` and an optional `compensate`. On any step failure the
orchestrator runs the compensations of all previously-completed steps in
REVERSE order, producing a full forward + rollback trace. This is what the
PROOD doc's "Saga Pattern with full compensation and recovery" requires.
"""
from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

# A step callable takes the running context dict and returns an (updated) dict.
StepFn = Callable[[Dict[str, Any]], Any]  # may be sync or async


@dataclass
class SagaStep:
    name: str
    action: StepFn
    compensate: Optional[StepFn] = None
    requires_compensation: bool = False


@dataclass
class SagaResult:
    saga: str
    status: str  # completed | compensated | compensation_incomplete | failed
    context: Dict[str, Any]
    forward_trace: List[Dict] = field(default_factory=list)
    compensation_trace: List[Dict] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "saga": self.saga, "status": self.status,
            "context": self.context, "forward_trace": self.forward_trace,
            "compensation_trace": self.compensation_trace, "error": self.error,
        }


async def _maybe_await(fn: StepFn, context: Dict[str, Any]) -> Any:
    res = fn(context)
    if inspect.isawaitable(res):
        return await res
    return res


class SagaOrchestrator:
    def __init__(self):
        self.sagas: Dict[str, List[SagaStep]] = {}

    def register_saga(self, name: str, steps: List[SagaStep]) -> None:
        if not isinstance(name, str) or not 1 <= len(name) <= 128:
            raise ValueError("invalid saga name")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 128:
            raise ValueError("invalid saga steps")
        if any(not isinstance(step, SagaStep) or not callable(step.action)
               or (step.compensate is not None and not callable(step.compensate))
               or not isinstance(step.name, str) or not 1 <= len(step.name) <= 128
               for step in steps):
            raise ValueError("invalid saga step")
        if len({step.name for step in steps}) != len(steps):
            raise ValueError("duplicate saga step name")
        self.sagas[name] = list(steps)

    async def _rollback(self, completed, result, ctx):
        incomplete = False
        for done in reversed(completed):
            c0 = time.monotonic()
            if done.compensate is None:
                incomplete |= done.requires_compensation
                result.compensation_trace.append({
                    "step": done.name,
                    "status": "missing_compensation" if done.requires_compensation else "not_required",
                })
                continue
            try:
                cout = await asyncio.wait_for(_maybe_await(done.compensate, ctx), timeout=30)
                if isinstance(cout, dict):
                    ctx.update(cout)
                result.compensation_trace.append({
                    "step": done.name, "status": "compensated",
                    "ms": round((time.monotonic() - c0) * 1000, 1),
                })
            except (Exception, asyncio.CancelledError):
                incomplete = True
                result.compensation_trace.append({
                    "step": done.name, "status": "compensation_failed",
                    "error": "compensation_failed",
                })
        result.status = "compensation_incomplete" if incomplete else "compensated"
        result.context = ctx

    async def execute_saga(self, saga_name: str, context: Optional[Dict[str, Any]] = None) -> SagaResult:
        ctx: Dict[str, Any] = dict(context or {})
        # Snapshot a registered definition. Unknown names cannot succeed as
        # empty transactions, and registration during an await cannot mutate
        # the executing sequence.
        steps = tuple(self.sagas.get(saga_name, ()))
        result = SagaResult(saga=saga_name, status="completed", context=ctx)
        if not steps:
            result.status = "failed"
            result.error = "unknown_saga"
            return result
        completed: List[SagaStep] = []
        for step in steps:
            t0 = time.monotonic()
            try:
                out = await _maybe_await(step.action, ctx)
                if isinstance(out, dict):
                    ctx.update(out)
                completed.append(step)
                result.forward_trace.append({
                    "step": step.name, "status": "ok",
                    "ms": round((time.monotonic() - t0) * 1000, 1),
                })
            except asyncio.CancelledError:
                # Keep compensation alive when the request owner cancels.
                # The currently interrupted action remains ambiguous; actions
                # with external side effects must expose idempotent recovery.
                cleanup = asyncio.create_task(self._rollback(completed, result, ctx))
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        continue
                cleanup.result()
                raise
            except Exception:
                result.error = f"{step.name}: step_failed"
                result.forward_trace.append({
                    "step": step.name, "status": "failed", "error": "step_failed",
                    "ms": round((time.monotonic() - t0) * 1000, 1),
                })
                await self._rollback(completed, result, ctx)
                return result
        return result


# Global orchestrator
saga_orchestrator = SagaOrchestrator()
