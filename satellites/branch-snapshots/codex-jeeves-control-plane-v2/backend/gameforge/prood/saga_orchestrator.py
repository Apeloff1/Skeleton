"""
PROOD SagaOrchestrator — distributed-transaction pattern with REAL compensation.

Upgrade over the shipped stub (which just ran steps forward with no recovery):
each step has an `action` and an optional `compensate`. On any step failure the
orchestrator runs the compensations of all previously-completed steps in
REVERSE order, producing a full forward + rollback trace. This is what the
PROOD doc's "Saga Pattern with full compensation and recovery" requires.
"""
from __future__ import annotations

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


@dataclass
class SagaResult:
    saga: str
    status: str                       # "completed" | "compensated" | "failed"
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
    if hasattr(res, "__await__"):
        return await res
    return res


class SagaOrchestrator:
    def __init__(self):
        self.sagas: Dict[str, List[SagaStep]] = {}

    def register_saga(self, name: str, steps: List[SagaStep]) -> None:
        self.sagas[name] = steps

    async def execute_saga(self, saga_name: str, context: Optional[Dict[str, Any]] = None) -> SagaResult:
        steps = self.sagas.get(saga_name, [])
        ctx: Dict[str, Any] = dict(context or {})
        result = SagaResult(saga=saga_name, status="completed", context=ctx)
        completed: List[SagaStep] = []

        for step in steps:
            t0 = time.time()
            try:
                out = await _maybe_await(step.action, ctx)
                if isinstance(out, dict):
                    ctx.update(out)
                completed.append(step)
                result.forward_trace.append({
                    "step": step.name, "status": "ok",
                    "ms": round((time.time() - t0) * 1000, 1),
                })
            except Exception as e:  # noqa: BLE001
                result.status = "failed"
                result.error = f"{step.name}: {type(e).__name__}: {e}"
                result.forward_trace.append({
                    "step": step.name, "status": "failed",
                    "error": str(e), "ms": round((time.time() - t0) * 1000, 1),
                })
                # ── compensate completed steps in reverse ──
                for done in reversed(completed):
                    c0 = time.time()
                    if not done.compensate:
                        result.compensation_trace.append({"step": done.name, "status": "no_compensation"})
                        continue
                    try:
                        cout = await _maybe_await(done.compensate, ctx)
                        if isinstance(cout, dict):
                            ctx.update(cout)
                        result.compensation_trace.append({
                            "step": done.name, "status": "compensated",
                            "ms": round((time.time() - c0) * 1000, 1),
                        })
                    except Exception as ce:  # noqa: BLE001
                        result.compensation_trace.append({
                            "step": done.name, "status": "compensation_failed",
                            "error": str(ce),
                        })
                result.status = "compensated"
                result.context = ctx
                return result

        result.context = ctx
        return result


# Global orchestrator
saga_orchestrator = SagaOrchestrator()
