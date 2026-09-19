"""Fleet-level health policy for durable compaction lineage proofs.

This guard is intentionally read-only. It composes the durable compaction
lineage auditor across a bounded workflow set and turns historical lineage
status into an admission decision suitable for startup, maintenance windows,
and destructive-operation preflight.

Manual-review lineage can never be tolerated. Incomplete workflows may be
allowed only through an explicit bounded policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

from skeleton.shells.ai.durable_compaction_lineage import (
    CompactionLineageArtifactState,
    CompactionLineageFinding,
    CompactionLineageSeverity,
    CompactionLineageStatus,
    DurableCompactionLineageAuditor,
    DurableCompactionLineageReport,
)


class CompactionLineageHealthSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class CompactionLineageHealthPolicy:
    max_workflows: int = 512
    max_incomplete: int = 0
    minimum_verified: int = 0
    require_nonempty: bool = False
    max_findings: int = 2048

    def __post_init__(self) -> None:
        for name in (
            "max_workflows",
            "max_incomplete",
            "minimum_verified",
            "max_findings",
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
        if self.max_workflows <= 0:
            raise ValueError(
                "max_workflows must be positive"
            )
        if self.max_findings <= 0:
            raise ValueError(
                "max_findings must be positive"
            )
        if (
            self.max_incomplete
            > self.max_workflows
        ):
            raise ValueError(
                "max_incomplete exceeds max_workflows"
            )
        if (
            self.minimum_verified
            > self.max_workflows
        ):
            raise ValueError(
                "minimum_verified exceeds max_workflows"
            )
        if not isinstance(
            self.require_nonempty,
            bool,
        ):
            raise ValueError(
                "require_nonempty must be bool"
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
            "max_workflows": self.max_workflows,
            "max_incomplete": self.max_incomplete,
            "minimum_verified": self.minimum_verified,
            "require_nonempty": self.require_nonempty,
            "max_findings": self.max_findings,
        }


@dataclass(frozen=True)
class CompactionLineageHealthFinding:
    severity: CompactionLineageHealthSeverity
    code: str
    message: str
    workflow_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "severity",
            CompactionLineageHealthSeverity(
                self.severity
            ),
        )
        if not self.code or len(self.code) > 160:
            raise ValueError(
                "invalid lineage health finding code"
            )
        if (
            not self.message
            or len(self.message) > 2048
        ):
            raise ValueError(
                "invalid lineage health finding message"
            )
        if len(self.workflow_id) > 256:
            raise ValueError(
                "lineage health workflow_id too long"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "workflow_id": self.workflow_id,
        }


@dataclass(frozen=True)
class CompactionLineageFleetReport:
    policy_digest: str
    workflow_ids: tuple[str, ...]
    reports: tuple[
        DurableCompactionLineageReport,
        ...,
    ]
    findings: tuple[
        CompactionLineageHealthFinding,
        ...,
    ]

    def __post_init__(self) -> None:
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be 64-character digest"
            )
        ids = tuple(self.workflow_ids)
        if ids != tuple(sorted(ids)):
            raise ValueError(
                "workflow_ids must be sorted"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate workflow_id"
            )
        if any(
            not item
            or len(item) != 64
            for item in ids
        ):
            raise ValueError(
                "invalid workflow_id"
            )
        reports = tuple(self.reports)
        report_ids = tuple(
            item.workflow_id
            for item in reports
        )
        if report_ids != ids:
            raise ValueError(
                "reports do not match workflow ids"
            )
        object.__setattr__(
            self,
            "workflow_ids",
            ids,
        )
        object.__setattr__(
            self,
            "reports",
            reports,
        )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )

    @property
    def verified(self) -> int:
        return sum(
            item.status
            is CompactionLineageStatus.VERIFIED
            for item in self.reports
        )

    @property
    def incomplete(self) -> int:
        return sum(
            item.status
            is CompactionLineageStatus.INCOMPLETE
            for item in self.reports
        )

    @property
    def manual_review(self) -> int:
        return sum(
            item.status
            is CompactionLineageStatus.MANUAL_REVIEW
            for item in self.reports
        )

    @property
    def errors(self) -> int:
        return sum(
            item.severity
            is CompactionLineageHealthSeverity.ERROR
            for item in self.findings
        )

    @property
    def warnings(self) -> int:
        return sum(
            item.severity
            is CompactionLineageHealthSeverity.WARNING
            for item in self.findings
        )

    @property
    def allowed(self) -> bool:
        return self.errors == 0

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
            "verified": self.verified,
            "incomplete": self.incomplete,
            "manual_review": self.manual_review,
            "errors": self.errors,
            "warnings": self.warnings,
            "policy_digest": self.policy_digest,
            "workflow_ids": list(
                self.workflow_ids
            ),
            "reports": [
                item.to_dict()
                for item in self.reports
            ],
            "findings": [
                item.to_dict()
                for item in self.findings
            ],
        }
        if include_digest:
            data["digest"] = self.digest
        return data


class CompactionLineageFleetError(
    RuntimeError
):
    pass


class CompactionLineageFleetGuard:
    """Apply bounded fail-closed policy to historical compaction lineages."""

    def __init__(
        self,
        auditor: DurableCompactionLineageAuditor,
        policy: CompactionLineageHealthPolicy | None = None,
    ) -> None:
        if not isinstance(
            auditor,
            DurableCompactionLineageAuditor,
        ):
            raise TypeError(
                "auditor must be DurableCompactionLineageAuditor"
            )
        self.auditor = auditor
        self.policy = (
            policy
            or CompactionLineageHealthPolicy()
        )
        if not isinstance(
            self.policy,
            CompactionLineageHealthPolicy,
        ):
            raise TypeError(
                "policy must be CompactionLineageHealthPolicy"
            )

    @staticmethod
    def _normalize_ids(
        workflow_ids: Iterable[str],
        *,
        maximum: int,
    ) -> tuple[str, ...]:
        values = tuple(workflow_ids)
        if len(values) > maximum:
            raise CompactionLineageFleetError(
                "compaction lineage workflow bound exceeded"
            )
        if any(
            not isinstance(item, str)
            or len(item) != 64
            for item in values
        ):
            raise ValueError(
                "workflow ids must be 64-character digests"
            )
        if len(values) != len(set(values)):
            raise ValueError(
                "duplicate workflow_id"
            )
        return tuple(sorted(values))

    @staticmethod
    def _synthetic_manual_report(
        workflow_id: str,
        exc: Exception,
    ) -> DurableCompactionLineageReport:
        empty = CompactionLineageArtifactState(
            False,
            False,
            False,
        )
        return DurableCompactionLineageReport(
            workflow_id,
            "",
            "",
            None,
            CompactionLineageStatus.MANUAL_REVIEW,
            "",
            empty,
            empty,
            empty,
            empty,
            empty,
            empty,
            (
                CompactionLineageFinding(
                    "lineage.probe_error",
                    CompactionLineageSeverity.CORRUPTION,
                    "lineage auditor raised "
                    f"{type(exc).__name__}",
                ),
            ),
        )

    def _inspect_one(
        self,
        workflow_id: str,
    ) -> DurableCompactionLineageReport:
        try:
            return self.auditor.inspect(
                workflow_id
            )
        except Exception as exc:
            return self._synthetic_manual_report(
                workflow_id,
                exc,
            )

    @staticmethod
    def _workflow_findings(
        report: DurableCompactionLineageReport,
        *,
        incomplete_allowed: bool,
    ) -> tuple[
        CompactionLineageHealthFinding,
        ...,
    ]:
        findings: list[
            CompactionLineageHealthFinding
        ] = []
        if (
            report.status
            is CompactionLineageStatus.MANUAL_REVIEW
        ):
            findings.append(
                CompactionLineageHealthFinding(
                    CompactionLineageHealthSeverity.ERROR,
                    "compaction_lineage.manual_review",
                    "compaction lineage requires manual review",
                    report.workflow_id,
                )
            )
        elif (
            report.status
            is CompactionLineageStatus.INCOMPLETE
        ):
            findings.append(
                CompactionLineageHealthFinding(
                    (
                        CompactionLineageHealthSeverity.WARNING
                        if incomplete_allowed
                        else CompactionLineageHealthSeverity.ERROR
                    ),
                    "compaction_lineage.incomplete",
                    "compaction lineage is incomplete",
                    report.workflow_id,
                )
            )
        return tuple(findings)

    def inspect(
        self,
        workflow_ids: Iterable[str],
    ) -> CompactionLineageFleetReport:
        ids = self._normalize_ids(
            workflow_ids,
            maximum=self.policy.max_workflows,
        )
        reports = tuple(
            self._inspect_one(item)
            for item in ids
        )
        findings: list[
            CompactionLineageHealthFinding
        ] = []

        if (
            self.policy.require_nonempty
            and not ids
        ):
            findings.append(
                CompactionLineageHealthFinding(
                    CompactionLineageHealthSeverity.ERROR,
                    "compaction_lineage.empty_required_set",
                    "lineage policy requires at least one workflow",
                )
            )

        verified = sum(
            item.status
            is CompactionLineageStatus.VERIFIED
            for item in reports
        )
        incomplete = sum(
            item.status
            is CompactionLineageStatus.INCOMPLETE
            for item in reports
        )
        manual = sum(
            item.status
            is CompactionLineageStatus.MANUAL_REVIEW
            for item in reports
        )

        if (
            verified
            < self.policy.minimum_verified
        ):
            findings.append(
                CompactionLineageHealthFinding(
                    CompactionLineageHealthSeverity.ERROR,
                    "compaction_lineage.minimum_verified",
                    (
                        "verified compaction lineages below "
                        f"required minimum: {verified}<"
                        f"{self.policy.minimum_verified}"
                    ),
                )
            )

        if (
            incomplete
            > self.policy.max_incomplete
        ):
            findings.append(
                CompactionLineageHealthFinding(
                    CompactionLineageHealthSeverity.ERROR,
                    "compaction_lineage.incomplete_bound",
                    (
                        "incomplete compaction lineages exceed "
                        f"policy bound: {incomplete}>"
                        f"{self.policy.max_incomplete}"
                    ),
                )
            )
        elif incomplete:
            findings.append(
                CompactionLineageHealthFinding(
                    CompactionLineageHealthSeverity.WARNING,
                    "compaction_lineage.incomplete_tolerated",
                    (
                        f"{incomplete} incomplete compaction "
                        "lineage(s) are within policy tolerance"
                    ),
                )
            )

        if manual:
            findings.append(
                CompactionLineageHealthFinding(
                    CompactionLineageHealthSeverity.ERROR,
                    "compaction_lineage.manual_review_present",
                    (
                        f"{manual} compaction lineage(s) "
                        "require manual review"
                    ),
                )
            )

        incomplete_allowed = (
            incomplete
            <= self.policy.max_incomplete
        )
        for report in reports:
            findings.extend(
                self._workflow_findings(
                    report,
                    incomplete_allowed=(
                        incomplete_allowed
                    ),
                )
            )
            for detail in report.findings:
                if detail.severity in {
                    CompactionLineageSeverity.CONFLICT,
                    CompactionLineageSeverity.CORRUPTION,
                }:
                    findings.append(
                        CompactionLineageHealthFinding(
                            CompactionLineageHealthSeverity.ERROR,
                            (
                                "compaction_lineage.detail."
                                + detail.code
                            )[:160],
                            detail.message,
                            report.workflow_id,
                        )
                    )

        if len(findings) > self.policy.max_findings:
            raise CompactionLineageFleetError(
                "compaction lineage finding bound exceeded"
            )

        return CompactionLineageFleetReport(
            self.policy.digest,
            ids,
            reports,
            tuple(findings),
        )

    def require(
        self,
        workflow_ids: Iterable[str],
    ) -> CompactionLineageFleetReport:
        report = self.inspect(
            workflow_ids
        )
        if not report.allowed:
            detail = (
                report.findings[0].message
                if report.findings
                else "compaction lineage fleet denied"
            )
            raise CompactionLineageFleetError(
                detail
            )
        return report
