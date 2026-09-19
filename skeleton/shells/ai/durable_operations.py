"""Consolidated operational diagnostics for durable AI shell evidence.

This module does not mutate evidence, publish checkpoints, or prune data.  It
combines chain integrity, signed-checkpoint validity, retention pressure, and
required-finalization recovery health into one deterministic operator report.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Iterable

from skeleton.shells.ai.durable_compaction_maintenance import (
    DurableCompactionMaintenanceGuard,
    DurableCompactionMaintenanceReport,
)
from skeleton.shells.ai.durable_checkpoint import (
    CheckpointableEvidenceChain,
    DurableChainCheckpointStore,
    DurableCheckpointIndexHealth,
    DurableCheckpointIndexState,
    DurableCheckpointVerification,
)
from skeleton.shells.ai.durable_health import (
    DurableRecoveryHealthGuard,
    DurableRecoveryHealthReport,
)
from skeleton.shells.ai.durable_orphan_scan import (
    DurableOrphanScanReport,
    DurableOrphanScanner,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlan,
    DurableRetentionPlanner,
    DurableRetentionState,
)
from skeleton.shells.ai.durable_verification_health import (
    DurableChainVerificationHealth,
    DurableVerificationFleetGuard,
)


class DurableOperationsSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DurableChainOperationalState(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    INVALID = "invalid"


@dataclass(frozen=True)
class DurableOperationsPolicy:
    """Operational admission policy layered over retention diagnostics."""

    block_capacity_critical: bool = True
    require_checkpoint_above_warning: bool = False
    require_recovery_health: bool = False
    require_checkpoint_indexes: bool = False
    require_compaction_maintenance: bool = False
    require_orphan_scan: bool = False
    warn_on_orphan_candidates: bool = True
    max_findings: int = 512

    def __post_init__(self) -> None:
        for name in (
            "block_capacity_critical",
            "require_checkpoint_above_warning",
            "require_recovery_health",
            "require_checkpoint_indexes",
            "require_compaction_maintenance",
            "require_orphan_scan",
            "warn_on_orphan_candidates",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        if (
            isinstance(self.max_findings, bool)
            or not isinstance(self.max_findings, int)
            or self.max_findings <= 0
        ):
            raise ValueError("max_findings must be positive integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "block_capacity_critical": self.block_capacity_critical,
            "require_checkpoint_above_warning": (
                self.require_checkpoint_above_warning
            ),
            "require_recovery_health": self.require_recovery_health,
            "require_checkpoint_indexes": (
                self.require_checkpoint_indexes
            ),
            "require_compaction_maintenance": (
                self.require_compaction_maintenance
            ),
            "require_orphan_scan": self.require_orphan_scan,
            "warn_on_orphan_candidates": (
                self.warn_on_orphan_candidates
            ),
            "max_findings": self.max_findings,
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
class DurableOperationsFinding:
    severity: DurableOperationsSeverity
    code: str
    message: str
    chain_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "severity",
            DurableOperationsSeverity(self.severity),
        )
        if not self.code or len(self.code) > 128:
            raise ValueError("invalid durable operations finding code")
        if not self.message or len(self.message) > 2048:
            raise ValueError("invalid durable operations finding message")
        if len(self.chain_id) > 128:
            raise ValueError("durable operations chain_id too long")

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "chain_id": self.chain_id,
        }


@dataclass(frozen=True)
class DurableChainOperationsReport:
    chain_id: str
    state: DurableChainOperationalState
    chain_valid: bool
    sequence: int
    root_hash: str
    capacity: int
    utilization: float
    latest_checkpoint_digest: str
    checkpoint_verification: DurableCheckpointVerification | None
    retention: DurableRetentionPlan | None
    findings: tuple[DurableOperationsFinding, ...]
    verification_health: DurableChainVerificationHealth | None = None
    checkpoint_index_health: DurableCheckpointIndexHealth | None = None
    orphan_scan: DurableOrphanScanReport | None = None

    def __post_init__(self) -> None:
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError("invalid chain_id")
        object.__setattr__(
            self,
            "state",
            DurableChainOperationalState(self.state),
        )
        if not isinstance(self.chain_valid, bool):
            raise ValueError("chain_valid must be bool")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError("sequence must be non-negative integer")
        if len(self.root_hash) != 64:
            raise ValueError("root_hash must be SHA-256 hex")
        # Opaque 64-character root digest.
        if (
            isinstance(self.capacity, bool)
            or not isinstance(self.capacity, int)
            or self.capacity <= 0
        ):
            raise ValueError("capacity must be positive integer")
        if (
            isinstance(self.utilization, bool)
            or not isinstance(self.utilization, (int, float))
            or not math.isfinite(float(self.utilization))
            or float(self.utilization) < 0.0
        ):
            raise ValueError("utilization must be finite and non-negative")
        object.__setattr__(self, "utilization", float(self.utilization))
        if self.latest_checkpoint_digest:
            if len(self.latest_checkpoint_digest) != 64:
                raise ValueError(
                    "latest_checkpoint_digest must be SHA-256 hex"
                )
            # Opaque 64-character checkpoint digest.
        object.__setattr__(self, "findings", tuple(self.findings))
        if (
            self.orphan_scan is not None
            and self.orphan_scan.chain_id
            != self.chain_id
        ):
            raise ValueError(
                "orphan scan chain_id differs from operations report"
            )

    @property
    def errors(self) -> int:
        return sum(
            item.severity is DurableOperationsSeverity.ERROR
            for item in self.findings
        )

    @property
    def warnings(self) -> int:
        return sum(
            item.severity is DurableOperationsSeverity.WARNING
            for item in self.findings
        )

    @property
    def ok(self) -> bool:
        return self.errors == 0 and self.chain_valid

    @property
    def checkpoint_valid(self) -> bool | None:
        if self.checkpoint_verification is None:
            return None
        return self.checkpoint_verification.valid

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
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "state": self.state.value,
            "chain_valid": self.chain_valid,
            "sequence": self.sequence,
            "root_hash": self.root_hash,
            "capacity": self.capacity,
            "utilization": self.utilization,
            "errors": self.errors,
            "warnings": self.warnings,
            "ok": self.ok,
            "latest_checkpoint_digest": self.latest_checkpoint_digest,
            "checkpoint_valid": self.checkpoint_valid,
            "checkpoint_verification": (
                None
                if self.checkpoint_verification is None
                else self.checkpoint_verification.to_dict()
            ),
            "verification_health": (
                None
                if self.verification_health is None
                else self.verification_health.to_dict()
            ),
            "checkpoint_index_health": (
                None
                if self.checkpoint_index_health is None
                else self.checkpoint_index_health.to_dict()
            ),
            "retention": (
                None
                if self.retention is None
                else self.retention.to_dict()
            ),
            "orphan_scan": (
                None
                if self.orphan_scan is None
                else self.orphan_scan.to_dict()
            ),
            "findings": [item.to_dict() for item in self.findings],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableEvidenceOperationsReport:
    policy_digest: str
    chains: tuple[DurableChainOperationsReport, ...]
    recovery_health: DurableRecoveryHealthReport | None
    findings: tuple[DurableOperationsFinding, ...]
    compaction_maintenance: DurableCompactionMaintenanceReport | None = None

    def __post_init__(self) -> None:
        if len(self.policy_digest) != 64:
            raise ValueError("policy_digest must be SHA-256 hex")
        # Opaque 64-character policy digest.
        chains = tuple(self.chains)
        ids = tuple(item.chain_id for item in chains)
        if ids != tuple(sorted(ids)):
            raise ValueError("durable operations chains must be sorted")
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate durable operations chain_id")
        object.__setattr__(self, "chains", chains)
        object.__setattr__(self, "findings", tuple(self.findings))

    @property
    def errors(self) -> int:
        own = sum(
            item.severity is DurableOperationsSeverity.ERROR
            for item in self.findings
        )
        return own + sum(item.errors for item in self.chains)

    @property
    def warnings(self) -> int:
        own = sum(
            item.severity is DurableOperationsSeverity.WARNING
            for item in self.findings
        )
        return own + sum(item.warnings for item in self.chains)

    @property
    def allowed(self) -> bool:
        if self.errors:
            return False
        if any(not item.ok for item in self.chains):
            return False
        if (
            self.recovery_health is not None
            and not self.recovery_health.allowed
        ):
            return False
        if (
            self.compaction_maintenance is not None
            and not self.compaction_maintenance.allowed
        ):
            return False
        return True

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
        data: dict[str, object] = {
            "allowed": self.allowed,
            "errors": self.errors,
            "warnings": self.warnings,
            "policy_digest": self.policy_digest,
            "chains": [item.to_dict() for item in self.chains],
            "recovery_health": (
                None
                if self.recovery_health is None
                else self.recovery_health.to_dict()
            ),
            "compaction_maintenance": (
                None
                if self.compaction_maintenance is None
                else self.compaction_maintenance.to_dict()
            ),
            "findings": [item.to_dict() for item in self.findings],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableEvidenceOperationsError(RuntimeError):
    pass


class DurableEvidenceOperationsInspector:
    """Inspect durable chains without mutating them."""

    def __init__(
        self,
        checkpoints: DurableChainCheckpointStore,
        retention: DurableRetentionPlanner,
        *,
        recovery_health: DurableRecoveryHealthGuard | None = None,
        policy: DurableOperationsPolicy | None = None,
        verification_guard: DurableVerificationFleetGuard | None = None,
        compaction_maintenance: DurableCompactionMaintenanceGuard | None = None,
        orphan_scanner: DurableOrphanScanner | None = None,
    ) -> None:
        if not isinstance(checkpoints, DurableChainCheckpointStore):
            raise TypeError("checkpoints must be DurableChainCheckpointStore")
        if not isinstance(retention, DurableRetentionPlanner):
            raise TypeError("retention must be DurableRetentionPlanner")
        if (
            recovery_health is not None
            and not isinstance(
                recovery_health,
                DurableRecoveryHealthGuard,
            )
        ):
            raise TypeError(
                "recovery_health must be DurableRecoveryHealthGuard"
            )
        if (
            verification_guard is not None
            and not isinstance(
                verification_guard,
                DurableVerificationFleetGuard,
            )
        ):
            raise TypeError(
                "verification_guard must be DurableVerificationFleetGuard"
            )
        if (
            compaction_maintenance is not None
            and not isinstance(
                compaction_maintenance,
                DurableCompactionMaintenanceGuard,
            )
        ):
            raise TypeError(
                "compaction_maintenance must be DurableCompactionMaintenanceGuard"
            )
        if (
            orphan_scanner is not None
            and not isinstance(
                orphan_scanner,
                DurableOrphanScanner,
            )
        ):
            raise TypeError(
                "orphan_scanner must be DurableOrphanScanner"
            )
        self.checkpoints = checkpoints
        self.retention = retention
        self.recovery_health = recovery_health
        self.verification_guard = verification_guard
        self.compaction_maintenance = compaction_maintenance
        self.orphan_scanner = orphan_scanner
        self.policy = policy or DurableOperationsPolicy()

    @staticmethod
    def _capacity(chain: object) -> int:
        value = getattr(
            chain,
            "max_events",
            getattr(chain, "max_receipts", None),
        )
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            raise DurableEvidenceOperationsError(
                "durable chain capacity is unavailable"
            )
        return value

    def _inspect_chain(
        self,
        chain_id: str,
        chain: CheckpointableEvidenceChain,
        *,
        protected_roots: tuple[str, ...] = (),
    ) -> DurableChainOperationsReport:
        findings: list[DurableOperationsFinding] = []
        verification_health: DurableChainVerificationHealth | None = None
        try:
            head = chain.head()
            sequence = int(head.sequence)
            root_hash = str(head.root_hash)
            capacity = self._capacity(chain)
            utilization = sequence / capacity
            if self.verification_guard is None:
                chain_valid = bool(chain.verify())
            else:
                verification_report = self.verification_guard.inspect(
                    ((chain_id, chain),)
                )
                verification_health = verification_report.chains[0]
                chain_valid = verification_health.ok
        except Exception as exc:
            return DurableChainOperationsReport(
                chain_id,
                DurableChainOperationalState.INVALID,
                False,
                0,
                "0" * 64,
                1,
                0.0,
                "",
                None,
                None,
                (
                    DurableOperationsFinding(
                        DurableOperationsSeverity.ERROR,
                        "durable_chain.inspect_error",
                        (
                            "durable chain inspection raised "
                            f"{type(exc).__name__}"
                        ),
                        chain_id,
                    ),
                ),
                verification_health,
            )

        if not chain_valid:
            code = (
                "durable_verification.cursor_not_current"
                if verification_health is not None
                else "durable_chain.integrity"
            )
            message = (
                "signed durable verification cursor is not current"
                if verification_health is not None
                else "durable evidence chain failed integrity verification"
            )
            findings.append(
                DurableOperationsFinding(
                    DurableOperationsSeverity.ERROR,
                    code,
                    message,
                    chain_id,
                )
            )

        latest = None
        checkpoint_verification = None
        latest_digest = ""
        try:
            latest = self.checkpoints.latest(chain_id)
            if latest is not None:
                latest_digest = latest.checkpoint.digest
                checkpoint_verification = self.checkpoints.inspect(
                    latest,
                    chain,
                )
                if not checkpoint_verification.valid:
                    findings.append(
                        DurableOperationsFinding(
                            DurableOperationsSeverity.ERROR,
                            "durable_checkpoint.invalid",
                            "latest durable checkpoint failed verification",
                            chain_id,
                        )
                    )
        except Exception as exc:
            findings.append(
                DurableOperationsFinding(
                    DurableOperationsSeverity.ERROR,
                    "durable_checkpoint.inspect_error",
                    (
                        "durable checkpoint inspection raised "
                        f"{type(exc).__name__}"
                    ),
                    chain_id,
                )
            )

        checkpoint_index_health = None
        try:
            checkpoint_index_health = (
                self.checkpoints
                .inspect_lookup_indexes(
                    chain_id
                )
            )
            if (
                checkpoint_index_health.state
                is DurableCheckpointIndexState.INVALID
            ):
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.ERROR,
                        "durable_checkpoint.index_invalid",
                        (
                            "durable checkpoint exact indexes conflict "
                            "with canonical registry"
                        ),
                        chain_id,
                    )
                )
            elif (
                checkpoint_index_health.state
                is DurableCheckpointIndexState.DEGRADED
            ):
                findings.append(
                    DurableOperationsFinding(
                        (
                            DurableOperationsSeverity.ERROR
                            if self.policy.require_checkpoint_indexes
                            else DurableOperationsSeverity.WARNING
                        ),
                        "durable_checkpoint.index_repair_required",
                        (
                            "durable checkpoint exact indexes are incomplete "
                            f"({checkpoint_index_health.missing} missing)"
                        ),
                        chain_id,
                    )
                )
        except Exception as exc:
            findings.append(
                DurableOperationsFinding(
                    DurableOperationsSeverity.ERROR,
                    "durable_checkpoint.index_inspect_error",
                    (
                        "durable checkpoint index inspection raised "
                        f"{type(exc).__name__}"
                    ),
                    chain_id,
                )
            )

        retention_plan = None
        try:
            retention_plan = self.retention.plan(
                chain_id,
                chain,
                protected_roots=protected_roots,
                capacity=capacity,
                verified_head=(
                    verification_health
                    if (
                        verification_health is not None
                        and verification_health.ok
                    )
                    else None
                ),
            )
        except Exception as exc:
            findings.append(
                DurableOperationsFinding(
                    DurableOperationsSeverity.ERROR,
                    "durable_retention.inspect_error",
                    (
                        "durable retention planning raised "
                        f"{type(exc).__name__}"
                    ),
                    chain_id,
                )
            )

        orphan_scan = None
        if self.orphan_scanner is None:
            if self.policy.require_orphan_scan:
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.ERROR,
                        "durable_orphan.scan_required",
                        (
                            "durable operations policy requires "
                            "an orphan scanner"
                        ),
                        chain_id,
                    )
                )
        else:
            try:
                orphan_scan = self.orphan_scanner.scan(
                    chain_id,
                    chain,
                )
                if orphan_scan.requires_manual_review:
                    findings.append(
                        DurableOperationsFinding(
                            DurableOperationsSeverity.ERROR,
                            "durable_orphan.manual_review",
                            (
                                "durable orphan scan found authority "
                                "conflicts, corrupt records, or truncation"
                            ),
                            chain_id,
                        )
                    )
                elif (
                    orphan_scan.orphan_candidates
                    and self.policy.warn_on_orphan_candidates
                ):
                    findings.append(
                        DurableOperationsFinding(
                            DurableOperationsSeverity.WARNING,
                            "durable_orphan.candidates",
                            (
                                "durable chain has "
                                f"{orphan_scan.orphan_candidates} "
                                "unreachable orphan candidate(s)"
                            ),
                            chain_id,
                        )
                    )
            except Exception as exc:
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.ERROR,
                        "durable_orphan.scan_error",
                        (
                            "durable orphan scan raised "
                            f"{type(exc).__name__}"
                        ),
                        chain_id,
                    )
                )

        if retention_plan is not None:
            if (
                retention_plan.state
                is DurableRetentionState.CAPACITY_CRITICAL
            ):
                findings.append(
                    DurableOperationsFinding(
                        (
                            DurableOperationsSeverity.ERROR
                            if self.policy.block_capacity_critical
                            else DurableOperationsSeverity.WARNING
                        ),
                        "durable_retention.capacity_critical",
                        "durable evidence chain is at critical capacity utilization",
                        chain_id,
                    )
                )
            elif (
                retention_plan.state
                is DurableRetentionState.CHECKPOINT_REQUIRED
            ):
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.WARNING,
                        "durable_retention.checkpoint_required",
                        "durable evidence chain requires a signed archival checkpoint",
                        chain_id,
                    )
                )
            elif (
                retention_plan.state
                is DurableRetentionState.ARCHIVE_RECOMMENDED
            ):
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.WARNING,
                        "durable_retention.archive_recommended",
                        "durable evidence chain has a signed prefix recommended for archival",
                        chain_id,
                    )
                )

            if (
                self.policy.require_checkpoint_above_warning
                and utilization
                >= self.retention.policy.warning_utilization
                and latest is None
            ):
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.ERROR,
                        "durable_checkpoint.required_above_warning",
                        (
                            "capacity warning threshold requires at least "
                            "one signed durable checkpoint"
                        ),
                        chain_id,
                    )
                )

        if not chain_valid or any(
            item.severity is DurableOperationsSeverity.ERROR
            for item in findings
        ):
            state = DurableChainOperationalState.INVALID
        elif (
            retention_plan is not None
            and retention_plan.state
            is DurableRetentionState.CAPACITY_CRITICAL
        ):
            state = DurableChainOperationalState.CRITICAL
        elif findings:
            state = DurableChainOperationalState.WARNING
        else:
            state = DurableChainOperationalState.HEALTHY

        return DurableChainOperationsReport(
            chain_id,
            state,
            chain_valid,
            sequence,
            root_hash,
            capacity,
            utilization,
            latest_digest,
            checkpoint_verification,
            retention_plan,
            tuple(findings),
            verification_health,
            checkpoint_index_health,
            orphan_scan,
        )

    def inspect(
        self,
        chains: Iterable[
            tuple[str, CheckpointableEvidenceChain]
        ],
        *,
        protected_roots: dict[str, tuple[str, ...]] | None = None,
        recovery_finalization_ids: tuple[str, ...] = (),
        compaction_workflow_ids: tuple[str, ...] = (),
    ) -> DurableEvidenceOperationsReport:
        entries = tuple(chains)
        if not entries:
            raise ValueError("at least one durable chain is required")
        ids = tuple(item[0] for item in entries)
        if any(
            not isinstance(item, str)
            or not item
            or len(item) > 128
            for item in ids
        ):
            raise ValueError("invalid durable chain_id")
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate durable chain_id")
        protected_roots = dict(protected_roots or {})
        unknown = set(protected_roots) - set(ids)
        if unknown:
            raise ValueError(
                "protected roots reference unknown durable chain"
            )

        reports = tuple(
            self._inspect_chain(
                chain_id,
                chain,
                protected_roots=tuple(
                    protected_roots.get(chain_id, ())
                ),
            )
            for chain_id, chain in sorted(
                entries,
                key=lambda item: item[0],
            )
        )

        findings: list[DurableOperationsFinding] = []
        recovery_report = None
        if self.recovery_health is None:
            if self.policy.require_recovery_health:
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.ERROR,
                        "durable_recovery.health_required",
                        (
                            "durable operations policy requires "
                            "a recovery health guard"
                        ),
                    )
                )
            elif recovery_finalization_ids:
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.ERROR,
                        "durable_recovery.guard_missing",
                        (
                            "recovery finalization ids were supplied "
                            "without a recovery health guard"
                        ),
                    )
                )
        else:
            recovery_report = self.recovery_health.inspect(
                recovery_finalization_ids
            )
            if not recovery_report.allowed:
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.ERROR,
                        "durable_recovery.health_denied",
                        "durable recovery health gate denied admission",
                    )
                )
            elif recovery_report.warnings:
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.WARNING,
                        "durable_recovery.health_warning",
                        (
                            "durable recovery health contains "
                            f"{recovery_report.warnings} warning(s)"
                        ),
                    )
                )

        compaction_report = None
        if self.compaction_maintenance is None:
            if self.policy.require_compaction_maintenance:
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.ERROR,
                        "durable_compaction.maintenance_required",
                        (
                            "durable operations policy requires "
                            "compaction maintenance health"
                        ),
                    )
                )
            elif compaction_workflow_ids:
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.ERROR,
                        "durable_compaction.guard_missing",
                        (
                            "compaction workflow ids were supplied "
                            "without a compaction maintenance guard"
                        ),
                    )
                )
        else:
            try:
                compaction_report = (
                    self.compaction_maintenance.inspect(
                        compaction_workflow_ids,
                        ids,
                    )
                )
                if not compaction_report.allowed:
                    findings.append(
                        DurableOperationsFinding(
                            DurableOperationsSeverity.ERROR,
                            "durable_compaction.maintenance_denied",
                            (
                                "durable compaction maintenance "
                                "gate denied admission"
                            ),
                        )
                    )
                elif compaction_report.warnings:
                    findings.append(
                        DurableOperationsFinding(
                            DurableOperationsSeverity.WARNING,
                            "durable_compaction.maintenance_warning",
                            (
                                "durable compaction maintenance "
                                f"reported {compaction_report.warnings} warning(s)"
                            ),
                        )
                    )
            except Exception as exc:
                findings.append(
                    DurableOperationsFinding(
                        DurableOperationsSeverity.ERROR,
                        "durable_compaction.maintenance_error",
                        (
                            "durable compaction maintenance "
                            "inspection raised "
                            f"{type(exc).__name__}"
                        ),
                    )
                )

        if len(findings) + sum(
            len(item.findings) for item in reports
        ) > self.policy.max_findings:
            raise DurableEvidenceOperationsError(
                "durable operations finding bound exceeded"
            )

        return DurableEvidenceOperationsReport(
            self.policy.digest,
            reports,
            recovery_report,
            tuple(findings),
            compaction_report,
        )

    def require(
        self,
        chains: Iterable[
            tuple[str, CheckpointableEvidenceChain]
        ],
        *,
        protected_roots: dict[str, tuple[str, ...]] | None = None,
        recovery_finalization_ids: tuple[str, ...] = (),
        compaction_workflow_ids: tuple[str, ...] = (),
    ) -> DurableEvidenceOperationsReport:
        report = self.inspect(
            chains,
            protected_roots=protected_roots,
            recovery_finalization_ids=recovery_finalization_ids,
            compaction_workflow_ids=compaction_workflow_ids,
        )
        if not report.allowed:
            all_findings = list(report.findings)
            for chain in report.chains:
                all_findings.extend(chain.findings)
            detail = (
                all_findings[0].message
                if all_findings
                else "durable evidence operations denied admission"
            )
            raise DurableEvidenceOperationsError(detail)
        return report
