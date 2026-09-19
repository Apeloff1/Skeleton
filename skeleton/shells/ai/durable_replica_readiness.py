"""Replica-aware admission guard for the durable evidence plane.

Local chain readiness is necessary but insufficient for a replicated durable
system.  A worker should not advertise promotion-capable readiness while the
replica fleet lacks quorum, the replicas disagree about source history, or the
agreed history conflicts with the monotonic consensus lineage.

This module composes the existing local readiness guard, replica fleet,
consensus evaluator, and optional consensus-history store.  Inspection is
strictly non-mutating.  Reconciliation may invoke the existing local repair
surface and, when explicitly enabled, append a new consensus-history epoch only
after local readiness, fleet quorum, and replica consensus are all valid.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

from skeleton.shells.ai.durable_readiness import (
    DurableEvidenceReadinessGuard,
    DurableEvidenceReadinessReport,
)
from skeleton.shells.ai.durable_replica_consensus import (
    DurableReplicaConsensusEvaluator,
    DurableReplicaConsensusReport,
)
from skeleton.shells.ai.durable_replica_consensus_history import (
    DurableReplicaConsensusHistoryError,
    DurableReplicaConsensusHistoryStore,
    StoredDurableReplicaConsensusEpoch,
)
from skeleton.shells.ai.durable_replica_fleet import (
    DurableReplicaFleet,
    DurableReplicaFleetReport,
)


def _stable_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


class DurableReplicaReadinessState(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    ERROR = "error"


class DurableReplicaReadinessSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class DurableReplicaReadinessPolicy:
    require_local_ready: bool = True
    require_fleet_quorum: bool = True
    require_consensus: bool = True
    require_history_store: bool = False
    require_history_initialized: bool = False
    require_history_current: bool = True
    allow_history_record_on_reconcile: bool = True
    max_findings: int = 256

    def __post_init__(self) -> None:
        for name in (
            "require_local_ready",
            "require_fleet_quorum",
            "require_consensus",
            "require_history_store",
            "require_history_initialized",
            "require_history_current",
            "allow_history_record_on_reconcile",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        if (
            self.require_history_initialized
            and not self.require_history_current
        ):
            raise ValueError(
                "initialized history requirement implies current history requirement"
            )
        if (
            isinstance(self.max_findings, bool)
            or not isinstance(
                self.max_findings,
                int,
            )
            or not 1 <= self.max_findings <= 65536
        ):
            raise ValueError(
                "max_findings outside supported range"
            )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict()
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "require_local_ready": (
                self.require_local_ready
            ),
            "require_fleet_quorum": (
                self.require_fleet_quorum
            ),
            "require_consensus": (
                self.require_consensus
            ),
            "require_history_store": (
                self.require_history_store
            ),
            "require_history_initialized": (
                self.require_history_initialized
            ),
            "require_history_current": (
                self.require_history_current
            ),
            "allow_history_record_on_reconcile": (
                self.allow_history_record_on_reconcile
            ),
            "max_findings": self.max_findings,
        }


@dataclass(frozen=True)
class DurableReplicaReadinessFinding:
    severity: DurableReplicaReadinessSeverity
    code: str
    message: str
    target_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "severity",
            DurableReplicaReadinessSeverity(
                self.severity
            ),
        )
        if not self.code or len(self.code) > 128:
            raise ValueError(
                "invalid replica readiness finding code"
            )
        if not self.message or len(self.message) > 2048:
            raise ValueError(
                "invalid replica readiness finding message"
            )
        if len(self.target_id) > 128:
            raise ValueError(
                "replica readiness target_id too long"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "target_id": self.target_id,
        }


@dataclass(frozen=True)
class DurableReplicaReadinessReport:
    state: DurableReplicaReadinessState
    policy_digest: str
    local: DurableEvidenceReadinessReport
    fleet: DurableReplicaFleetReport
    consensus: DurableReplicaConsensusReport
    history: StoredDurableReplicaConsensusEpoch | None
    mutations: tuple[str, ...]
    findings: tuple[
        DurableReplicaReadinessFinding,
        ...,
    ]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "state",
            DurableReplicaReadinessState(
                self.state
            ),
        )
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be digest-shaped"
            )
        if not isinstance(
            self.local,
            DurableEvidenceReadinessReport,
        ):
            raise TypeError(
                "local must be DurableEvidenceReadinessReport"
            )
        if not isinstance(
            self.fleet,
            DurableReplicaFleetReport,
        ):
            raise TypeError(
                "fleet must be DurableReplicaFleetReport"
            )
        if not isinstance(
            self.consensus,
            DurableReplicaConsensusReport,
        ):
            raise TypeError(
                "consensus must be DurableReplicaConsensusReport"
            )
        if (
            self.history is not None
            and not isinstance(
                self.history,
                StoredDurableReplicaConsensusEpoch,
            )
        ):
            raise TypeError(
                "history must be StoredDurableReplicaConsensusEpoch"
            )
        mutations = tuple(
            self.mutations
        )
        findings = tuple(
            self.findings
        )
        if len(mutations) != len(
            set(mutations)
        ):
            raise ValueError(
                "duplicate replica readiness mutation"
            )
        object.__setattr__(
            self,
            "mutations",
            mutations,
        )
        object.__setattr__(
            self,
            "findings",
            findings,
        )

    @property
    def ready(self) -> bool:
        return (
            self.state
            is DurableReplicaReadinessState.READY
        )

    @property
    def degraded(self) -> bool:
        return (
            self.state
            is DurableReplicaReadinessState.DEGRADED
        )

    @property
    def blocked(self) -> bool:
        return self.state in {
            DurableReplicaReadinessState.BLOCKED,
            DurableReplicaReadinessState.ERROR,
        }

    @property
    def errors(self) -> int:
        return sum(
            item.severity
            is DurableReplicaReadinessSeverity.ERROR
            for item in self.findings
        )

    @property
    def warnings(self) -> int:
        return sum(
            item.severity
            is DurableReplicaReadinessSeverity.WARNING
            for item in self.findings
        )

    @property
    def repaired(self) -> bool:
        return bool(
            self.mutations
        )

    @property
    def consensus_history_generation(
        self,
    ) -> int | None:
        return (
            None
            if self.history is None
            else self.history.epoch.generation
        )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(
                include_digest=False
            )
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "state": self.state.value,
            "ready": self.ready,
            "degraded": self.degraded,
            "blocked": self.blocked,
            "errors": self.errors,
            "warnings": self.warnings,
            "repaired": self.repaired,
            "policy_digest": (
                self.policy_digest
            ),
            "local": self.local.to_dict(),
            "fleet": self.fleet.to_dict(),
            "consensus": (
                self.consensus.to_dict()
            ),
            "history": (
                None
                if self.history is None
                else self.history.to_dict()
            ),
            "consensus_history_generation": (
                self.consensus_history_generation
            ),
            "mutations": list(
                self.mutations
            ),
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableReplicaReadinessError(
    RuntimeError,
):
    pass


class DurableReplicaReadinessGuard:
    """Compose local durability with replica consensus and history."""

    def __init__(
        self,
        local: DurableEvidenceReadinessGuard,
        fleet: DurableReplicaFleet,
        consensus: DurableReplicaConsensusEvaluator,
        *,
        journal_chain,
        receipt_chain,
        history: DurableReplicaConsensusHistoryStore | None = None,
        policy: DurableReplicaReadinessPolicy | None = None,
    ) -> None:
        if not isinstance(
            local,
            DurableEvidenceReadinessGuard,
        ):
            raise TypeError(
                "local must be DurableEvidenceReadinessGuard"
            )
        if not isinstance(
            fleet,
            DurableReplicaFleet,
        ):
            raise TypeError(
                "fleet must be DurableReplicaFleet"
            )
        if not isinstance(
            consensus,
            DurableReplicaConsensusEvaluator,
        ):
            raise TypeError(
                "consensus must be DurableReplicaConsensusEvaluator"
            )
        if (
            history is not None
            and not isinstance(
                history,
                DurableReplicaConsensusHistoryStore,
            )
        ):
            raise TypeError(
                "history must be DurableReplicaConsensusHistoryStore"
            )
        self._require_chain(
            journal_chain,
            "journal_chain",
        )
        self._require_chain(
            receipt_chain,
            "receipt_chain",
        )
        self.local = local
        self.fleet = fleet
        self.consensus = consensus
        self.journal_chain = journal_chain
        self.receipt_chain = receipt_chain
        self.history = history
        self.policy = (
            policy
            or DurableReplicaReadinessPolicy()
        )
        if not isinstance(
            self.policy,
            DurableReplicaReadinessPolicy,
        ):
            raise TypeError(
                "policy must be DurableReplicaReadinessPolicy"
            )
        if (
            self.policy.require_history_store
            and self.history is None
        ):
            raise ValueError(
                "replica readiness policy requires consensus history store"
            )

    @staticmethod
    def _require_chain(
        chain,
        label: str,
    ) -> None:
        for method in (
            "head",
            "root_for_sequence",
        ):
            if not callable(
                getattr(
                    chain,
                    method,
                    None,
                )
            ):
                raise TypeError(
                    f"{label} is missing {method}"
                )

    @staticmethod
    def _finding(
        findings: list[
            DurableReplicaReadinessFinding
        ],
        severity: DurableReplicaReadinessSeverity,
        code: str,
        message: str,
        target_id: str = "",
    ) -> None:
        findings.append(
            DurableReplicaReadinessFinding(
                severity,
                code,
                message,
                target_id,
            )
        )

    def _history_status(
        self,
        consensus_report: DurableReplicaConsensusReport,
        findings: list[
            DurableReplicaReadinessFinding
        ],
    ) -> StoredDurableReplicaConsensusEpoch | None:
        if self.history is None:
            if self.policy.require_history_store:
                self._finding(
                    findings,
                    DurableReplicaReadinessSeverity.ERROR,
                    "replica_readiness.history_unavailable",
                    "consensus history store is required but unavailable",
                )
            return None

        try:
            current = self.history.current(
                consensus_report.source_id
            )
        except Exception as exc:
            self._finding(
                findings,
                DurableReplicaReadinessSeverity.ERROR,
                "replica_readiness.history_error",
                "consensus history inspection raised "
                f"{type(exc).__name__}",
            )
            return None

        if current is None:
            if self.policy.require_history_initialized:
                self._finding(
                    findings,
                    DurableReplicaReadinessSeverity.ERROR,
                    "replica_readiness.history_uninitialized",
                    "consensus history has not recorded an initial epoch",
                )
            return None

        if self.policy.require_history_current:
            try:
                return self.history.require_current(
                    consensus_report,
                    journal_chain=self.journal_chain,
                    receipt_chain=self.receipt_chain,
                )
            except DurableReplicaConsensusHistoryError as exc:
                self._finding(
                    findings,
                    DurableReplicaReadinessSeverity.ERROR,
                    "replica_readiness.history_not_current",
                    "live replica consensus conflicts with monotonic history: "
                    + str(exc)[:1600],
                )
                return None
        return current

    def _compose(
        self,
        local_report: DurableEvidenceReadinessReport,
        fleet_report: DurableReplicaFleetReport,
        consensus_report: DurableReplicaConsensusReport,
        *,
        mutations: tuple[str, ...] = (),
    ) -> DurableReplicaReadinessReport:
        findings: list[
            DurableReplicaReadinessFinding
        ] = []

        if not local_report.ready:
            self._finding(
                findings,
                (
                    DurableReplicaReadinessSeverity.ERROR
                    if self.policy.require_local_ready
                    else DurableReplicaReadinessSeverity.WARNING
                ),
                "replica_readiness.local_not_ready",
                "local durable evidence readiness is not ready",
            )

        if not fleet_report.quorum_ready:
            self._finding(
                findings,
                (
                    DurableReplicaReadinessSeverity.ERROR
                    if self.policy.require_fleet_quorum
                    else DurableReplicaReadinessSeverity.WARNING
                ),
                "replica_readiness.fleet_quorum_unready",
                (
                    fleet_report.findings[0].message
                    if fleet_report.findings
                    else "replica fleet quorum is not ready"
                ),
            )

        if not consensus_report.certifiable:
            self._finding(
                findings,
                (
                    DurableReplicaReadinessSeverity.ERROR
                    if self.policy.require_consensus
                    else DurableReplicaReadinessSeverity.WARNING
                ),
                "replica_readiness.consensus_unhealthy",
                (
                    consensus_report.findings[0].message
                    if consensus_report.findings
                    else "replica root consensus is not certifiable"
                ),
            )

        history_report = None
        if consensus_report.certifiable:
            history_report = self._history_status(
                consensus_report,
                findings,
            )

        if len(findings) > self.policy.max_findings:
            raise DurableReplicaReadinessError(
                "replica readiness finding bound exceeded"
            )

        errors = sum(
            item.severity
            is DurableReplicaReadinessSeverity.ERROR
            for item in findings
        )
        warnings = sum(
            item.severity
            is DurableReplicaReadinessSeverity.WARNING
            for item in findings
        )
        if errors:
            state = (
                DurableReplicaReadinessState.BLOCKED
            )
        elif warnings:
            state = (
                DurableReplicaReadinessState.DEGRADED
            )
        else:
            state = (
                DurableReplicaReadinessState.READY
            )
        return DurableReplicaReadinessReport(
            state,
            self.policy.digest,
            local_report,
            fleet_report,
            consensus_report,
            history_report,
            tuple(mutations),
            tuple(findings),
        )

    def inspect(
        self,
        chains: Iterable[
            tuple[str, object]
        ],
        *,
        protected_roots: (
            dict[str, tuple[str, ...]]
            | None
        ) = None,
        recovery_finalization_ids: tuple[
            str,
            ...,
        ] = (),
        compaction_workflow_ids: tuple[
            str,
            ...,
        ] = (),
    ) -> DurableReplicaReadinessReport:
        local_report = self.local.inspect(
            chains,
            protected_roots=protected_roots,
            recovery_finalization_ids=(
                recovery_finalization_ids
            ),
            compaction_workflow_ids=(
                compaction_workflow_ids
            ),
        )
        fleet_report = self.fleet.inspect()
        consensus_report = (
            self.consensus.evaluate(
                fleet_report
            )
        )
        return self._compose(
            local_report,
            fleet_report,
            consensus_report,
        )

    def reconcile(
        self,
        chains: Iterable[
            tuple[str, object]
        ],
        *,
        protected_roots: (
            dict[str, tuple[str, ...]]
            | None
        ) = None,
        recovery_finalization_ids: tuple[
            str,
            ...,
        ] = (),
        compaction_workflow_ids: tuple[
            str,
            ...,
        ] = (),
    ) -> DurableReplicaReadinessReport:
        local_report = self.local.reconcile(
            chains,
            protected_roots=protected_roots,
            recovery_finalization_ids=(
                recovery_finalization_ids
            ),
            compaction_workflow_ids=(
                compaction_workflow_ids
            ),
        )
        fleet_report = self.fleet.inspect()
        consensus_report = (
            self.consensus.evaluate(
                fleet_report
            )
        )
        mutations = list(
            local_report.mutations
        )

        if (
            local_report.ready
            and fleet_report.quorum_ready
            and consensus_report.certifiable
            and self.history is not None
            and self.policy.allow_history_record_on_reconcile
        ):
            before = self.history.current(
                consensus_report.source_id
            )
            try:
                after = self.history.record(
                    consensus_report,
                    journal_chain=self.journal_chain,
                    receipt_chain=self.receipt_chain,
                )
            except DurableReplicaConsensusHistoryError as exc:
                raise DurableReplicaReadinessError(
                    "consensus history reconciliation failed"
                ) from exc
            if (
                before is None
                or before.epoch.digest
                != after.epoch.digest
            ):
                mutations.append(
                    "consensus_history_record"
                )

        return self._compose(
            local_report,
            fleet_report,
            consensus_report,
            mutations=tuple(
                dict.fromkeys(mutations)
            ),
        )

    def require_ready(
        self,
        chains: Iterable[
            tuple[str, object]
        ],
        *,
        protected_roots: (
            dict[str, tuple[str, ...]]
            | None
        ) = None,
        recovery_finalization_ids: tuple[
            str,
            ...,
        ] = (),
        compaction_workflow_ids: tuple[
            str,
            ...,
        ] = (),
    ) -> DurableReplicaReadinessReport:
        report = self.inspect(
            chains,
            protected_roots=protected_roots,
            recovery_finalization_ids=(
                recovery_finalization_ids
            ),
            compaction_workflow_ids=(
                compaction_workflow_ids
            ),
        )
        if not report.ready:
            detail = (
                report.findings[0].message
                if report.findings
                else "replica durable readiness is not ready"
            )
            raise DurableReplicaReadinessError(
                detail
            )
        return report
