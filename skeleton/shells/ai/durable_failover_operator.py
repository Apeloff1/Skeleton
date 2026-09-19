"""Operator-facing orchestration for durable replica synchronization and failover.

This surface does not switch external traffic or mutate deployment routing.
It coordinates existing replication/fleet/failover authorities, reports the
exact state an operator is acting on, and keeps synchronization, ticket issue,
claim, apply authorization, and cancellation as explicit separate operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import time
from typing import Callable

from skeleton.shells.ai.durable_failover import (
    DurableFailoverCoordinator,
    DurableFailoverPhase,
    DurableFailoverTicketError,
    SignedDurableFailoverTicket,
    StoredDurableFailover,
)
from skeleton.shells.ai.durable_replica_consensus import (
    DurableReplicaConsensusReport,
)
from skeleton.shells.ai.durable_replica_consensus_history import (
    StoredDurableReplicaConsensusEpoch,
)
from skeleton.shells.ai.durable_replica_fleet import (
    DurableReplicaFleet,
    DurableReplicaFleetReport,
    DurableReplicaFleetRun,
)
from skeleton.shells.ai.durable_replication import (
    DurableEvidenceReplicaManager,
    DurableEvidenceReplicationReport,
    DurableEvidenceReplicationRun,
)


class DurableFailoverOperatorState(str, Enum):
    READY = "ready"
    NEEDS_SYNC = "needs_sync"
    QUORUM_BLOCKED = "quorum_blocked"
    TARGET_BLOCKED = "target_blocked"
    CONSENSUS_BLOCKED = "consensus_blocked"
    HISTORY_BLOCKED = "history_blocked"
    CLAIMED = "claimed"
    APPLIED = "applied"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class DurableFailoverOperatorPolicy:
    max_batches_per_sync: int = 64
    require_fleet_quorum: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_batches_per_sync, bool)
            or not isinstance(self.max_batches_per_sync, int)
            or not 1 <= self.max_batches_per_sync <= 4096
        ):
            raise ValueError(
                "max_batches_per_sync outside supported range"
            )
        if not isinstance(
            self.require_fleet_quorum,
            bool,
        ):
            raise ValueError(
                "require_fleet_quorum must be bool"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "max_batches_per_sync": self.max_batches_per_sync,
            "require_fleet_quorum": self.require_fleet_quorum,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DurableFailoverOperatorReport:
    source_id: str
    target_id: str
    observed_at: float
    state: DurableFailoverOperatorState
    replication: DurableEvidenceReplicationReport
    fleet: DurableReplicaFleetReport | None
    failover: StoredDurableFailover | None
    ticket_id: str
    policy_digest: str
    reason: str = ""
    consensus: DurableReplicaConsensusReport | None = None
    consensus_history: StoredDurableReplicaConsensusEpoch | None = None

    def __post_init__(self) -> None:
        for name in ("source_id", "target_id"):
            value = getattr(self, name)
            if not value or len(value) > 128:
                raise ValueError(f"invalid {name}")
        if self.source_id == self.target_id:
            raise ValueError(
                "operator source_id and target_id must differ"
            )
        if (
            isinstance(self.observed_at, bool)
            or not isinstance(self.observed_at, (int, float))
            or not math.isfinite(float(self.observed_at))
            or float(self.observed_at) < 0.0
        ):
            raise ValueError(
                "observed_at must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "observed_at",
            float(self.observed_at),
        )
        object.__setattr__(
            self,
            "state",
            DurableFailoverOperatorState(
                self.state
            ),
        )
        if not isinstance(
            self.replication,
            DurableEvidenceReplicationReport,
        ):
            raise TypeError(
                "replication must be DurableEvidenceReplicationReport"
            )
        if (
            self.fleet is not None
            and not isinstance(
                self.fleet,
                DurableReplicaFleetReport,
            )
        ):
            raise TypeError(
                "fleet must be DurableReplicaFleetReport"
            )
        if (
            self.failover is not None
            and not isinstance(
                self.failover,
                StoredDurableFailover,
            )
        ):
            raise TypeError(
                "failover must be StoredDurableFailover"
            )
        if self.ticket_id and len(self.ticket_id) != 64:
            raise ValueError(
                "ticket_id must be SHA-256 hex"
            )
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be SHA-256 hex"
            )
        if len(self.reason) > 2048:
            raise ValueError("operator reason too long")
        if (
            self.consensus is not None
            and not isinstance(
                self.consensus,
                DurableReplicaConsensusReport,
            )
        ):
            raise TypeError(
                "consensus must be DurableReplicaConsensusReport"
            )
        if (
            self.consensus_history is not None
            and not isinstance(
                self.consensus_history,
                StoredDurableReplicaConsensusEpoch,
            )
        ):
            raise TypeError(
                "consensus_history must be StoredDurableReplicaConsensusEpoch"
            )

    @property
    def can_issue(self) -> bool:
        return self.state is DurableFailoverOperatorState.READY

    @property
    def terminal(self) -> bool:
        return self.state in {
            DurableFailoverOperatorState.APPLIED,
            DurableFailoverOperatorState.CANCELLED,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "observed_at": self.observed_at,
            "state": self.state.value,
            "replication": self.replication.to_dict(),
            "fleet": (
                None
                if self.fleet is None
                else self.fleet.to_dict()
            ),
            "failover": (
                None
                if self.failover is None
                else {
                    "revision": self.failover.revision,
                    "record": self.failover.record.to_dict(),
                }
            ),
            "ticket_id": self.ticket_id,
            "policy_digest": self.policy_digest,
            "reason": self.reason,
            "can_issue": self.can_issue,
            "terminal": self.terminal,
            "consensus": (
                None
                if self.consensus is None
                else self.consensus.to_dict()
            ),
            "consensus_history": (
                None
                if self.consensus_history is None
                else self.consensus_history.to_dict()
            ),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableFailoverSyncResult:
    before: DurableFailoverOperatorReport
    target_run: DurableEvidenceReplicationRun
    fleet_run: DurableReplicaFleetRun | None
    after: DurableFailoverOperatorReport

    @property
    def transferred_items(self) -> int:
        fleet_items = (
            0
            if self.fleet_run is None
            else self.fleet_run.transferred_items
        )
        return (
            self.target_run.transferred_items
            + fleet_items
        )

    @property
    def ready(self) -> bool:
        return self.after.can_issue

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "before": self.before.to_dict(),
            "target_run": self.target_run.to_dict(),
            "fleet_run": (
                None
                if self.fleet_run is None
                else self.fleet_run.to_dict()
            ),
            "after": self.after.to_dict(),
            "transferred_items": self.transferred_items,
            "ready": self.ready,
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableFailoverTicketResult:
    report: DurableFailoverOperatorReport
    ticket: SignedDurableFailoverTicket

    def __post_init__(self) -> None:
        if self.report.ticket_id and (
            self.report.ticket_id
            != self.ticket.ticket.ticket_id
        ):
            raise ValueError(
                "operator report/ticket identity mismatch"
            )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(include_digest=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data = {
            "report": self.report.to_dict(),
            "ticket": self.ticket.to_dict(),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableFailoverOperatorError(RuntimeError):
    pass


class DurableFailoverOperator:
    """Coordinate explicit durable-replica recovery actions for operators."""

    def __init__(
        self,
        manager: DurableEvidenceReplicaManager,
        coordinator: DurableFailoverCoordinator,
        *,
        fleet: DurableReplicaFleet | None = None,
        policy: DurableFailoverOperatorPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            manager,
            DurableEvidenceReplicaManager,
        ):
            raise TypeError(
                "manager must be DurableEvidenceReplicaManager"
            )
        if not isinstance(
            coordinator,
            DurableFailoverCoordinator,
        ):
            raise TypeError(
                "coordinator must be DurableFailoverCoordinator"
            )
        if (
            fleet is not None
            and not isinstance(
                fleet,
                DurableReplicaFleet,
            )
        ):
            raise TypeError(
                "fleet must be DurableReplicaFleet"
            )
        if (
            coordinator.manager is not manager
        ):
            raise ValueError(
                "operator manager differs from coordinator manager"
            )
        if (
            coordinator.fleet is not fleet
        ):
            raise ValueError(
                "operator fleet differs from coordinator fleet"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.manager = manager
        self.coordinator = coordinator
        self.fleet = fleet
        self.policy = (
            policy
            or DurableFailoverOperatorPolicy()
        )
        self._clock = clock

    def _now(self) -> float:
        value = float(self._clock())
        if not math.isfinite(value) or value < 0.0:
            raise DurableFailoverOperatorError(
                "operator clock returned invalid time"
            )
        return value

    def inspect(
        self,
        *,
        ticket_id: str = "",
    ) -> DurableFailoverOperatorReport:
        replication = self.manager.inspect()
        fleet_report = (
            None
            if self.fleet is None
            else self.fleet.inspect()
        )
        failover = (
            None
            if not ticket_id
            else self.coordinator.registry.current(
                ticket_id
            )
        )

        reason = ""
        state = DurableFailoverOperatorState.READY
        if failover is not None:
            phase = failover.record.phase
            if phase is DurableFailoverPhase.APPLIED:
                state = DurableFailoverOperatorState.APPLIED
            elif phase is DurableFailoverPhase.CANCELLED:
                state = DurableFailoverOperatorState.CANCELLED
            else:
                state = DurableFailoverOperatorState.CLAIMED
        elif not replication.promotion_ready:
            state = DurableFailoverOperatorState.NEEDS_SYNC
            reason = (
                "target journal/receipt replica is not current"
            )
        elif (
            self.policy.require_fleet_quorum
            and self.fleet is None
        ):
            state = DurableFailoverOperatorState.QUORUM_BLOCKED
            reason = (
                "operator policy requires replica fleet quorum"
            )
        elif (
            fleet_report is not None
            and not fleet_report.quorum_ready
        ):
            state = DurableFailoverOperatorState.QUORUM_BLOCKED
            reason = (
                fleet_report.findings[0].message
                if fleet_report.findings
                else "replica fleet quorum is not ready"
            )
        elif fleet_report is not None:
            try:
                target = fleet_report.member(
                    self.coordinator.target_id
                )
            except KeyError:
                state = DurableFailoverOperatorState.TARGET_BLOCKED
                reason = (
                    "selected target is not a fleet member"
                )
            else:
                if not target.ready:
                    state = DurableFailoverOperatorState.TARGET_BLOCKED
                    reason = (
                        "selected target is not fleet-ready"
                    )

        consensus_report = None
        consensus_history = None
        if (
            failover is None
            and state
            is DurableFailoverOperatorState.READY
            and self.coordinator.consensus is not None
        ):
            try:
                consensus_report = (
                    self.coordinator.consensus_report()
                )
            except DurableFailoverTicketError as exc:
                state = (
                    DurableFailoverOperatorState
                    .CONSENSUS_BLOCKED
                )
                reason = str(exc)[:2048]
            else:
                try:
                    consensus_history = (
                        self.coordinator
                        .verify_consensus_history_current(
                            consensus_report
                        )
                    )
                except DurableFailoverTicketError as exc:
                    state = (
                        DurableFailoverOperatorState
                        .HISTORY_BLOCKED
                    )
                    reason = str(exc)[:2048]

        return DurableFailoverOperatorReport(
            self.coordinator.source_id,
            self.coordinator.target_id,
            self._now(),
            state,
            replication,
            fleet_report,
            failover,
            ticket_id,
            self.policy.digest,
            reason,
            consensus_report,
            consensus_history,
        )

    def synchronize(
        self,
        *,
        sync_fleet: bool = True,
        max_batches: int | None = None,
    ) -> DurableFailoverSyncResult:
        if not isinstance(sync_fleet, bool):
            raise ValueError("sync_fleet must be bool")
        limit = (
            self.policy.max_batches_per_sync
            if max_batches is None
            else max_batches
        )
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 4096
        ):
            raise ValueError(
                "max_batches outside supported range"
            )
        before = self.inspect()
        target_run = self.manager.sync(
            max_batches=limit
        )
        fleet_run = None
        if sync_fleet and self.fleet is not None:
            fleet_run = self.fleet.sync_all(
                max_batches=limit
            )
        return DurableFailoverSyncResult(
            before,
            target_run,
            fleet_run,
            self.inspect(),
        )

    def issue(
        self,
        *,
        ttl_seconds: float = 60.0,
    ) -> DurableFailoverTicketResult:
        before = self.inspect()
        if not before.can_issue:
            raise DurableFailoverOperatorError(
                "failover ticket cannot be issued: "
                f"{before.state.value}: {before.reason}"
            )
        ticket = self.coordinator.issue(
            ttl_seconds=ttl_seconds
        )
        return DurableFailoverTicketResult(
            self.inspect(
                ticket_id=ticket.ticket.ticket_id
            ),
            ticket,
        )

    def claim(
        self,
        ticket: SignedDurableFailoverTicket,
        *,
        consumer_id: str,
    ) -> DurableFailoverOperatorReport:
        self.coordinator.claim(
            ticket,
            consumer_id=consumer_id,
        )
        return self.inspect(
            ticket_id=ticket.ticket.ticket_id
        )

    def complete(
        self,
        ticket: SignedDurableFailoverTicket,
        *,
        consumer_id: str,
    ) -> DurableFailoverOperatorReport:
        self.coordinator.complete(
            ticket,
            consumer_id=consumer_id,
        )
        return self.inspect(
            ticket_id=ticket.ticket.ticket_id
        )

    def cancel(
        self,
        ticket: SignedDurableFailoverTicket,
        *,
        consumer_id: str,
    ) -> DurableFailoverOperatorReport:
        self.coordinator.cancel(
            ticket,
            consumer_id=consumer_id,
        )
        return self.inspect(
            ticket_id=ticket.ticket.ticket_id
        )
