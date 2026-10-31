"""Application-owned offline inference stream admission and durable execution.

This bridge wires the canonical resource sampler and authenticated fair-stream
custody into an app-callable service. It intentionally never constructs a key
vault, untrusted SQLite path, simulated sensor or execution receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Mapping

from skeleton.ai.model_runtime.fair_stream_dispatch import (
    DispatchDeferred, DispatchUncertain, DurableExecutionOwner,
    GuardedFairStreamDispatch,
)
from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
from skeleton.ai.model_runtime.fair_stream_queue import StreamRequest
from skeleton.ai.model_runtime.fair_stream_session import (
    DurableFairStreamSession, TrustedHighWatermark,
)
from skeleton.ai.model_runtime.fair_stream_sqlite import DurableFairStreamStore


@dataclass(frozen=True, slots=True)
class OfflineDispatchStatus:
    """No secrets, model text, keys, filesystem paths or raw checkpoints."""

    schema: str
    generation: int
    pending_leases: int
    quarantined: bool
    execution_uncertain: bool


class OfflineAdaptiveDispatchService:
    """CPU-only canonical app service; no implicit retry after execution.

    The app supplies a securely opened, exclusively owned SQLite connection,
    independently trusted high-watermark and authorized execution owner.
    Callers must not share the connection with another writer or trust this
    class to provision keys or durable result storage.
    """

    def __init__(
        self, session: DurableFairStreamSession,
        owner: DurableExecutionOwner,
        *, storage_path: str,
        sampler: LiveStreamBudgetSampler | None = None,
    ) -> None:
        if not isinstance(session, DurableFairStreamSession):
            raise ValueError("canonical durable session required")
        self._session = session
        self._guard = GuardedFairStreamDispatch(
            session, sampler if sampler is not None else LiveStreamBudgetSampler(),
            owner, storage_path=storage_path,
        )

    @classmethod
    def from_trusted_handles(
        cls, *, connection: sqlite3.Connection, custody_key: bytes,
        execution_key: bytes, session_id: str,
        watermark: TrustedHighWatermark, owner: DurableExecutionOwner,
        storage_path: str, bootstrap: bool = False,
    ) -> "OfflineAdaptiveDispatchService":
        """Never silently reset a previous session on a restart."""
        store = DurableFairStreamStore(
            connection, custody_key=custody_key, execution_key=execution_key,
            session_id=session_id,
        )
        if type(bootstrap) is not bool:
            raise ValueError("explicit bootstrap boolean required")
        session = (
            DurableFairStreamSession.bootstrap(store, watermark)
            if bootstrap else DurableFairStreamSession(store, watermark)
        )
        return cls(session, owner, storage_path=storage_path)

    def status(self) -> OfflineDispatchStatus:
        state = self._session.verify()
        return OfflineDispatchStatus(
            schema="skeleton.app.offline-dispatch-status.v1",
            generation=state["generation"],
            pending_leases=len(self._session.pending_ids()),
            quarantined=self._session.quarantined,
            execution_uncertain=self._guard.uncertain,
        )

    def submit(self, request: StreamRequest) -> OfflineDispatchStatus:
        self._guard.submit(request)
        return self.status()

    def cancel(self, request_id: str) -> OfflineDispatchStatus:
        self._guard.cancel(request_id)
        return self.status()

    def execute_next(self, *, token_budget: int) -> dict[str, object]:
        """Plan and execute ONE source-bound slice; no backend on a hold.

        A deferred or uncertain result must not be converted into a successful
        inference response. The owner controls model execution, quota and
        durable result publication; only signed receipts retire pending leases.
        """
        permits, observation = self._guard.plan_live(token_budget=token_budget)
        if not permits:
            return {
                "schema": "skeleton.app.offline-dispatch-result.v1",
                "state": "idle",
                "executed": False,
                "gpu_device_qualified": False,
                "observation": {
                    "pressure_ppm": observation.pressure_ppm,
                    "auxiliary_telemetry_incomplete": observation.auxiliary_telemetry_incomplete,
                },
            }
        if len(permits) != 1:
            raise DispatchUncertain("single-flight execution contract violated")
        state = self._guard.execute_once(permits[0])
        return {
            "schema": "skeleton.app.offline-dispatch-result.v1",
            "state": "durably_acknowledged",
            "executed": True,
            "gpu_device_qualified": False,
            "generation": state["generation"],
            "checkpoint_digest": state["checkpoint_digest"],
            "lease_id": permits[0].lease_id,
            "observation": {
                "pressure_ppm": observation.pressure_ppm,
                "auxiliary_telemetry_incomplete": observation.auxiliary_telemetry_incomplete,
            },
        }
