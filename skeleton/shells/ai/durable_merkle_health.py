"""Inspection-only health policy for finalized-session Merkle proof bundles.

Merkle proofs are derived acceleration evidence.  They do not make an invalid
recovery state valid and this guard never prepares or mutates proof bundles.
Operators may separately use DurableSessionMerkleOperator.prepare().

The health guard exists so deployments can gradually move from optional Merkle
proofs to required compact-proof coverage without weakening the existing
recovery or durable-readiness gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

from skeleton.shells.ai.durable_merkle_operator import (
    DurableMerkleOperatorResult,
    DurableMerkleOperatorStatus,
    DurableSessionMerkleOperator,
)


class DurableMerkleHealthSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class DurableMerkleHealthPolicy:
    max_finalizations: int = 512
    require_nonempty: bool = False
    require_bundles: bool = False
    maximum_missing: int = 512
    maximum_incomplete: int = 0
    minimum_verified: int = 0
    reject_manual_review: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_finalizations",
            "maximum_missing",
            "maximum_incomplete",
            "minimum_verified",
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
        if self.max_finalizations <= 0:
            raise ValueError(
                "max_finalizations must be positive"
            )
        # Tolerances above the inspection bound are valid and simply act as
        # effectively-unbounded ceilings. A required minimum, however, must be
        # satisfiable within the bounded inspection set.
        if self.minimum_verified > self.max_finalizations:
            raise ValueError(
                "minimum_verified exceeds max_finalizations"
            )
        for name in (
            "require_nonempty",
            "require_bundles",
            "reject_manual_review",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        if not self.reject_manual_review:
            raise ValueError(
                "manual-review Merkle state may not be allowed"
            )
        if self.require_bundles and (
            self.maximum_missing != 0
        ):
            raise ValueError(
                "require_bundles requires maximum_missing=0"
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
            "max_finalizations": self.max_finalizations,
            "require_nonempty": self.require_nonempty,
            "require_bundles": self.require_bundles,
            "maximum_missing": self.maximum_missing,
            "maximum_incomplete": self.maximum_incomplete,
            "minimum_verified": self.minimum_verified,
            "reject_manual_review": self.reject_manual_review,
        }


@dataclass(frozen=True)
class DurableMerkleHealthFinding:
    severity: DurableMerkleHealthSeverity
    code: str
    message: str
    finalization_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "severity",
            DurableMerkleHealthSeverity(
                self.severity
            ),
        )
        if not self.code or len(self.code) > 128:
            raise ValueError(
                "invalid Merkle health finding code"
            )
        if not self.message or len(self.message) > 2048:
            raise ValueError(
                "invalid Merkle health finding message"
            )
        if len(self.finalization_id) > 256:
            raise ValueError(
                "Merkle health finalization_id too long"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "finalization_id": self.finalization_id,
        }


@dataclass(frozen=True)
class DurableMerkleHealthReport:
    policy_digest: str
    finalization_ids: tuple[str, ...]
    reports: tuple[
        DurableMerkleOperatorResult,
        ...,
    ]
    findings: tuple[
        DurableMerkleHealthFinding,
        ...,
    ]

    def __post_init__(self) -> None:
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be digest-shaped"
            )
        ids = tuple(
            self.finalization_ids
        )
        if ids != tuple(sorted(ids)):
            raise ValueError(
                "Merkle health finalization_ids must be sorted"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate Merkle health finalization_id"
            )
        if any(
            not item
            or len(item) > 256
            for item in ids
        ):
            raise ValueError(
                "invalid Merkle health finalization_id"
            )
        object.__setattr__(
            self,
            "finalization_ids",
            ids,
        )
        object.__setattr__(
            self,
            "reports",
            tuple(self.reports),
        )
        object.__setattr__(
            self,
            "findings",
            tuple(self.findings),
        )
        if tuple(
            item.finalization_id
            for item in self.reports
        ) != ids:
            raise ValueError(
                "Merkle health reports do not match requested ids"
            )

    @property
    def verified(self) -> int:
        return sum(
            item.status
            is DurableMerkleOperatorStatus.VERIFIED
            for item in self.reports
        )

    @property
    def missing(self) -> int:
        return sum(
            item.status
            is DurableMerkleOperatorStatus.MISSING
            for item in self.reports
        )

    @property
    def incomplete(self) -> int:
        return sum(
            item.status
            is DurableMerkleOperatorStatus.INCOMPLETE
            for item in self.reports
        )

    @property
    def manual_review(self) -> int:
        return sum(
            item.status
            is DurableMerkleOperatorStatus.MANUAL_REVIEW
            for item in self.reports
        )

    @property
    def errors(self) -> int:
        return sum(
            item.severity
            is DurableMerkleHealthSeverity.ERROR
            for item in self.findings
        )

    @property
    def warnings(self) -> int:
        return sum(
            item.severity
            is DurableMerkleHealthSeverity.WARNING
            for item in self.findings
        )

    @property
    def allowed(self) -> bool:
        return self.errors == 0

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
            "verified": self.verified,
            "missing": self.missing,
            "incomplete": self.incomplete,
            "manual_review": self.manual_review,
            "errors": self.errors,
            "warnings": self.warnings,
            "policy_digest": self.policy_digest,
            "finalization_ids": list(
                self.finalization_ids
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


class DurableMerkleHealthError(
    RuntimeError
):
    pass


class DurableMerkleHealthGuard:
    """Inspect a bounded finalization set without mutating proof state."""

    def __init__(
        self,
        operator: DurableSessionMerkleOperator,
        policy: DurableMerkleHealthPolicy | None = None,
    ) -> None:
        if not isinstance(
            operator,
            DurableSessionMerkleOperator,
        ):
            raise TypeError(
                "operator must be DurableSessionMerkleOperator"
            )
        self.operator = operator
        self.policy = (
            policy
            or DurableMerkleHealthPolicy()
        )
        if not isinstance(
            self.policy,
            DurableMerkleHealthPolicy,
        ):
            raise TypeError(
                "policy must be DurableMerkleHealthPolicy"
            )

    @staticmethod
    def _ids(
        finalization_ids: Iterable[str],
        *,
        maximum: int,
    ) -> tuple[str, ...]:
        values = tuple(
            finalization_ids
        )
        if len(values) > maximum:
            raise ValueError(
                "Merkle health finalization bound exceeded"
            )
        if any(
            not isinstance(item, str)
            or not item
            or len(item) > 256
            for item in values
        ):
            raise ValueError(
                "invalid Merkle health finalization_id"
            )
        if len(values) != len(set(values)):
            raise ValueError(
                "duplicate Merkle health finalization_id"
            )
        return tuple(sorted(values))

    def _inspect_one(
        self,
        finalization_id: str,
    ) -> DurableMerkleOperatorResult:
        try:
            return self.operator.inspect(
                finalization_id
            )
        except Exception as exc:
            return DurableMerkleOperatorResult(
                finalization_id,
                "",
                DurableMerkleOperatorStatus.MANUAL_REVIEW,
                "",
                None,
                False,
                False,
                "",
                0,
                0,
                None,
                (
                    "Merkle health operator raised "
                    f"{type(exc).__name__}",
                ),
            )

    @staticmethod
    def _finding(
        findings: list[
            DurableMerkleHealthFinding
        ],
        severity: DurableMerkleHealthSeverity,
        code: str,
        message: str,
        finalization_id: str = "",
    ) -> None:
        findings.append(
            DurableMerkleHealthFinding(
                severity,
                code,
                message,
                finalization_id,
            )
        )

    def inspect(
        self,
        finalization_ids: Iterable[str],
    ) -> DurableMerkleHealthReport:
        ids = self._ids(
            finalization_ids,
            maximum=(
                self.policy.max_finalizations
            ),
        )
        reports = tuple(
            self._inspect_one(item)
            for item in ids
        )
        findings: list[
            DurableMerkleHealthFinding
        ] = []

        if (
            self.policy.require_nonempty
            and not ids
        ):
            self._finding(
                findings,
                DurableMerkleHealthSeverity.ERROR,
                "merkle_health.empty_required_set",
                (
                    "Merkle health policy requires at least "
                    "one finalization"
                ),
            )

        verified = sum(
            item.status
            is DurableMerkleOperatorStatus.VERIFIED
            for item in reports
        )
        missing = sum(
            item.status
            is DurableMerkleOperatorStatus.MISSING
            for item in reports
        )
        incomplete = sum(
            item.status
            is DurableMerkleOperatorStatus.INCOMPLETE
            for item in reports
        )
        manual = sum(
            item.status
            is DurableMerkleOperatorStatus.MANUAL_REVIEW
            for item in reports
        )

        if (
            verified
            < self.policy.minimum_verified
        ):
            self._finding(
                findings,
                DurableMerkleHealthSeverity.ERROR,
                "merkle_health.minimum_verified",
                (
                    "verified Merkle bundles below required minimum: "
                    f"{verified}<"
                    f"{self.policy.minimum_verified}"
                ),
            )

        if (
            missing
            > self.policy.maximum_missing
        ):
            self._finding(
                findings,
                DurableMerkleHealthSeverity.ERROR,
                "merkle_health.missing_bound",
                (
                    "missing Merkle bundles exceed policy bound: "
                    f"{missing}>"
                    f"{self.policy.maximum_missing}"
                ),
            )
        elif missing:
            severity = (
                DurableMerkleHealthSeverity.ERROR
                if self.policy.require_bundles
                else DurableMerkleHealthSeverity.WARNING
            )
            self._finding(
                findings,
                severity,
                (
                    "merkle_health.required_missing"
                    if self.policy.require_bundles
                    else "merkle_health.missing_optional"
                ),
                (
                    f"{missing} finalized session(s) do not "
                    "yet have stored Merkle proof bundles"
                ),
            )

        if (
            incomplete
            > self.policy.maximum_incomplete
        ):
            self._finding(
                findings,
                DurableMerkleHealthSeverity.ERROR,
                "merkle_health.incomplete_bound",
                (
                    "incomplete Merkle recovery states exceed policy bound: "
                    f"{incomplete}>"
                    f"{self.policy.maximum_incomplete}"
                ),
            )
        elif incomplete:
            self._finding(
                findings,
                DurableMerkleHealthSeverity.WARNING,
                "merkle_health.incomplete_tolerated",
                (
                    f"{incomplete} incomplete recovery state(s) "
                    "are within configured tolerance"
                ),
            )

        if manual:
            self._finding(
                findings,
                DurableMerkleHealthSeverity.ERROR,
                "merkle_health.manual_review",
                (
                    f"{manual} Merkle/recovery state(s) "
                    "require manual review"
                ),
            )

        for report in reports:
            if (
                report.status
                is DurableMerkleOperatorStatus.VERIFIED
            ):
                continue
            if (
                report.status
                is DurableMerkleOperatorStatus.MISSING
            ):
                severity = (
                    DurableMerkleHealthSeverity.ERROR
                    if self.policy.require_bundles
                    or missing
                    > self.policy.maximum_missing
                    else DurableMerkleHealthSeverity.WARNING
                )
            elif (
                report.status
                is DurableMerkleOperatorStatus.INCOMPLETE
            ):
                severity = (
                    DurableMerkleHealthSeverity.ERROR
                    if incomplete
                    > self.policy.maximum_incomplete
                    else DurableMerkleHealthSeverity.WARNING
                )
            else:
                severity = (
                    DurableMerkleHealthSeverity.ERROR
                )
            self._finding(
                findings,
                severity,
                (
                    "merkle_health.finalization_"
                    f"{report.status.value}"
                ),
                (
                    "Merkle proof state for finalization is "
                    f"{report.status.value}"
                ),
                report.finalization_id,
            )

        return DurableMerkleHealthReport(
            self.policy.digest,
            ids,
            reports,
            tuple(findings),
        )

    def require(
        self,
        finalization_ids: Iterable[str],
    ) -> DurableMerkleHealthReport:
        report = self.inspect(
            finalization_ids
        )
        if not report.allowed:
            detail = (
                report.findings[0].message
                if report.findings
                else "Merkle health denied"
            )
            raise DurableMerkleHealthError(
                detail
            )
        return report
