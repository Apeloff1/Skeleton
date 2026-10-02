"""Bind the spine worker without replacing the runtime dispatcher."""

from __future__ import annotations

from typing import Any

from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.spine_worker import SpineWorker


class SpineBindError(RuntimeError):
    """Bind rejected its inputs. Not a maturity signal."""


class SpineBind:
    """Start the composed worker. Does not call runtime.start_dispatcher."""

    def __init__(self, runtime: DurableOperationRuntime, worker: SpineWorker) -> None:
        if not isinstance(runtime, DurableOperationRuntime):
            raise SpineBindError("runtime must be a DurableOperationRuntime")
        if not isinstance(worker, SpineWorker):
            raise SpineBindError("worker must be a SpineWorker")
        self.runtime = runtime
        self.worker = worker
        self.bound = False

    def bind(self) -> dict[str, Any]:
        started = self.worker.start()
        self.bound = True
        return {
            "kind": "spine_bind",
            "hit": started or self.worker.cycles >= 0,
            "law": "worker-not-runtime-dispatcher",
            "citation": "VOL-134",
            "started": started,
            "runtime_replaced": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def release(self) -> dict[str, Any]:
        card = self.worker.stop()
        card["runtime_replaced"] = False
        return card
