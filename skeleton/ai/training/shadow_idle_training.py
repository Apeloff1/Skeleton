"""Idle-only shadow training dispatcher with fenced leases and staged custody.

The dispatcher does not train or promote models by itself. Callers supply an
actual trainer that produces a dataset revision, manifest and native candidate
checkpoint; the dispatcher strictly transfers its results into shadow custody.
The independent mirror, admission and serving gates are intentionally separate.

Long jobs call session.heartbeat() to extend their lease, passing the updated
fencing token to the final acknowledgement. Interactive load immediately
preempts background work at the next heartbeat or commit boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .flgb_training_runtime import (
    DatasetRevision, TrainingCheckpoint, TrainingManifest, require_id,
)
from .shadow_training_handoff import stage_trained_shadow
from .shadow_weight_intake import ShadowIntakeLease, ShadowKnowledgeQueue
from .shadow_weight_ledger import ShadowWeightLedger
from .shadow_weights import ShadowWeightError


class ShadowTrainingPaused(ShadowWeightError):
    """Background capacity is no longer available for this training job."""


class ShadowTrainingRejected(ShadowWeightError):
    """Explicit permanent rejection from the trusted candidate trainer."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = require_id(reason_code, "training rejection reason")
        super().__init__(f"shadow candidate rejected: {reason_code}")


@dataclass(frozen=True, slots=True)
class ShadowTrainingArtifacts:
    """Real training output. Neither scores nor hashes synthesize these objects."""

    dataset: DatasetRevision
    manifest: TrainingManifest
    checkpoint: TrainingCheckpoint
    candidate_id: str
    checkpoint_path: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dataset, DatasetRevision):
            raise ShadowWeightError("training worker must return a dataset revision")
        if not isinstance(self.manifest, TrainingManifest):
            raise ShadowWeightError("training worker must return a training manifest")
        if not isinstance(self.checkpoint, TrainingCheckpoint):
            raise ShadowWeightError("training worker must return a materialized checkpoint")
        require_id(self.candidate_id, "trained candidate_id")


@dataclass(frozen=True, slots=True)
class ShadowWorkReceipt:
    """One background dispatch result, not a production promotion certificate."""

    knowledge_id: str
    disposition: str
    worker_id: str
    handoff_digest: str | None = None
    candidate_id: str | None = None
    ledger_revision: int | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        require_id(self.knowledge_id, "knowledge_id")
        require_id(self.worker_id, "worker_id")
        if self.disposition not in {"staged", "quarantined", "paused"}:
            raise ShadowWeightError("unknown background work disposition")


class ShadowLeaseSession:
    """Mutable local lease handle; durable revision ownership stays in SQLite."""

    def __init__(
        self, queue: ShadowKnowledgeQueue, lease: ShadowIntakeLease,
        *, is_idle: Callable[[], bool],
    ) -> None:
        if not isinstance(queue, ShadowKnowledgeQueue):
            raise ShadowWeightError("shadow queue required")
        if not isinstance(lease, ShadowIntakeLease):
            raise ShadowWeightError("shadow lease required")
        if not callable(is_idle):
            raise ShadowWeightError("idle admission callback required")
        self._queue = queue
        self._lease = lease
        self._is_idle = is_idle
        self._finished = False

    @property
    def lease(self) -> ShadowIntakeLease:
        return self._lease

    def require_idle(self) -> None:
        if self._finished:
            raise ShadowWeightError("shadow lease session has finished")
        state = self._is_idle()
        if not isinstance(state, bool) or not state:
            raise ShadowTrainingPaused("interactive workload preempted shadow training")

    def heartbeat(self, *, duration_seconds: int = 900) -> ShadowIntakeLease:
        """Refresh the deadline and revision; old lease tokens become invalid."""
        self.require_idle()
        self._lease = self._queue.renew(
            self._lease, idle=True, duration_seconds=duration_seconds,
        )
        return self._lease

    def _finish(self) -> None:
        self._finished = True


class ShadowIdleTrainingWorker:
    """Connect an idle scheduler to real candidate training and shadow ledger.

    Every invocation handles at most one bounded leased observation; repeated
    invocations are scheduled externally. Training code should heartbeat for
    jobs longer than their lease and stop when a heartbeat is preempted.
    """

    def __init__(
        self, queue: ShadowKnowledgeQueue, ledger: ShadowWeightLedger,
        *, worker_id: str, is_idle: Callable[[], bool],
        trainer: Callable[[ShadowLeaseSession], ShadowTrainingArtifacts],
        lease_seconds: int = 900,
    ) -> None:
        if not isinstance(queue, ShadowKnowledgeQueue):
            raise ShadowWeightError("shadow intake queue required")
        if not isinstance(ledger, ShadowWeightLedger):
            raise ShadowWeightError("candidate custody ledger required")
        self.worker_id = require_id(worker_id, "worker_id")
        if not callable(is_idle) or not callable(trainer):
            raise ShadowWeightError("scheduler and trainer callbacks required")
        if (
            isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int)
            or not 15 <= lease_seconds <= 86_400
        ):
            raise ShadowWeightError("invalid shadow worker lease seconds")
        self.queue = queue
        self.ledger = ledger
        self.is_idle = is_idle
        self.trainer = trainer
        self.lease_seconds = lease_seconds

    def run_once(self) -> ShadowWorkReceipt | None:
        """Do real training only while idle; never implicitly promote weights."""
        idle = self.is_idle()
        if not isinstance(idle, bool):
            raise ShadowWeightError("idle scheduler must return a boolean")
        lease = self.queue.lease(
            self.worker_id, idle=idle, duration_seconds=self.lease_seconds,
        )
        if lease is None:
            return None
        session = ShadowLeaseSession(self.queue, lease, is_idle=self.is_idle)
        try:
            session.require_idle()
            artifacts = self.trainer(session)
            if not isinstance(artifacts, ShadowTrainingArtifacts):
                raise ShadowWeightError("trainer did not return candidate artifacts")
            session.require_idle()
            handoff, snapshot = stage_trained_shadow(
                self.queue, self.ledger, session.lease,
                artifacts.dataset, artifacts.manifest, artifacts.checkpoint,
                candidate_id=artifacts.candidate_id,
            )
            session._finish()
            return ShadowWorkReceipt(
                knowledge_id=lease.knowledge.knowledge_id,
                disposition="staged", worker_id=self.worker_id,
                handoff_digest=handoff.digest,
                candidate_id=artifacts.candidate_id,
                ledger_revision=snapshot.revision,
            )
        except ShadowTrainingRejected as exc:
            self.queue.quarantine_lease(
                session.lease, reason_code=exc.reason_code,
            )
            session._finish()
            return ShadowWorkReceipt(
                knowledge_id=lease.knowledge.knowledge_id,
                disposition="quarantined", worker_id=self.worker_id,
                reason_code=exc.reason_code,
            )
        except ShadowTrainingPaused:
            try:
                self.queue.release(session.lease)
            except ShadowWeightError:
                # A timed-out or stolen lease is already fenced out by the DB.
                pass
            session._finish()
            return ShadowWorkReceipt(
                knowledge_id=lease.knowledge.knowledge_id,
                disposition="paused", worker_id=self.worker_id,
            )
        except Exception:
            try:
                self.queue.release(session.lease, backoff=True)
            except ShadowWeightError:
                # Preserve the original training failure, not a stale lease error.
                pass
            session._finish()
            raise


__all__ = [
    "ShadowTrainingPaused", "ShadowTrainingRejected", "ShadowTrainingArtifacts",
    "ShadowWorkReceipt", "ShadowLeaseSession", "ShadowIdleTrainingWorker",
]
