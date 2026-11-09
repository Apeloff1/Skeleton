"""Generation-checked runtime slot for explicit P2 deployment transitions."""

from __future__ import annotations

from threading import RLock
from typing import Any

from skeleton.persistence.operation_runtime import DurableOperationRuntime


class SpineRuntimeSlotError(RuntimeError):
    """Runtime slot rejected a stale or unsafe replacement."""


class SpineRuntimeSlot:
    """Own one explicit runtime reference and generation counter."""

    def __init__(self, runtime: DurableOperationRuntime) -> None:
        if not isinstance(runtime, DurableOperationRuntime):
            raise SpineRuntimeSlotError("runtime must be a DurableOperationRuntime")
        if runtime.dispatcher_running:
            raise SpineRuntimeSlotError("initial runtime dispatcher must be stopped")
        self._runtime = runtime
        self._generation = 0
        self._lock = RLock()

    @property
    def runtime(self) -> DurableOperationRuntime:
        with self._lock:
            return self._runtime

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "kind": "spine_runtime_slot",
                "hit": True,
                "law": "runtime-slot-replacement-is-explicit-and-generation-checked",
                "citation": "VOL-134",
                "generation": self._generation,
                "runtime_type": type(self._runtime).__name__,
                "dispatcher_running": self._runtime.dispatcher_running,
                "stored_prose": 0,
                "completion_checkbox": False,
                "implementation_signature": False,
                "verification_signature": False,
            }

    def replace(
        self,
        *,
        expected: DurableOperationRuntime,
        replacement: DurableOperationRuntime,
    ) -> dict[str, Any]:
        if not isinstance(expected, DurableOperationRuntime):
            raise SpineRuntimeSlotError("expected runtime must be durable")
        if not isinstance(replacement, DurableOperationRuntime):
            raise SpineRuntimeSlotError("replacement runtime must be durable")
        if expected is replacement:
            raise SpineRuntimeSlotError("replacement must be a distinct runtime")
        with self._lock:
            if self._runtime is not expected:
                raise SpineRuntimeSlotError("runtime slot generation is stale")
            if expected.dispatcher_running:
                raise SpineRuntimeSlotError("current runtime dispatcher must be stopped")
            if replacement.dispatcher_running:
                raise SpineRuntimeSlotError("replacement runtime dispatcher must be stopped")
            before = self._generation
            self._runtime = replacement
            self._generation += 1
            return {
                "kind": "spine_runtime_slot_replace",
                "hit": True,
                "law": "runtime-slot-replacement-is-explicit-and-generation-checked",
                "citation": "VOL-134",
                "generation_before": before,
                "generation_after": self._generation,
                "runtime_replaced": True,
                "dispatcher_started": False,
                "runtime_activated": False,
                "stored_prose": 0,
                "completion_checkbox": False,
                "implementation_signature": False,
                "verification_signature": False,
            }

    def restore(
        self,
        *,
        expected_candidate: DurableOperationRuntime,
        original: DurableOperationRuntime,
    ) -> dict[str, Any]:
        if not isinstance(expected_candidate, DurableOperationRuntime):
            raise SpineRuntimeSlotError("candidate runtime must be durable")
        if not isinstance(original, DurableOperationRuntime):
            raise SpineRuntimeSlotError("original runtime must be durable")
        with self._lock:
            if self._runtime is not expected_candidate:
                raise SpineRuntimeSlotError("runtime slot is not on expected candidate")
            if expected_candidate.dispatcher_running:
                raise SpineRuntimeSlotError("candidate dispatcher must be stopped before restore")
            if original.dispatcher_running:
                raise SpineRuntimeSlotError("original dispatcher must be stopped before restore")
            before = self._generation
            self._runtime = original
            self._generation += 1
            return {
                "kind": "spine_runtime_slot_restore",
                "hit": True,
                "law": "runtime-slot-restore-is-generation-checked",
                "citation": "VOL-134",
                "generation_before": before,
                "generation_after": self._generation,
                "runtime_restored": True,
                "dispatcher_running": False,
                "runtime_activated": False,
                "stored_prose": 0,
                "completion_checkbox": False,
                "implementation_signature": False,
                "verification_signature": False,
            }
