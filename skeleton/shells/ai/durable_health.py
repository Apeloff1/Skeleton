"""Policy-bound health gating over durable AI execution recovery evidence.

The durable recovery verifier can prove one finalization.  This module turns a
set of required finalizations into an operator-facing health decision suitable
for service startup and live admission.

Manual-review or corruption states always fail closed.  Missing/incomplete
finalizations may be tolerated only through an explicit bounded policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable

from skeleton.shells.ai.durable_recovery import (
    DurableRecoveryFinding,
    DurableRecoveryStatus,
    DurableSessionRecoveryReport,
    DurableSessionRecoveryVerifier,
    RecoveryFindingSeverity,
)


class DurableRecoveryHealthSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class DurableRecoveryHealthPolicy:
    max_finalizations: int = 512
    max_incomplete: int = 0
    minimum_verified: int = 0
    require_nonempty: bool = False
    reject_manual_review: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_finalizations",
            "max_incomplete",
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
        if self.max_incomplete > self.max_finalizations:
            raise ValueError(
                "max_incomplete exceeds max_finalizations"
            )
        if self.minimum_verified > self.max_finalizations:
            raise ValueError(
                "minimum_verified exceeds max_finalizations"
            )
        if not isinstance(self.require_nonempty, bool):
            raise ValueError(
                "require_nonempty must be bool"
            )
        if not isinstance(self.reject_manual_review, bool):
            raise ValueError(
                "reject_manual_review must be bool"
            )
        if not self.reject_manual_review:
            raise ValueError(
                "manual-review durable recovery may not be allowed"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "max_finalizations": self.max_finalizations,
            "max_incomplete": self.max_incomplete,
            "minimum_verified": self.minimum_verified,
            "require_nonempty": self.require_nonempty,
            "reject_manual_review": self.reject_manual_review,
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
class DurableRecoveryHealthFinding:
    severity: DurableRecoveryHealthSeverity
    code: str
    message: str
    finalization_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "severity",
            DurableRecoveryHealthSeverity(
                self.severity
            ),
        )
        if not self.code or len(self.code) > 128:
            raise ValueError(
                "invalid durable recovery health code"
            )
        if not self.message or len(self.message) > 2048:
            raise ValueError(
                "invalid durable recovery health message"
            )
        if len(self.finalization_id) > 256:
            raise ValueError(
                "durable recovery finalization_id too long"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "finalization_id": self.finalization_id,
        }


@dataclass(frozen=True)
class DurableRecoveryHealthReport:
    policy_digest: str
    finalization_ids: tuple[str, ...]
    reports: tuple[DurableSessionRecoveryReport, ...]
    findings: tuple[DurableRecoveryHealthFinding, ...]

    def __post_init__(self) -> None:
        if len(self.policy_digest) != 64:
            raise ValueError(
                "policy_digest must be SHA-256 hex"
            )
        # Opaque 64-character policy digest.
        ids = tuple(self.finalization_ids)
        if len(ids) != len(set(ids)):
            raise ValueError(
                "duplicate durable recovery finalization_id"
            )
        if tuple(sorted(ids)) != ids:
            raise ValueError(
                "durable recovery finalization_ids must be sorted"
            )
        if any(
            not item or len(item) > 256
            for item in ids
        ):
            raise ValueError(
                "invalid durable recovery finalization_id"
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
        report_ids = tuple(
            item.finalization_id
            for item in self.reports
        )
        if report_ids != ids:
            raise ValueError(
                "durable recovery reports do not match requested ids"
            )

    @property
    def verified(self) -> int:
        return sum(
            item.status
            is DurableRecoveryStatus.VERIFIED
            for item in self.reports
        )

    @property
    def incomplete(self) -> int:
        return sum(
            item.status
            is DurableRecoveryStatus.INCOMPLETE
            for item in self.reports
        )

    @property
    def manual_review(self) -> int:
        return sum(
            item.status
            is DurableRecoveryStatus.MANUAL_REVIEW
            for item in self.reports
        )

    @property
    def errors(self) -> int:
        return sum(
            item.severity
            is DurableRecoveryHealthSeverity.ERROR
            for item in self.findings
        )

    @property
    def warnings(self) -> int:
        return sum(
            item.severity
            is DurableRecoveryHealthSeverity.WARNING
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


class DurableRecoveryHealthError(RuntimeError):
    pass


class DurableRecoveryHealthGuard:
    """Verify a bounded required finalization set and apply health policy."""

    def __init__(
        self,
        verifier: DurableSessionRecoveryVerifier,
        policy: DurableRecoveryHealthPolicy | None = None,
    ) -> None:
        if not isinstance(
            verifier,
            DurableSessionRecoveryVerifier,
        ):
            raise TypeError(
                "verifier must be DurableSessionRecoveryVerifier"
            )
        self.verifier = verifier
        self.policy = (
            policy or DurableRecoveryHealthPolicy()
        )

    @staticmethod
    def _ids(
        finalization_ids: Iterable[str],
        *,
        maximum: int,
    ) -> tuple[str, ...]:
        values = tuple(finalization_ids)
        if len(values) > maximum:
            raise ValueError(
                "durable recovery finalization bound exceeded"
            )
        if any(
            not isinstance(item, str)
            or not item
            or len(item) > 256
            for item in values
        ):
            raise ValueError(
                "invalid durable recovery finalization_id"
            )
        if len(values) != len(set(values)):
            raise ValueError(
                "duplicate durable recovery finalization_id"
            )
        return tuple(sorted(values))

    def _verify_one(
        self,
        finalization_id: str,
    ) -> DurableSessionRecoveryReport:
        try:
            return self.verifier.verify(
                finalization_id
            )
        except Exception as exc:
            # Health admission is a fail-closed operational boundary. A
            # backend/probe exception is represented as manual-review evidence
            # so lifecycle callers receive a deterministic denial report.
            return DurableSessionRecoveryReport(
                finalization_id,
                "",
                DurableRecoveryStatus.MANUAL_REVIEW,
                "",
                None,
                None,
                None,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                None,
                (
                    DurableRecoveryFinding(
                        "durable_health.probe_error",
                        RecoveryFindingSeverity.CORRUPTION,
                        (
                            "durable recovery verifier raised "
                            f"{type(exc).__name__}"
                        ),
                    ),
                ),
            )

    def inspect(
        self,
        finalization_ids: Iterable[str],
    ) -> DurableRecoveryHealthReport:
        ids = self._ids(
            finalization_ids,
            maximum=self.policy.max_finalizations,
        )
        reports = tuple(
            self._verify_one(item)
            for item in ids
        )
        findings: list[
            DurableRecoveryHealthFinding
        ] = []

        if self.policy.require_nonempty and not ids:
            findings.append(
                DurableRecoveryHealthFinding(
                    DurableRecoveryHealthSeverity.ERROR,
                    "durable_recovery.empty_required_set",
                    (
                        "durable recovery policy requires at least "
                        "one finalization"
                    ),
                )
            )

        verified = sum(
            item.status
            is DurableRecoveryStatus.VERIFIED
            for item in reports
        )
        incomplete = sum(
            item.status
            is DurableRecoveryStatus.INCOMPLETE
            for item in reports
        )
        manual = sum(
            item.status
            is DurableRecoveryStatus.MANUAL_REVIEW
            for item in reports
        )

        if verified < self.policy.minimum_verified:
            findings.append(
                DurableRecoveryHealthFinding(
                    DurableRecoveryHealthSeverity.ERROR,
                    "durable_recovery.minimum_verified",
                    (
                        "verified durable finalizations below "
                        f"required minimum: {verified}<"
                        f"{self.policy.minimum_verified}"
                    ),
                )
            )

        if incomplete > self.policy.max_incomplete:
            findings.append(
                DurableRecoveryHealthFinding(
                    DurableRecoveryHealthSeverity.ERROR,
                    "durable_recovery.incomplete_bound",
                    (
                        "incomplete durable finalizations exceed "
                        f"policy bound: {incomplete}>"
                        f"{self.policy.max_incomplete}"
                    ),
                )
            )
        elif incomplete:
            findings.append(
                DurableRecoveryHealthFinding(
                    DurableRecoveryHealthSeverity.WARNING,
                    "durable_recovery.incomplete_tolerated",
                    (
                        f"{incomplete} incomplete durable finalization"
                        " state(s) are within configured tolerance"
                    ),
                )
            )

        if manual:
            findings.append(
                DurableRecoveryHealthFinding(
                    DurableRecoveryHealthSeverity.ERROR,
                    "durable_recovery.manual_review",
                    (
                        f"{manual} durable finalization state(s) "
                        "require manual review"
                    ),
                )
            )

        for report in reports:
            if report.status is DurableRecoveryStatus.VERIFIED:
                continue
            severity = (
                DurableRecoveryHealthSeverity.ERROR
                if (
                    report.status
                    is DurableRecoveryStatus.MANUAL_REVIEW
                    or incomplete > self.policy.max_incomplete
                )
                else DurableRecoveryHealthSeverity.WARNING
            )
            findings.append(
                DurableRecoveryHealthFinding(
                    severity,
                    (
                        "durable_recovery.finalization_"
                        f"{report.status.value}"
                    ),
                    (
                        "durable recovery finalization is "
                        f"{report.status.value}"
                    ),
                    report.finalization_id,
                )
            )

        return DurableRecoveryHealthReport(
            self.policy.digest,
            ids,
            reports,
            tuple(findings),
        )

    def require(
        self,
        finalization_ids: Iterable[str],
    ) -> DurableRecoveryHealthReport:
        report = self.inspect(
            finalization_ids
        )
        if not report.allowed:
            detail = (
                report.findings[0].message
                if report.findings
                else "durable recovery health denied"
            )
            raise DurableRecoveryHealthError(
                detail
            )
        return report
