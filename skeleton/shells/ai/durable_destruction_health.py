"""Health and admission gating for durable destruction evidence.

Destructive maintenance is only as trustworthy as the audit trail proving what
was removed. This module converts per-chain destruction-ledger verification and
secondary-index health into a bounded fleet decision suitable for maintenance
admission.

Inspection is read-only. Repair is explicit and limited to reconstructing
missing secondary operation indexes from already committed signed history. It
never creates destruction records or mutates evidence chains.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

from skeleton.shells.ai.durable_destruction import (
    DurableDestructionIndexHealth,
    DurableDestructionIndexState,
    DurableDestructionKind,
    DurableDestructionLedger,
    DurableDestructionVerification,
)


class DurableDestructionHealthSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class DurableDestructionHealthPolicy:
    max_chains: int = 32
    max_findings: int = 512
    max_records_per_chain: int = 100_000
    warn_records_at_fraction: float = 0.80
    require_nonempty: bool = False
    require_healthy_indexes: bool = True
    require_post_verified: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_chains",
            "max_findings",
            "max_records_per_chain",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive integer"
                )
        value = self.warn_records_at_fraction
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0.0 < float(value) <= 1.0
        ):
            raise ValueError(
                "warn_records_at_fraction must be in (0, 1]"
            )
        object.__setattr__(
            self,
            "warn_records_at_fraction",
            float(value),
        )
        for name in (
            "require_nonempty",
            "require_healthy_indexes",
            "require_post_verified",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "max_chains": self.max_chains,
            "max_findings": self.max_findings,
            "max_records_per_chain": (
                self.max_records_per_chain
            ),
            "warn_records_at_fraction": (
                self.warn_records_at_fraction
            ),
            "require_nonempty": self.require_nonempty,
            "require_healthy_indexes": (
                self.require_healthy_indexes
            ),
            "require_post_verified": (
                self.require_post_verified
            ),
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
class DurableDestructionHealthFinding:
    severity: DurableDestructionHealthSeverity
    code: str
    message: str
    chain_id: str = ""
    record_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "severity",
            DurableDestructionHealthSeverity(
                self.severity
            ),
        )
        if not self.code or len(self.code) > 128:
            raise ValueError(
                "invalid destruction health code"
            )
        if not self.message or len(self.message) > 2048:
            raise ValueError(
                "invalid destruction health message"
            )
        if len(self.chain_id) > 128:
            raise ValueError(
                "destruction health chain_id too long"
            )
        if self.record_id and len(self.record_id) != 64:
            raise ValueError(
                "destruction health record_id must be digest"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "chain_id": self.chain_id,
            "record_id": self.record_id,
        }


@dataclass(frozen=True)
class DurableDestructionChainHealth:
    chain_id: str
    verification: DurableDestructionVerification
    index_health: DurableDestructionIndexHealth
    records: int
    pruning_records: int
    orphan_gc_records: int
    verified_records: int
    latest_record_id: str
    utilization: float
    findings: tuple[
        DurableDestructionHealthFinding,
        ...,
    ]

    def __post_init__(self) -> None:
        if not self.chain_id or len(self.chain_id) > 128:
            raise ValueError(
                "invalid destruction health chain_id"
            )
        if self.verification.chain_id != self.chain_id:
            raise ValueError(
                "destruction verification chain mismatch"
            )
        if self.index_health.chain_id != self.chain_id:
            raise ValueError(
                "destruction index health chain mismatch"
            )
        for name in (
            "records",
            "pruning_records",
            "orphan_gc_records",
            "verified_records",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        if (
            self.pruning_records
            + self.orphan_gc_records
            != self.records
        ):
            raise ValueError(
                "destruction kind counts differ from records"
            )
        if self.verified_records > self.records:
            raise ValueError(
                "verified destruction count exceeds records"
            )
        if self.latest_record_id and len(
            self.latest_record_id
        ) != 64:
            raise ValueError(
                "latest_record_id must be digest"
            )
        if (
            isinstance(self.utilization, bool)
            or not isinstance(
                self.utilization,
                (int, float),
            )
            or not 0.0 <= float(
                self.utilization
            )
        ):
            raise ValueError(
                "utilization must be non-negative"
            )
        object.__setattr__(
            self,
            "utilization",
            float(self.utilization),
        )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )
        if any(
            item.chain_id
            and item.chain_id != self.chain_id
            for item in self.findings
        ):
            raise ValueError(
                "destruction finding chain mismatch"
            )

    @property
    def errors(self) -> int:
        return sum(
            item.severity
            is DurableDestructionHealthSeverity.ERROR
            for item in self.findings
        )

    @property
    def warnings(self) -> int:
        return sum(
            item.severity
            is DurableDestructionHealthSeverity.WARNING
            for item in self.findings
        )

    @property
    def ok(self) -> bool:
        return (
            self.verification.ok
            and self.errors == 0
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False
            ),
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
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "records": self.records,
            "pruning_records": (
                self.pruning_records
            ),
            "orphan_gc_records": (
                self.orphan_gc_records
            ),
            "verified_records": (
                self.verified_records
            ),
            "latest_record_id": (
                self.latest_record_id
            ),
            "utilization": self.utilization,
            "verification": (
                self.verification.to_dict()
            ),
            "index_health": (
                self.index_health.to_dict()
            ),
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableDestructionFleetHealth:
    policy_digest: str
    chains: tuple[
        DurableDestructionChainHealth,
        ...,
    ]
    findings: tuple[
        DurableDestructionHealthFinding,
        ...,
    ]

    def __post_init__(self) -> None:
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be digest"
            )
        object.__setattr__(
            self,
            "chains",
            tuple(self.chains),
        )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )
        ids = tuple(
            item.chain_id
            for item in self.chains
        )
        if ids != tuple(sorted(ids)):
            raise ValueError(
                "destruction health chains must be sorted"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate destruction health chain"
            )

    @property
    def errors(self) -> int:
        return sum(
            item.errors
            for item in self.chains
        ) + sum(
            item.severity
            is DurableDestructionHealthSeverity.ERROR
            for item in self.findings
        )

    @property
    def warnings(self) -> int:
        return sum(
            item.warnings
            for item in self.chains
        ) + sum(
            item.severity
            is DurableDestructionHealthSeverity.WARNING
            for item in self.findings
        )

    @property
    def records(self) -> int:
        return sum(
            item.records
            for item in self.chains
        )

    @property
    def allowed(self) -> bool:
        return (
            self.errors == 0
            and all(
                item.ok
                for item in self.chains
            )
        )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(
                include_digest=False
            ),
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
            "records": self.records,
            "policy_digest": (
                self.policy_digest
            ),
            "chains": [
                item.to_dict()
                for item in self.chains
            ],
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class DurableDestructionHealthError(RuntimeError):
    pass


class DurableDestructionHealthGuard:
    """Inspect and gate destruction-ledger integrity across bounded chains."""

    def __init__(
        self,
        ledger: DurableDestructionLedger,
        *,
        policy: DurableDestructionHealthPolicy | None = None,
    ) -> None:
        if not isinstance(
            ledger,
            DurableDestructionLedger,
        ):
            raise TypeError(
                "ledger must be DurableDestructionLedger"
            )
        self.ledger = ledger
        self.policy = (
            policy
            or DurableDestructionHealthPolicy()
        )
        if not isinstance(
            self.policy,
            DurableDestructionHealthPolicy,
        ):
            raise TypeError(
                "policy must be DurableDestructionHealthPolicy"
            )

    def _ids(
        self,
        chain_ids: Iterable[str],
    ) -> tuple[str, ...]:
        ids = tuple(
            sorted(
                str(item)
                for item in chain_ids
            )
        )
        if len(ids) > self.policy.max_chains:
            raise DurableDestructionHealthError(
                "destruction health chain bound exceeded"
            )
        if len(ids) != len(set(ids)):
            raise DurableDestructionHealthError(
                "duplicate destruction health chain"
            )
        if any(
            not item or len(item) > 128
            for item in ids
        ):
            raise ValueError(
                "invalid destruction health chain_id"
            )
        return ids

    def _inspect_chain(
        self,
        chain_id: str,
    ) -> DurableDestructionChainHealth:
        findings: list[
            DurableDestructionHealthFinding
        ] = []
        try:
            verification = (
                self.ledger.verify(
                    chain_id
                )
            )
        except Exception as exc:
            verification = DurableDestructionVerification(
                chain_id,
                0,
                0,
                False,
                False,
                False,
                (
                    "ledger verification raised "
                    f"{type(exc).__name__}",
                ),
            )
        try:
            index_health = (
                self.ledger
                .inspect_operation_indexes(
                    chain_id
                )
            )
        except Exception as exc:
            index_health = DurableDestructionIndexHealth(
                chain_id,
                0,
                0,
                0,
                0,
                0,
                (),
            )
            findings.append(
                DurableDestructionHealthFinding(
                    DurableDestructionHealthSeverity.ERROR,
                    "destruction.index.inspect_failed",
                    "destruction index inspection failed: "
                    f"{type(exc).__name__}",
                    chain_id,
                )
            )

        try:
            records = self.ledger.snapshot(
                chain_id
            )
        except Exception as exc:
            records = ()
            findings.append(
                DurableDestructionHealthFinding(
                    DurableDestructionHealthSeverity.ERROR,
                    "destruction.snapshot.failed",
                    "destruction snapshot failed: "
                    f"{type(exc).__name__}",
                    chain_id,
                )
            )

        if not verification.signatures_valid:
            findings.append(
                DurableDestructionHealthFinding(
                    DurableDestructionHealthSeverity.ERROR,
                    "destruction.signature.invalid",
                    "one or more destruction signatures are invalid",
                    chain_id,
                )
            )
        if not verification.linkage_valid:
            findings.append(
                DurableDestructionHealthFinding(
                    DurableDestructionHealthSeverity.ERROR,
                    "destruction.linkage.invalid",
                    "destruction record linkage is invalid",
                    chain_id,
                )
            )
        if (
            self.policy.require_healthy_indexes
            and not index_health.healthy
        ):
            findings.append(
                DurableDestructionHealthFinding(
                    DurableDestructionHealthSeverity.ERROR,
                    "destruction.index.unhealthy",
                    "destruction operation indexes are unhealthy",
                    chain_id,
                )
            )
        elif not index_health.healthy:
            findings.append(
                DurableDestructionHealthFinding(
                    DurableDestructionHealthSeverity.WARNING,
                    "destruction.index.unhealthy",
                    "destruction operation indexes are unhealthy",
                    chain_id,
                )
            )

        if (
            self.policy.require_nonempty
            and not records
        ):
            findings.append(
                DurableDestructionHealthFinding(
                    DurableDestructionHealthSeverity.ERROR,
                    "destruction.history.empty",
                    "destruction history is required but empty",
                    chain_id,
                )
            )

        unverified = tuple(
            item
            for item in records
            if not item.record.post_verified
        )
        if unverified:
            severity = (
                DurableDestructionHealthSeverity.ERROR
                if self.policy.require_post_verified
                else DurableDestructionHealthSeverity.WARNING
            )
            for item in unverified:
                findings.append(
                    DurableDestructionHealthFinding(
                        severity,
                        "destruction.post_verify.missing",
                        "destruction record lacks successful post-delete verification",
                        chain_id,
                        item.record_id,
                    )
                )

        if len(records) > self.policy.max_records_per_chain:
            findings.append(
                DurableDestructionHealthFinding(
                    DurableDestructionHealthSeverity.ERROR,
                    "destruction.records.bound_exceeded",
                    "destruction history exceeds health-policy record bound",
                    chain_id,
                )
            )
        elif (
            len(records)
            >= int(
                self.policy.max_records_per_chain
                * self.policy.warn_records_at_fraction
            )
            and records
        ):
            findings.append(
                DurableDestructionHealthFinding(
                    DurableDestructionHealthSeverity.WARNING,
                    "destruction.records.pressure",
                    "destruction history is approaching configured record bound",
                    chain_id,
                )
            )

        if verification.issues:
            for issue in verification.issues:
                findings.append(
                    DurableDestructionHealthFinding(
                        DurableDestructionHealthSeverity.ERROR,
                        "destruction.verify.issue",
                        issue,
                        chain_id,
                    )
                )

        if len(findings) > self.policy.max_findings:
            findings = findings[
                : self.policy.max_findings
            ]
            findings.append(
                DurableDestructionHealthFinding(
                    DurableDestructionHealthSeverity.ERROR,
                    "destruction.findings.truncated",
                    "destruction health findings exceeded configured bound",
                    chain_id,
                )
            )

        pruning = sum(
            item.record.operation_kind
            is DurableDestructionKind.PRUNING
            for item in records
        )
        orphan_gc = sum(
            item.record.operation_kind
            is DurableDestructionKind.ORPHAN_GC
            for item in records
        )
        verified = sum(
            item.record.post_verified
            for item in records
        )
        latest = (
            ""
            if not records
            else records[-1].record_id
        )
        utilization = (
            len(records)
            / self.policy.max_records_per_chain
        )
        return DurableDestructionChainHealth(
            chain_id,
            verification,
            index_health,
            len(records),
            pruning,
            orphan_gc,
            verified,
            latest,
            utilization,
            tuple(findings),
        )

    def inspect(
        self,
        chain_ids: Iterable[str],
    ) -> DurableDestructionFleetHealth:
        ids = self._ids(
            chain_ids
        )
        chains = tuple(
            self._inspect_chain(
                chain_id
            )
            for chain_id in ids
        )
        findings: list[
            DurableDestructionHealthFinding
        ] = []
        if not ids and self.policy.require_nonempty:
            findings.append(
                DurableDestructionHealthFinding(
                    DurableDestructionHealthSeverity.ERROR,
                    "destruction.fleet.empty",
                    "destruction health requires at least one chain",
                )
            )
        return DurableDestructionFleetHealth(
            self.policy.digest,
            chains,
            tuple(findings),
        )

    def require(
        self,
        chain_ids: Iterable[str],
    ) -> DurableDestructionFleetHealth:
        report = self.inspect(
            chain_ids
        )
        if not report.allowed:
            finding = next(
                (
                    item
                    for chain in report.chains
                    for item in chain.findings
                    if item.severity
                    is DurableDestructionHealthSeverity.ERROR
                ),
                None,
            )
            if finding is None:
                finding = next(
                    (
                        item
                        for item in report.findings
                        if item.severity
                        is DurableDestructionHealthSeverity.ERROR
                    ),
                    None,
                )
            detail = (
                "durable destruction health failed"
                if finding is None
                else finding.message
            )
            raise DurableDestructionHealthError(
                detail
            )
        return report

    def repair_indexes_and_require(
        self,
        chain_ids: Iterable[str],
        *,
        max_repairs_per_chain: int = 10_000,
    ) -> DurableDestructionFleetHealth:
        ids = self._ids(
            chain_ids
        )
        if (
            isinstance(max_repairs_per_chain, bool)
            or not isinstance(max_repairs_per_chain, int)
            or max_repairs_per_chain <= 0
        ):
            raise ValueError(
                "max_repairs_per_chain must be positive integer"
            )
        for chain_id in ids:
            health = (
                self.ledger
                .inspect_operation_indexes(
                    chain_id
                )
            )
            if health.missing_indexes:
                self.ledger.repair_operation_indexes(
                    chain_id,
                    max_repairs=(
                        max_repairs_per_chain
                    ),
                )
        return self.require(
            ids
        )
