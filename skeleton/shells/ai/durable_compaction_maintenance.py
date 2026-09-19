"""Fail-closed maintenance preflight over durable compaction history.

Individual compaction workflows can be internally valid while the overall
destructive history is incomplete.  In particular, a signed hot floor may
exist without any workflow in the operator's audited set, or multiple workflows
may claim the same floor.

This module combines:
- historical workflow lineage verification;
- signed hot-floor history verification to genesis; and
- exact workflow-to-floor coverage.

It is read-only.  It issues no certificate or authorization, mutates no floor,
and performs no pruning or repair.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

from skeleton.shells.ai.durable_compaction_lineage import (
    CompactionLineageStatus,
)
from skeleton.shells.ai.durable_compaction_lineage_health import (
    CompactionLineageFleetGuard,
    CompactionLineageFleetReport,
)
from skeleton.shells.ai.durable_hot_floor import (
    DurableHotFloorHistoryReport,
)


class CompactionMaintenanceSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class CompactionMaintenancePolicy:
    max_chains: int = 32
    max_findings: int = 4096
    require_nonempty_chains: bool = True
    require_floor_workflow_coverage: bool = True
    reject_duplicate_floor_claims: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_chains",
            "max_findings",
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
        for name in (
            "require_nonempty_chains",
            "require_floor_workflow_coverage",
            "reject_duplicate_floor_claims",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "max_chains": self.max_chains,
            "max_findings": self.max_findings,
            "require_nonempty_chains": (
                self.require_nonempty_chains
            ),
            "require_floor_workflow_coverage": (
                self.require_floor_workflow_coverage
            ),
            "reject_duplicate_floor_claims": (
                self.reject_duplicate_floor_claims
            ),
        }


@dataclass(frozen=True)
class CompactionMaintenanceFinding:
    severity: CompactionMaintenanceSeverity
    code: str
    message: str
    chain_id: str = ""
    workflow_id: str = ""
    floor_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "severity",
            CompactionMaintenanceSeverity(
                self.severity
            ),
        )
        if not self.code or len(self.code) > 160:
            raise ValueError(
                "invalid maintenance finding code"
            )
        if (
            not self.message
            or len(self.message) > 2048
        ):
            raise ValueError(
                "invalid maintenance finding message"
            )
        if len(self.chain_id) > 128:
            raise ValueError(
                "maintenance chain_id too long"
            )
        if len(self.workflow_id) > 256:
            raise ValueError(
                "maintenance workflow_id too long"
            )
        if self.floor_id and len(self.floor_id) != 64:
            raise ValueError(
                "maintenance floor_id must be 64-character digest"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "chain_id": self.chain_id,
            "workflow_id": self.workflow_id,
            "floor_id": self.floor_id,
        }


@dataclass(frozen=True)
class CompactionChainMaintenanceHealth:
    chain_id: str
    history: DurableHotFloorHistoryReport | None
    claimed_floor_ids: tuple[str, ...]
    unclaimed_floor_ids: tuple[str, ...]
    duplicate_claim_floor_ids: tuple[str, ...]
    findings: tuple[
        CompactionMaintenanceFinding,
        ...,
    ]

    def __post_init__(self) -> None:
        if (
            not self.chain_id
            or len(self.chain_id) > 128
        ):
            raise ValueError(
                "invalid maintenance chain_id"
            )
        for name in (
            "claimed_floor_ids",
            "unclaimed_floor_ids",
            "duplicate_claim_floor_ids",
        ):
            values = tuple(
                getattr(self, name)
            )
            if any(
                len(item) != 64
                for item in values
            ):
                raise ValueError(
                    f"{name} contains invalid floor id"
                )
            if values != tuple(sorted(values)):
                raise ValueError(
                    f"{name} must be sorted"
                )
            if len(values) != len(set(values)):
                raise ValueError(
                    f"{name} contains duplicate floor id"
                )
            object.__setattr__(
                self,
                name,
                values,
            )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )
        if (
            self.history is not None
            and self.history.chain_id
            != self.chain_id
        ):
            raise ValueError(
                "history chain differs from maintenance chain"
            )

    @property
    def errors(self) -> int:
        return sum(
            item.severity
            is CompactionMaintenanceSeverity.ERROR
            for item in self.findings
        )

    @property
    def warnings(self) -> int:
        return sum(
            item.severity
            is CompactionMaintenanceSeverity.WARNING
            for item in self.findings
        )

    @property
    def floor_count(self) -> int:
        return (
            0
            if self.history is None
            else self.history.floor_count
        )

    @property
    def ok(self) -> bool:
        return (
            self.history is not None
            and self.history.ok
            and self.errors == 0
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
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "floor_count": self.floor_count,
            "history": (
                None
                if self.history is None
                else self.history.to_dict()
            ),
            "claimed_floor_ids": list(
                self.claimed_floor_ids
            ),
            "unclaimed_floor_ids": list(
                self.unclaimed_floor_ids
            ),
            "duplicate_claim_floor_ids": list(
                self.duplicate_claim_floor_ids
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
class DurableCompactionMaintenanceReport:
    policy_digest: str
    lineage: CompactionLineageFleetReport
    chains: tuple[
        CompactionChainMaintenanceHealth,
        ...,
    ]
    findings: tuple[
        CompactionMaintenanceFinding,
        ...,
    ]

    def __post_init__(self) -> None:
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be 64-character digest"
            )
        chains = tuple(self.chains)
        ids = tuple(
            item.chain_id
            for item in chains
        )
        if ids != tuple(sorted(ids)):
            raise ValueError(
                "maintenance chains must be sorted"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate maintenance chain_id"
            )
        object.__setattr__(
            self,
            "chains",
            chains,
        )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )

    @property
    def errors(self) -> int:
        own = sum(
            item.severity
            is CompactionMaintenanceSeverity.ERROR
            for item in self.findings
        )
        return (
            own
            + sum(
                item.errors
                for item in self.chains
            )
            + self.lineage.errors
        )

    @property
    def warnings(self) -> int:
        own = sum(
            item.severity
            is CompactionMaintenanceSeverity.WARNING
            for item in self.findings
        )
        return (
            own
            + sum(
                item.warnings
                for item in self.chains
            )
            + self.lineage.warnings
        )

    @property
    def allowed(self) -> bool:
        return (
            self.lineage.allowed
            and self.errors == 0
            and all(
                item.ok
                for item in self.chains
            )
        )

    @property
    def total_floors(self) -> int:
        return sum(
            item.floor_count
            for item in self.chains
        )

    @property
    def unclaimed_floors(self) -> int:
        return sum(
            len(item.unclaimed_floor_ids)
            for item in self.chains
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
        data: dict[str, object] = {
            "allowed": self.allowed,
            "errors": self.errors,
            "warnings": self.warnings,
            "total_floors": self.total_floors,
            "unclaimed_floors": (
                self.unclaimed_floors
            ),
            "policy_digest": self.policy_digest,
            "lineage": self.lineage.to_dict(),
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


class DurableCompactionMaintenanceError(
    RuntimeError
):
    pass


class DurableCompactionMaintenanceGuard:
    """Read-only preflight for historical destructive compaction state."""

    def __init__(
        self,
        lineage: CompactionLineageFleetGuard,
        policy: CompactionMaintenancePolicy | None = None,
    ) -> None:
        if not isinstance(
            lineage,
            CompactionLineageFleetGuard,
        ):
            raise TypeError(
                "lineage must be CompactionLineageFleetGuard"
            )
        self.lineage = lineage
        self.policy = (
            policy
            or CompactionMaintenancePolicy()
        )
        if not isinstance(
            self.policy,
            CompactionMaintenancePolicy,
        ):
            raise TypeError(
                "policy must be CompactionMaintenancePolicy"
            )
        self.hot_floors = (
            lineage.auditor.hot_floors
        )

    @staticmethod
    def _chain_ids(
        chain_ids: Iterable[str],
        *,
        maximum: int,
    ) -> tuple[str, ...]:
        values = tuple(chain_ids)
        if len(values) > maximum:
            raise DurableCompactionMaintenanceError(
                "maintenance chain bound exceeded"
            )
        if any(
            not isinstance(item, str)
            or not item
            or len(item) > 128
            for item in values
        ):
            raise ValueError(
                "invalid maintenance chain_id"
            )
        if len(values) != len(set(values)):
            raise ValueError(
                "duplicate maintenance chain_id"
            )
        return tuple(sorted(values))

    @staticmethod
    def _add(
        findings: list[
            CompactionMaintenanceFinding
        ],
        severity: CompactionMaintenanceSeverity,
        code: str,
        message: str,
        *,
        chain_id: str = "",
        workflow_id: str = "",
        floor_id: str = "",
    ) -> None:
        findings.append(
            CompactionMaintenanceFinding(
                severity,
                code,
                message,
                chain_id,
                workflow_id,
                floor_id,
            )
        )

    def _history(
        self,
        chain_id: str,
    ) -> tuple[
        DurableHotFloorHistoryReport | None,
        tuple[CompactionMaintenanceFinding, ...],
    ]:
        findings: list[
            CompactionMaintenanceFinding
        ] = []
        try:
            report = (
                self.hot_floors
                .inspect_history(chain_id)
            )
        except Exception as exc:
            self._add(
                findings,
                CompactionMaintenanceSeverity.ERROR,
                "maintenance.floor_history_probe_error",
                "hot-floor history inspection raised "
                f"{type(exc).__name__}",
                chain_id=chain_id,
            )
            return None, tuple(findings)
        if not report.ok:
            self._add(
                findings,
                CompactionMaintenanceSeverity.ERROR,
                "maintenance.floor_history_invalid",
                (
                    report.issues[0]
                    if report.issues
                    else "hot-floor history is incomplete"
                ),
                chain_id=chain_id,
            )
        return report, tuple(findings)

    @staticmethod
    def _claims(
        lineage: CompactionLineageFleetReport,
    ) -> dict[
        tuple[str, str],
        list[str],
    ]:
        claims: dict[
            tuple[str, str],
            list[str],
        ] = {}
        for report in lineage.reports:
            if (
                not report.chain_id
                or not report.hot_floor.present
                or not report.hot_floor.artifact_id
            ):
                continue
            key = (
                report.chain_id,
                report.hot_floor.artifact_id,
            )
            claims.setdefault(
                key,
                [],
            ).append(
                report.workflow_id
            )
        return claims

    def inspect(
        self,
        workflow_ids: Iterable[str],
        chain_ids: Iterable[str],
    ) -> DurableCompactionMaintenanceReport:
        ids = self._chain_ids(
            chain_ids,
            maximum=self.policy.max_chains,
        )
        lineage = self.lineage.inspect(
            workflow_ids
        )
        own_findings: list[
            CompactionMaintenanceFinding
        ] = []

        if (
            self.policy.require_nonempty_chains
            and not ids
        ):
            self._add(
                own_findings,
                CompactionMaintenanceSeverity.ERROR,
                "maintenance.empty_chain_set",
                "maintenance policy requires at least one chain",
            )

        chain_set = set(ids)
        for report in lineage.reports:
            if (
                report.chain_id
                and report.chain_id
                not in chain_set
            ):
                self._add(
                    own_findings,
                    CompactionMaintenanceSeverity.ERROR,
                    "maintenance.workflow_chain_unchecked",
                    (
                        "workflow lineage references a chain "
                        "outside maintenance preflight"
                    ),
                    chain_id=report.chain_id,
                    workflow_id=report.workflow_id,
                    floor_id=(
                        report.hot_floor.artifact_id
                    ),
                )

        claims = self._claims(
            lineage
        )
        chain_health: list[
            CompactionChainMaintenanceHealth
        ] = []

        for chain_id in ids:
            history, history_findings = (
                self._history(chain_id)
            )
            findings = list(
                history_findings
            )
            historical_ids = (
                set()
                if history is None
                else {
                    item.floor.floor_id
                    for item in history.floors
                }
            )
            claimed = {
                floor_id
                for (
                    claim_chain,
                    floor_id,
                ) in claims
                if claim_chain == chain_id
            }
            duplicate = {
                floor_id
                for (
                    claim_chain,
                    floor_id,
                ), workflow_claims
                in claims.items()
                if (
                    claim_chain == chain_id
                    and len(workflow_claims) > 1
                )
            }
            unclaimed = (
                historical_ids - claimed
            )

            if (
                self.policy
                .require_floor_workflow_coverage
            ):
                for floor_id in sorted(
                    unclaimed
                ):
                    self._add(
                        findings,
                        CompactionMaintenanceSeverity.ERROR,
                        "maintenance.floor_without_workflow",
                        (
                            "committed hot floor has no audited "
                            "workflow lineage"
                        ),
                        chain_id=chain_id,
                        floor_id=floor_id,
                    )

            if (
                self.policy
                .reject_duplicate_floor_claims
            ):
                for floor_id in sorted(
                    duplicate
                ):
                    self._add(
                        findings,
                        CompactionMaintenanceSeverity.ERROR,
                        "maintenance.floor_claimed_by_multiple_workflows",
                        (
                            "committed hot floor is claimed by "
                            "multiple workflows"
                        ),
                        chain_id=chain_id,
                        floor_id=floor_id,
                    )

            for floor_id in sorted(
                claimed - historical_ids
            ):
                self._add(
                    findings,
                    CompactionMaintenanceSeverity.ERROR,
                    "maintenance.workflow_floor_not_in_history",
                    (
                        "workflow claims a floor absent from "
                        "committed hot-floor history"
                    ),
                    chain_id=chain_id,
                    floor_id=floor_id,
                )

            chain_health.append(
                CompactionChainMaintenanceHealth(
                    chain_id,
                    history,
                    tuple(sorted(claimed)),
                    tuple(sorted(unclaimed)),
                    tuple(sorted(duplicate)),
                    tuple(findings),
                )
            )

        finding_count = (
            len(own_findings)
            + sum(
                len(item.findings)
                for item in chain_health
            )
            + len(lineage.findings)
        )
        if finding_count > self.policy.max_findings:
            raise DurableCompactionMaintenanceError(
                "maintenance finding bound exceeded"
            )

        return DurableCompactionMaintenanceReport(
            self.policy.digest,
            lineage,
            tuple(chain_health),
            tuple(own_findings),
        )

    def require(
        self,
        workflow_ids: Iterable[str],
        chain_ids: Iterable[str],
    ) -> DurableCompactionMaintenanceReport:
        report = self.inspect(
            workflow_ids,
            chain_ids,
        )
        if not report.allowed:
            detail = ""
            if report.findings:
                detail = (
                    report.findings[0].message
                )
            else:
                for chain in report.chains:
                    if chain.findings:
                        detail = (
                            chain.findings[0].message
                        )
                        break
            if not detail and report.lineage.findings:
                detail = (
                    report.lineage.findings[0].message
                )
            raise DurableCompactionMaintenanceError(
                detail
                or "durable compaction maintenance preflight denied"
            )
        return report
