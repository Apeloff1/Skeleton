"""Application-owned offline inference stream admission and durable execution.

This bridge wires the canonical resource sampler and authenticated fair-stream
custody into an app-callable service. It intentionally never constructs a key
vault, untrusted SQLite path, simulated sensor or execution receipt.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
import sqlite3
import os
from typing import Callable

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
from skeleton.ai.model_runtime.private_sqlite import PrivateSQLiteHandle, open_private_sqlite


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
        revoke_queued_prompt: Callable[[str], None] | None = None,
        validate_queued_prompts: Callable[[list[dict[str, object]]], None] | None = None,
    ) -> None:
        if not isinstance(session, DurableFairStreamSession):
            raise ValueError("canonical durable session required")
        self._session = session
        self._operation_lock = Lock()
        self._guard = GuardedFairStreamDispatch(
            session, sampler if sampler is not None else LiveStreamBudgetSampler(),
            owner, storage_path=storage_path, revoke_queued_prompt=revoke_queued_prompt,
            validate_queued_prompts=validate_queued_prompts,
        )

    @classmethod
    def from_trusted_handles(
        cls, *, connection: sqlite3.Connection, custody_key: bytes,
        execution_key: bytes, session_id: str,
        watermark: TrustedHighWatermark, owner: DurableExecutionOwner,
        storage_path: str, bootstrap: bool = False,
        private_handle: PrivateSQLiteHandle | None = None,
    ) -> "OfflineAdaptiveDispatchService":
        """Never silently reset a previous session on a restart."""
        if type(bootstrap) is not bool:
            raise ValueError("explicit bootstrap boolean required")
        store = DurableFairStreamStore(
            connection, custody_key=custody_key, execution_key=execution_key,
            session_id=session_id, private_handle=private_handle,
        )
        session = (
            DurableFairStreamSession.bootstrap(store, watermark)
            if bootstrap else DurableFairStreamSession(store, watermark)
        )
        return cls(session, owner, storage_path=storage_path)

    @classmethod
    def from_private_database(
        cls, *, directory: str | os.PathLike[str],
        custody_key: bytes, execution_key: bytes, session_id: str,
        watermark: TrustedHighWatermark, owner: DurableExecutionOwner,
        storage_path: str, bootstrap: bool = False,
        max_database_bytes: int = 64 << 20,
    ) -> tuple["OfflineAdaptiveDispatchService", PrivateSQLiteHandle]:
        """App bootstrap with a private POSIX DB; caller retains handle custody.

        This never provisions the external monotonic anchor or execution keys.
        The caller must close the handle only after the service is quiescent.
        """
        handle = open_private_sqlite(
            directory, create=bootstrap, max_database_bytes=max_database_bytes,
        )
        try:
            service = cls.from_trusted_handles(
                connection=handle.connection,
                custody_key=custody_key, execution_key=execution_key,
                session_id=session_id, watermark=watermark, owner=owner,
                storage_path=storage_path, bootstrap=bootstrap, private_handle=handle,
            )
        except BaseException:
            handle.close()
            raise
        return service, handle

    @contextmanager
    def _operation(self):
        # Check before either lock: a fork may inherit a lock held by a
        # thread that no longer exists. No caller waits behind model I/O.
        self._session._require_owner_process()
        if not self._operation_lock.acquire(blocking=False):
            raise DispatchDeferred("another app dispatch operation is active")
        try:
            if not self._guard._lock.acquire(blocking=False):
                raise DispatchDeferred("another guard dispatch operation is active")
            try:
                yield
            finally:
                self._guard._lock.release()
        finally:
            self._operation_lock.release()

    def status(self) -> OfflineDispatchStatus:
        with self._operation():
            return self._status_from_state(self._session.verify())

    def _status_from_state(self, state: dict[str, object]) -> OfflineDispatchStatus:
        pending = state["checkpoint"]["pending"]
        return OfflineDispatchStatus(
            schema="skeleton.app.offline-dispatch-status.v1",
            generation=state["generation"],
            pending_leases=len(pending),
            quarantined=self._session.quarantined,
            execution_uncertain=self._guard.uncertain or bool(pending and not self._guard._issued),
        )

    def submit(self, request: StreamRequest) -> OfflineDispatchStatus:
        with self._operation():
            return self._status_from_state(self._guard.submit(request))

    def cancel(self, request_id: str, *, tenant_id: str | None = None) -> OfflineDispatchStatus:
        with self._operation():
            return self._status_from_state(self._guard.cancel(request_id, tenant_id=tenant_id))

    def reconcile_committed(
        self, *, journal: "FairStreamExecutionJournal",
        authorization: "RecoveryAuthorization", recovery_key: bytes,
    ) -> OfflineDispatchStatus:
        """Explicit operator-only recovery of an ALREADY committed receipt.

        Never invoke this automatically on startup. The caller must hold an
        independently signed, exact-generation operator approval and an
        exclusive canonical execution-journal handle. No model execution
        occurs during reconciliation, and no keys enter public status.
        """
        with self._operation():
            state = self._guard.reconcile_committed(
                journal=journal, authorization=authorization, recovery_key=recovery_key,
            )
            return self._status_from_state(state)

    def abandon_uncertain(self, *, authorization: object, recovery_key: bytes) -> OfflineDispatchStatus:
        """Trusted operator-only recovery, not a public user cancellation route."""
        with self._operation():
            state = self._guard.abandon_uncertain(authorization=authorization, recovery_key=recovery_key)
            return self._status_from_state(state)

    def execute_next(self, *, token_budget: int) -> dict[str, object]:
        """Plan and execute ONE source-bound slice; no backend on a hold.

        A deferred or uncertain result must not be converted into a successful
        inference response. The owner controls model execution, quota and
        durable result publication; only signed receipts retire pending leases.
        """
        with self._operation():
            return self._execute_next_locked(token_budget=token_budget)

    def _execute_next_locked(self, *, token_budget: int) -> dict[str, object]:
        permits, observation = self._guard.resume_or_plan_live(token_budget=token_budget)
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
        observation = self._guard._last_execution_observation
        if observation is None:
            raise DispatchUncertain("acknowledged execution observation unavailable")
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
