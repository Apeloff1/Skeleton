"""Application-owned offline inference stream admission and durable execution.

This bridge wires the canonical resource sampler and authenticated fair-stream
custody into an app-callable service. It intentionally never constructs a key
vault, untrusted SQLite path, simulated sensor or execution receipt.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hmac
import sqlite3
import os
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from skeleton.ai.model_runtime.fair_stream_execution_journal import FairStreamExecutionJournal
    from skeleton.ai.model_runtime.fair_stream_recovery import AbandonmentAuthorization, RecoveryAuthorization

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


def _validate_operator_provisioning(
    operator_key: bytes | None, custody_key: bytes, execution_key: bytes,
) -> None:
    """Reject invalid recovery configuration before opening or bootstrapping custody."""
    if operator_key is not None and (
        type(operator_key) is not bytes or not 32 <= len(operator_key) <= 128
        or any(type(key) is not bytes or hmac.compare_digest(operator_key, key)
               for key in (custody_key, execution_key))
    ):
        raise ValueError("independent operator recovery key required")


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
        whole_request: bool = False,
        queued_authority: Callable[[dict[str, object]], None] | None = None,
        cancel_cleanup: Callable[[str], None] | None = None,
        prepare_request: Callable[[StreamRequest], StreamRequest] | None = None,
        operator_recovery_key: bytes | None = None,
    ) -> None:
        if not isinstance(session, DurableFairStreamSession):
            raise ValueError("canonical durable session required")
        self._session = session
        self._guard = GuardedFairStreamDispatch(
            session, sampler if sampler is not None else LiveStreamBudgetSampler(),
            owner, storage_path=storage_path, whole_request=whole_request,
            queued_authority=queued_authority, cancel_cleanup=cancel_cleanup,
            prepare_request=prepare_request, operator_recovery_key=operator_recovery_key,
        )

    @classmethod
    def from_trusted_handles(
        cls, *, connection: sqlite3.Connection, custody_key: bytes,
        execution_key: bytes, session_id: str,
        watermark: TrustedHighWatermark, owner: DurableExecutionOwner,
        storage_path: str, bootstrap: bool = False, whole_request: bool = False,
        private_handle: PrivateSQLiteHandle | None = None,
        operator_recovery_key: bytes | None = None,
    ) -> "OfflineAdaptiveDispatchService":
        """Never silently reset a previous session on a restart."""
        if type(bootstrap) is not bool:
            raise ValueError("explicit bootstrap boolean required")
        _validate_operator_provisioning(operator_recovery_key, custody_key, execution_key)
        store = DurableFairStreamStore(
            connection, custody_key=custody_key, execution_key=execution_key,
            session_id=session_id, whole_request=whole_request,
            private_handle=private_handle,
        )
        session = (
            DurableFairStreamSession.bootstrap(store, watermark)
            if bootstrap else DurableFairStreamSession(store, watermark)
        )
        return cls(session, owner, storage_path=storage_path, whole_request=whole_request,
                   operator_recovery_key=operator_recovery_key)

    @classmethod
    def from_private_database(
        cls, *, directory: str | os.PathLike[str],
        custody_key: bytes, execution_key: bytes, session_id: str,
        watermark: TrustedHighWatermark, owner: DurableExecutionOwner,
        storage_path: str, bootstrap: bool = False,
        max_database_bytes: int = 64 << 20, whole_request: bool = False,
        operator_recovery_key: bytes | None = None,
    ) -> tuple["OfflineAdaptiveDispatchService", PrivateSQLiteHandle]:
        """App bootstrap with a private POSIX DB; caller retains handle custody.

        This never provisions the external monotonic anchor or execution keys.
        The caller must close the handle only after the service is quiescent.
        """
        if type(bootstrap) is not bool:
            raise ValueError("explicit bootstrap boolean required")
        _validate_operator_provisioning(operator_recovery_key, custody_key, execution_key)
        handle = open_private_sqlite(
            directory, create=bootstrap, max_database_bytes=max_database_bytes,
        )
        try:
            service = cls.from_trusted_handles(
                connection=handle.connection,
                custody_key=custody_key, execution_key=execution_key,
                session_id=session_id, watermark=watermark, owner=owner,
                storage_path=storage_path, bootstrap=bootstrap, whole_request=whole_request,
                private_handle=handle, operator_recovery_key=operator_recovery_key,
            )
        except BaseException:
            handle.close()
            raise
        return service, handle

    @contextmanager
    def _operation(self):
        """Never wait behind native model I/O; retain the guard's lock order."""
        self._guard._require_owner_process()
        if not self._guard._lock.acquire(blocking=False):
            raise DispatchDeferred("another app dispatch operation is active")
        try:
            yield
        finally:
            self._guard._lock.release()

    def _status_from_state(self, state: dict[str, object]) -> OfflineDispatchStatus:
        pending = state["checkpoint"]["pending"]
        known = (len(pending) == len(self._guard._issued) == 1
                 and pending[0]["lease_id"] in self._guard._issued)
        return OfflineDispatchStatus(
            schema="skeleton.app.offline-dispatch-status.v1",
            generation=state["generation"],
            pending_leases=len(pending),
            quarantined=self._session.quarantined,
            execution_uncertain=(self._guard._uncertain or self._guard._executing
                                 or bool(pending and not known)),
        )

    def status(self) -> OfflineDispatchStatus:
        with self._operation():
            return self._status_from_state(self._session.verify())

    def submit(self, request: StreamRequest) -> OfflineDispatchStatus:
        with self._operation():
            return self._status_from_state(self._guard.submit(request))

    def cancel(self, request_id: str, *, tenant_id: str | None = None) -> OfflineDispatchStatus:
        with self._operation():
            return self._status_from_state(self._guard.cancel(request_id, tenant_id=tenant_id))

    def cancel_unstarted(self, request_id: str, *, tenant_id: str) -> OfflineDispatchStatus:
        """Explicit tenant cancellation of a current-process unstarted permit."""
        with self._operation():
            return self._status_from_state(self._guard.cancel_unstarted(request_id, tenant_id=tenant_id))

    def reconcile_published(
        self, *, authorization: "RecoveryAuthorization", recovery_key: bytes,
    ) -> OfflineDispatchStatus:
        """Operator-approved recovery of existing authenticated sealed output."""
        with self._operation():
            return self._status_from_state(self._guard.reconcile_published(
                authorization=authorization, recovery_key=recovery_key,
            ))

    def reconcile_cancelled(
        self, *, authorization: "RecoveryAuthorization", recovery_key: bytes,
    ) -> OfflineDispatchStatus:
        """Explicitly settle a durable cancellation using a separate operator grant."""
        with self._operation():
            return self._status_from_state(self._guard.reconcile_cancelled(
                authorization=authorization, recovery_key=recovery_key,
            ))

    def abandon_uncertain(
        self, *, authorization: "AbandonmentAuthorization", recovery_key: bytes,
    ) -> OfflineDispatchStatus:
        """Operator-only no-output retirement; never initiate inference."""
        with self._operation():
            return self._status_from_state(self._guard.abandon_uncertain(
                authorization=authorization, recovery_key=recovery_key,
            ))

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
            return self._status_from_state(self._guard.reconcile_committed(
                journal=journal, authorization=authorization,
                recovery_key=recovery_key,
            ))

    def execute_next(self, *, token_budget: int) -> dict[str, object]:
        """Plan and execute ONE source-bound slice; no backend on a hold.

        A deferred or uncertain result must not be converted into a successful
        inference response. The owner controls model execution, quota and
        durable result publication; only signed receipts retire pending leases.
        """
        with self._operation():
            permit, state, observation = self._guard.dispatch_next(token_budget=token_budget)
        if permit is None:
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
        if state is None:
            raise DispatchUncertain("single-flight execution contract violated")
        return {
            "schema": "skeleton.app.offline-dispatch-result.v1",
            "state": "durably_acknowledged",
            "executed": True,
            "gpu_device_qualified": False,
            "generation": state["generation"],
            "checkpoint_digest": state["checkpoint_digest"],
            "lease_id": permit.lease_id,
            "observation": {
                "pressure_ppm": observation.pressure_ppm,
                "auxiliary_telemetry_incomplete": observation.auxiliary_telemetry_incomplete,
            },
        }
