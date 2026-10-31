"""App-owned durable tail observation recorder, fail-closed after CAS errors."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skeleton.ai.model_runtime.execution_telemetry import ExecutionTiming
from skeleton.ai.model_runtime.tail_latency_profile import LocalTailProfiler
from skeleton.ai.model_runtime.tail_profile_custody import (
    DurableTailProfileStore, TailCustodyQuarantined,
)
from .offline_tail_profile_adapter import LocalTailObservationCapture


@dataclass(frozen=True, slots=True)
class DurableTailStatus:
    schema: str
    generation: int
    profile_digest: str
    requests: int
    quarantined: bool
    device_qualified: bool = False


class OfflineDurableTailRecorder:
    """Persist every captured sample before returning a public receipt.

    No automatic reset, profile eviction, GPU qualification or inference
    execution. The caller owns the independently anchored SQLite connection.
    """

    def __init__(
        self, store: DurableTailProfileStore, *,
        storage_path: str | Path = ".", gpu_device: str | None = None,
        bootstrap: bool = False,
    ) -> None:
        if not isinstance(store, DurableTailProfileStore):
            raise ValueError("canonical tail custody store required")
        if type(bootstrap) is not bool:
            raise ValueError("explicit bootstrap flag required")
        self._store = store
        self._blocked = False
        profiler = store.bootstrap() if bootstrap else store.load()
        self._capture = LocalTailObservationCapture(
            profiler, storage_path=storage_path, gpu_device=gpu_device,
        )

    def capture(self, timing: ExecutionTiming) -> DurableTailStatus:
        if self._blocked or self._store.quarantined:
            raise TailCustodyQuarantined("tail recorder requires reconciliation")
        try:
            self._capture.capture(timing)
            self._store.persist(self._capture.profiler)
        except BaseException:
            # A capture may have modified in-memory profile state before the
            # independent anchor committed. Never reuse this recorder.
            self._blocked = True
            raise
        return self.status()

    def status(self) -> DurableTailStatus:
        if self._blocked or self._store.quarantined:
            raise TailCustodyQuarantined("tail recorder requires reconciliation")
        # Reverify independent anchor, not just an in-memory profile digest.
        persisted, generation, _ = self._store.verified_snapshot()
        checkpoint = persisted.checkpoint()
        return DurableTailStatus(
            schema="skeleton.app.offline-durable-tail.v1",
            generation=generation,
            profile_digest=checkpoint["digest"],
            requests=len(checkpoint["records"]),
            quarantined=False,
        )


__all__ = ["OfflineDurableTailRecorder", "DurableTailStatus"]
