"""Recovery coordinator for stale worker ownership and queue claims."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from skeleton.shells.queue import QueueItem, ShellWorkQueue
from skeleton.shells.worker_heartbeat import HeartbeatRegistry, WorkerLiveness
from skeleton.shells.worker_identity import WorkerIdentity, WorkerRegistry


@dataclass(frozen=True)
class RecoveryPolicy:
    stale_claim_after_seconds: float = 60.0
    priority_delta_on_recovery: int = 10
    disable_stale_workers: bool = True
    unregister_stale_workers: bool = False
    max_recoveries_per_pass: int = 1000

    def __post_init__(self) -> None:
        if self.stale_claim_after_seconds <= 0:
            raise ValueError("stale_claim_after_seconds must be positive")
        if not isinstance(self.priority_delta_on_recovery, int):
            raise ValueError("priority_delta_on_recovery must be an integer")
        if self.max_recoveries_per_pass <= 0:
            raise ValueError("max_recoveries_per_pass must be positive")
        if self.disable_stale_workers and self.unregister_stale_workers:
            raise ValueError("disable_stale_workers and unregister_stale_workers are mutually exclusive")


@dataclass(frozen=True)
class WorkerRecovery:
    identity: WorkerIdentity
    claimed_items: tuple[str, ...]
    disabled: bool
    unregistered: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_dict(),
            "claimed_items": list(self.claimed_items),
            "disabled": self.disabled,
            "unregistered": self.unregistered,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RecoveryReport:
    recoveries: tuple[WorkerRecovery, ...]
    requeued: tuple[QueueItem, ...]
    started_at: float
    finished_at: float
    truncated: bool = False

    @property
    def worker_count(self) -> int:
        return len(self.recoveries)

    @property
    def item_count(self) -> int:
        return len(self.requeued)

    def to_dict(self) -> dict[str, object]:
        return {
            "worker_count": self.worker_count,
            "item_count": self.item_count,
            "duration_seconds": max(0.0, self.finished_at - self.started_at),
            "truncated": self.truncated,
            "recoveries": [item.to_dict() for item in self.recoveries],
            "requeued": [item.item_id for item in self.requeued],
        }


class WorkerRecoveryCoordinator:
    """Detect stale worker generations and recover their queue claims."""

    def __init__(
        self,
        *,
        workers: WorkerRegistry,
        heartbeats: HeartbeatRegistry,
        queue: ShellWorkQueue,
        policy: RecoveryPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.workers = workers
        self.heartbeats = heartbeats
        self.queue = queue
        self.policy = policy or RecoveryPolicy()
        self._clock = clock

    def _recover_identity(self, identity: WorkerIdentity) -> WorkerRecovery:
        claimed_before = self.queue.claimed(owner=identity.worker_id)
        recovered = self.queue.requeue_stale_claims(
            max_age_seconds=self.policy.stale_claim_after_seconds,
            owner=identity.worker_id,
            priority_delta=self.policy.priority_delta_on_recovery,
        )
        disabled = False
        unregistered = False
        if self.policy.unregister_stale_workers:
            unregistered = self.workers.unregister(identity)
            if unregistered:
                self.heartbeats.forget(identity)
        elif self.policy.disable_stale_workers:
            try:
                self.workers.set_enabled(identity, False)
                disabled = True
            except Exception:
                disabled = False
        return WorkerRecovery(
            identity=identity,
            claimed_items=tuple(item.item_id for item in recovered),
            disabled=disabled,
            unregistered=unregistered,
            reason="stale heartbeat",
        )

    def recover(self) -> RecoveryReport:
        started = self._clock()
        recoveries: list[WorkerRecovery] = []
        all_requeued: list[QueueItem] = []
        truncated = False

        for registration in self.workers.snapshot().registrations:
            view = self.heartbeats.liveness(registration.identity)
            if view.liveness is not WorkerLiveness.STALE:
                continue
            if len(all_requeued) >= self.policy.max_recoveries_per_pass:
                truncated = True
                break
            recovery = self._recover_identity(registration.identity)
            recoveries.append(recovery)
            for item_id in recovery.claimed_items:
                all_requeued.append(self.queue.get(item_id))
                if len(all_requeued) >= self.policy.max_recoveries_per_pass:
                    truncated = True
                    break
            if truncated:
                break

        return RecoveryReport(
            recoveries=tuple(recoveries),
            requeued=tuple(all_requeued),
            started_at=started,
            finished_at=self._clock(),
            truncated=truncated,
        )

    def recover_worker(self, identity: WorkerIdentity) -> WorkerRecovery:
        registration = self.workers.require_current(identity)
        view = self.heartbeats.liveness(registration.identity)
        if view.liveness is not WorkerLiveness.STALE:
            raise RuntimeError("worker is not stale")
        return self._recover_identity(identity)
