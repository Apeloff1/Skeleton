"""Unified startup/readiness gate for the durable AI shell evidence plane.

The durable subsystem has intentionally separate authorities: chain integrity,
checkpoint/retention operations, signed verification cursors, sequence locator
indexes, and finalization recovery health.  This module composes those existing
controls into one deterministic worker-admission report without weakening any
component's authority semantics.

Inspection is non-mutating.  Reconciliation is explicit and is limited to
safe, already-supported maintenance actions: repairing missing secondary
sequence indexes and publishing fresh full verification cursors.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

from skeleton.shells.ai.durable_operations import (
    DurableEvidenceOperationsInspector,
    DurableEvidenceOperationsReport,
)
from skeleton.shells.ai.durable_sequence_index import (
    DurableSequenceIndexFleetReport,
    DurableSequenceIndexOperator,
)
from skeleton.shells.ai.durable_verification_operator import (
    DurableVerificationOperator,
    DurableVerificationOperatorReport,
    DurableVerificationRefreshReport,
)


def _stable_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


class DurableEvidenceReadinessState(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    ERROR = "error"


class DurableEvidenceReadinessSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class DurableEvidenceReadinessPolicy:
    require_operations_allowed: bool = True
    require_sequence_indexes: bool = True
    require_verification_current: bool = True
    allow_sequence_index_repair: bool = True
    allow_verification_refresh: bool = True
    require_nonempty_chains: bool = True
    max_chains: int = 32
    max_findings: int = 256

    def __post_init__(self) -> None:
        for name in (
            "require_operations_allowed",
            "require_sequence_indexes",
            "require_verification_current",
            "allow_sequence_index_repair",
            "allow_verification_refresh",
            "require_nonempty_chains",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")
        for name in ("max_chains", "max_findings"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(f"{name} must be positive integer")

    @property
    def digest(self) -> str:
        return _stable_digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "require_operations_allowed": self.require_operations_allowed,
            "require_sequence_indexes": self.require_sequence_indexes,
            "require_verification_current": self.require_verification_current,
            "allow_sequence_index_repair": (
                self.allow_sequence_index_repair
            ),
            "allow_verification_refresh": (
                self.allow_verification_refresh
            ),
            "require_nonempty_chains": self.require_nonempty_chains,
            "max_chains": self.max_chains,
            "max_findings": self.max_findings,
        }


@dataclass(frozen=True)
class DurableEvidenceReadinessFinding:
    severity: DurableEvidenceReadinessSeverity
    code: str
    message: str
    chain_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "severity",
            DurableEvidenceReadinessSeverity(self.severity),
        )
        if not self.code or len(self.code) > 128:
            raise ValueError("invalid readiness finding code")
        if not self.message or len(self.message) > 2048:
            raise ValueError("invalid readiness finding message")
        if len(self.chain_id) > 128:
            raise ValueError("readiness finding chain_id too long")

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "chain_id": self.chain_id,
        }


@dataclass(frozen=True)
class DurableEvidenceReadinessReport:
    state: DurableEvidenceReadinessState
    policy_digest: str
    chain_ids: tuple[str, ...]
    operations: DurableEvidenceOperationsReport | None
    sequence_indexes: DurableSequenceIndexFleetReport | None
    verification: DurableVerificationOperatorReport | None
    verification_refresh: DurableVerificationRefreshReport | None
    mutations: tuple[str, ...]
    findings: tuple[DurableEvidenceReadinessFinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "state",
            DurableEvidenceReadinessState(self.state),
        )
        if len(self.policy_digest) != 64:
            raise ValueError("policy_digest must be digest-shaped")
        chain_ids = tuple(self.chain_ids)
        if chain_ids != tuple(sorted(chain_ids)):
            raise ValueError("readiness chain_ids must be sorted")
        if len(chain_ids) != len(set(chain_ids)):
            raise ValueError("duplicate readiness chain_id")
        if any(
            not value or len(value) > 128
            for value in chain_ids
        ):
            raise ValueError("invalid readiness chain_id")
        object.__setattr__(self, "chain_ids", chain_ids)
        object.__setattr__(self, "mutations", tuple(self.mutations))
        object.__setattr__(self, "findings", tuple(self.findings))
        if len(set(self.mutations)) != len(self.mutations):
            raise ValueError("duplicate readiness mutation")

    @property
    def ready(self) -> bool:
        return self.state is DurableEvidenceReadinessState.READY

    @property
    def degraded(self) -> bool:
        return self.state is DurableEvidenceReadinessState.DEGRADED

    @property
    def blocked(self) -> bool:
        return self.state in {
            DurableEvidenceReadinessState.BLOCKED,
            DurableEvidenceReadinessState.ERROR,
        }

    @property
    def errors(self) -> int:
        return sum(
            item.severity
            is DurableEvidenceReadinessSeverity.ERROR
            for item in self.findings
        )

    @property
    def warnings(self) -> int:
        return sum(
            item.severity
            is DurableEvidenceReadinessSeverity.WARNING
            for item in self.findings
        )

    @property
    def repaired(self) -> bool:
        return bool(self.mutations)

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(include_digest=False)
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
            "policy_digest": self.policy_digest,
            "chain_ids": list(self.chain_ids),
            "operations": (
                None
                if self.operations is None
                else self.operations.to_dict()
            ),
            "sequence_indexes": (
                None
                if self.sequence_indexes is None
                else self.sequence_indexes.to_dict()
            ),
            "verification": (
                None
                if self.verification is None
                else self.verification.to_dict()
            ),
            "verification_refresh": (
                None
                if self.verification_refresh is None
                else self.verification_refresh.to_dict()
            ),
            "mutations": list(self.mutations),
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableEvidenceReadinessError(RuntimeError):
    pass


class DurableEvidenceReadinessGuard:
    """Compose durable subsystem health into one admission decision."""

    def __init__(
        self,
        operations: DurableEvidenceOperationsInspector,
        sequence_indexes: DurableSequenceIndexOperator,
        verification: DurableVerificationOperator,
        policy: DurableEvidenceReadinessPolicy | None = None,
    ) -> None:
        if not isinstance(
            operations,
            DurableEvidenceOperationsInspector,
        ):
            raise TypeError(
                "operations must be DurableEvidenceOperationsInspector"
            )
        if not isinstance(
            sequence_indexes,
            DurableSequenceIndexOperator,
        ):
            raise TypeError(
                "sequence_indexes must be DurableSequenceIndexOperator"
            )
        if not isinstance(
            verification,
            DurableVerificationOperator,
        ):
            raise TypeError(
                "verification must be DurableVerificationOperator"
            )
        self.operations = operations
        self.sequence_indexes = sequence_indexes
        self.verification = verification
        self.policy = (
            policy or DurableEvidenceReadinessPolicy()
        )
        if not isinstance(
            self.policy,
            DurableEvidenceReadinessPolicy,
        ):
            raise TypeError(
                "policy must be DurableEvidenceReadinessPolicy"
            )

    def _entries(
        self,
        chains: Iterable[tuple[str, object]],
    ) -> tuple[tuple[str, object], ...]:
        entries = tuple(chains)
        if self.policy.require_nonempty_chains and not entries:
            raise ValueError(
                "at least one durable readiness chain is required"
            )
        if len(entries) > self.policy.max_chains:
            raise DurableEvidenceReadinessError(
                "durable readiness chain bound exceeded"
            )
        normalized: list[tuple[str, object]] = []
        seen: set[str] = set()
        for item in entries:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
            ):
                raise ValueError(
                    "readiness chains must be (chain_id, chain) pairs"
                )
            chain_id, chain = item
            if (
                not isinstance(chain_id, str)
                or not chain_id
                or len(chain_id) > 128
            ):
                raise ValueError(
                    "invalid durable readiness chain_id"
                )
            if chain_id in seen:
                raise ValueError(
                    "duplicate durable readiness chain_id"
                )
            seen.add(chain_id)
            normalized.append((chain_id, chain))
        return tuple(
            sorted(
                normalized,
                key=lambda item: item[0],
            )
        )

    @staticmethod
    def _finding(
        findings: list[DurableEvidenceReadinessFinding],
        severity: DurableEvidenceReadinessSeverity,
        code: str,
        message: str,
        chain_id: str = "",
    ) -> None:
        findings.append(
            DurableEvidenceReadinessFinding(
                severity,
                code,
                message,
                chain_id,
            )
        )

    def _evaluate(
        self,
        entries: tuple[tuple[str, object], ...],
        *,
        protected_roots: dict[str, tuple[str, ...]] | None,
        recovery_finalization_ids: tuple[str, ...],
        compaction_workflow_ids: tuple[str, ...],
        sequence_report: DurableSequenceIndexFleetReport | None = None,
        verification_report: DurableVerificationOperatorReport | None = None,
        verification_refresh: DurableVerificationRefreshReport | None = None,
        mutations: tuple[str, ...] = (),
    ) -> DurableEvidenceReadinessReport:
        findings: list[
            DurableEvidenceReadinessFinding
        ] = []
        chain_ids = tuple(
            chain_id
            for chain_id, _ in entries
        )

        operations_report = None
        try:
            operations_report = self.operations.inspect(
                entries,
                protected_roots=protected_roots,
                recovery_finalization_ids=(
                    recovery_finalization_ids
                ),
                compaction_workflow_ids=(
                    compaction_workflow_ids
                ),
            )
            if not operations_report.allowed:
                self._finding(
                    findings,
                    (
                        DurableEvidenceReadinessSeverity.ERROR
                        if self.policy.require_operations_allowed
                        else DurableEvidenceReadinessSeverity.WARNING
                    ),
                    "readiness.operations_denied",
                    "durable evidence operations gate denied admission",
                )
            elif operations_report.warnings:
                self._finding(
                    findings,
                    DurableEvidenceReadinessSeverity.WARNING,
                    "readiness.operations_warning",
                    (
                        "durable evidence operations reported "
                        f"{operations_report.warnings} warning(s)"
                    ),
                )
        except Exception as exc:
            self._finding(
                findings,
                DurableEvidenceReadinessSeverity.ERROR,
                "readiness.operations_error",
                (
                    "durable evidence operations inspection raised "
                    f"{type(exc).__name__}"
                ),
            )

        if sequence_report is None:
            try:
                sequence_report = (
                    self.sequence_indexes.inspect(
                        dict(entries)
                    )
                )
            except Exception as exc:
                self._finding(
                    findings,
                    DurableEvidenceReadinessSeverity.ERROR,
                    "readiness.sequence_index_error",
                    (
                        "durable sequence-index inspection raised "
                        f"{type(exc).__name__}"
                    ),
                )
        if sequence_report is not None and not sequence_report.ok:
            self._finding(
                findings,
                (
                    DurableEvidenceReadinessSeverity.ERROR
                    if self.policy.require_sequence_indexes
                    else DurableEvidenceReadinessSeverity.WARNING
                ),
                "readiness.sequence_indexes_unhealthy",
                (
                    "durable sequence indexes are not healthy: "
                    f"missing={sequence_report.missing}, "
                    f"corrupt={sequence_report.corrupt}, "
                    f"bounded_out={sequence_report.bounded_out}, "
                    f"errors={sequence_report.errors}"
                ),
            )

        if verification_report is None:
            try:
                verification_report = (
                    self.verification.audit(entries)
                )
            except Exception as exc:
                self._finding(
                    findings,
                    DurableEvidenceReadinessSeverity.ERROR,
                    "readiness.verification_error",
                    (
                        "durable verification cursor audit raised "
                        f"{type(exc).__name__}"
                    ),
                )
        if (
            verification_report is not None
            and not verification_report.ok
        ):
            self._finding(
                findings,
                (
                    DurableEvidenceReadinessSeverity.ERROR
                    if self.policy.require_verification_current
                    else DurableEvidenceReadinessSeverity.WARNING
                ),
                "readiness.verification_not_current",
                (
                    "durable verification cursor fleet is not current"
                ),
            )

        if len(findings) > self.policy.max_findings:
            raise DurableEvidenceReadinessError(
                "durable readiness finding bound exceeded"
            )

        errors = sum(
            item.severity
            is DurableEvidenceReadinessSeverity.ERROR
            for item in findings
        )
        warnings = sum(
            item.severity
            is DurableEvidenceReadinessSeverity.WARNING
            for item in findings
        )
        if errors:
            state = DurableEvidenceReadinessState.BLOCKED
        elif warnings:
            state = DurableEvidenceReadinessState.DEGRADED
        else:
            state = DurableEvidenceReadinessState.READY

        return DurableEvidenceReadinessReport(
            state,
            self.policy.digest,
            chain_ids,
            operations_report,
            sequence_report,
            verification_report,
            verification_refresh,
            mutations,
            tuple(findings),
        )

    def inspect(
        self,
        chains: Iterable[tuple[str, object]],
        *,
        protected_roots: dict[str, tuple[str, ...]] | None = None,
        recovery_finalization_ids: tuple[str, ...] = (),
        compaction_workflow_ids: tuple[str, ...] = (),
    ) -> DurableEvidenceReadinessReport:
        entries = self._entries(chains)
        return self._evaluate(
            entries,
            protected_roots=protected_roots,
            recovery_finalization_ids=recovery_finalization_ids,
            compaction_workflow_ids=compaction_workflow_ids,
        )

    def reconcile(
        self,
        chains: Iterable[tuple[str, object]],
        *,
        protected_roots: dict[str, tuple[str, ...]] | None = None,
        recovery_finalization_ids: tuple[str, ...] = (),
    ) -> DurableEvidenceReadinessReport:
        entries = self._entries(chains)
        mutations: list[str] = []

        sequence_report = self.sequence_indexes.inspect(
            dict(entries)
        )
        if (
            not sequence_report.ok
            and sequence_report.missing
            and not sequence_report.corrupt
            and not sequence_report.errors
            and not sequence_report.bounded_out
        ):
            if not self.policy.allow_sequence_index_repair:
                raise DurableEvidenceReadinessError(
                    "sequence-index repair required but disabled by readiness policy"
                )
            sequence_report = self.sequence_indexes.repair(
                dict(entries)
            )
            mutations.append(
                "sequence_index_repair"
            )

        verification_report = self.verification.audit(
            entries
        )
        verification_refresh = None
        if not verification_report.ok:
            if not self.policy.allow_verification_refresh:
                raise DurableEvidenceReadinessError(
                    "verification refresh required but disabled by readiness policy"
                )
            verification_refresh = (
                self.verification.force_full_refresh(
                    entries
                )
            )
            verification_report = (
                verification_refresh.after
            )
            mutations.append(
                "verification_full_refresh"
            )

        return self._evaluate(
            entries,
            protected_roots=protected_roots,
            recovery_finalization_ids=recovery_finalization_ids,
            compaction_workflow_ids=compaction_workflow_ids,
            sequence_report=sequence_report,
            verification_report=verification_report,
            verification_refresh=verification_refresh,
            mutations=tuple(mutations),
        )

    def require_ready(
        self,
        chains: Iterable[tuple[str, object]],
        *,
        protected_roots: dict[str, tuple[str, ...]] | None = None,
        recovery_finalization_ids: tuple[str, ...] = (),
        compaction_workflow_ids: tuple[str, ...] = (),
        reconcile: bool = False,
    ) -> DurableEvidenceReadinessReport:
        report = (
            self.reconcile(
                chains,
                protected_roots=protected_roots,
                recovery_finalization_ids=recovery_finalization_ids,
                compaction_workflow_ids=compaction_workflow_ids,
            )
            if reconcile
            else self.inspect(
                chains,
                protected_roots=protected_roots,
                recovery_finalization_ids=recovery_finalization_ids,
                compaction_workflow_ids=compaction_workflow_ids,
            )
        )
        if not report.ready:
            detail = (
                report.findings[0].message
                if report.findings
                else (
                    "durable evidence readiness is "
                    f"{report.state.value}"
                )
            )
            raise DurableEvidenceReadinessError(
                detail
            )
        return report
