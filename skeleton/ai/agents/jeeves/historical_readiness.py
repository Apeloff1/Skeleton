"""Composite readiness gate for Jeeves historical model promotion.

Historical readiness is intentionally conjunctive. A candidate is not considered
ready merely because it ranks first, backtests well, or has independent evidence
in isolation. This module binds assurance, cohort independence, benchmark
comparability, and optional paired shadow evidence into one deterministic final
envelope.

The gate never recomputes lower-level evidence and never mutates model state.
Every decision cites the fingerprints of the reports it consumed. Readiness
reports are self-validating: pass state, reasons, check presence, and the report
fingerprint must agree before downstream authorization can consume a report.
"""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.jeeves.historical_assurance import HistoricalAssuranceReport
from skeleton.jeeves.historical_comparability import BenchmarkComparabilityReport
from skeleton.jeeves.historical_independence import EvidenceIndependenceReport
from skeleton.jeeves.historical_models import ModelIdentity, canonical_fingerprint
from skeleton.jeeves.historical_shadow import ShadowEvaluationReport


class HistoricalReadinessError(ValueError):
    """Invalid composite readiness evidence or policy."""


def _text(name: str, value: object, maximum: int = 160) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalReadinessError(f"{name} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise HistoricalReadinessError(f"{name} exceeds {maximum} characters")
    return cleaned


def _report_payload(
    *,
    candidate: ModelIdentity,
    policy_fingerprint: str,
    checks: tuple[ReadinessCheck, ...],
    reasons: tuple[str, ...],
) -> dict[str, object]:
    return {
        "candidate": candidate.key,
        "policy": policy_fingerprint,
        "checks": [
            {
                "id": item.check_id,
                "required": item.required,
                "present": item.present,
                "passed": item.passed,
                "evidence": item.evidence_fingerprint,
            }
            for item in checks
        ],
        "reasons": list(reasons),
    }


@dataclass(frozen=True, slots=True)
class ReadinessPolicy:
    require_assurance: bool = True
    require_independence: bool = True
    require_comparability: bool = True
    require_shadow: bool = False

    def __post_init__(self) -> None:
        for name in (
            "require_assurance",
            "require_independence",
            "require_comparability",
            "require_shadow",
        ):
            if not isinstance(getattr(self, name), bool):
                raise HistoricalReadinessError(f"{name} must be boolean")
        if not (
            self.require_assurance
            or self.require_independence
            or self.require_comparability
            or self.require_shadow
        ):
            raise HistoricalReadinessError("readiness policy must require at least one evidence plane")

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "require_assurance": self.require_assurance,
                "require_independence": self.require_independence,
                "require_comparability": self.require_comparability,
                "require_shadow": self.require_shadow,
            }
        )


@dataclass(frozen=True, slots=True)
class ReadinessEvidence:
    candidate: ModelIdentity
    assurance: HistoricalAssuranceReport | None
    independence: EvidenceIndependenceReport | None
    comparability: BenchmarkComparabilityReport | None
    shadow: ShadowEvaluationReport | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, ModelIdentity):
            raise HistoricalReadinessError("candidate must be ModelIdentity")
        if self.assurance is not None and not isinstance(self.assurance, HistoricalAssuranceReport):
            raise HistoricalReadinessError("assurance must be HistoricalAssuranceReport or None")
        if self.independence is not None and not isinstance(self.independence, EvidenceIndependenceReport):
            raise HistoricalReadinessError("independence must be EvidenceIndependenceReport or None")
        if self.comparability is not None and not isinstance(self.comparability, BenchmarkComparabilityReport):
            raise HistoricalReadinessError("comparability must be BenchmarkComparabilityReport or None")
        if self.shadow is not None and not isinstance(self.shadow, ShadowEvaluationReport):
            raise HistoricalReadinessError("shadow must be ShadowEvaluationReport or None")

        if self.assurance is not None and self.assurance.candidate != self.candidate:
            raise HistoricalReadinessError("assurance candidate mismatch")
        if self.independence is not None and self.independence.champion_model != self.candidate.key:
            raise HistoricalReadinessError("independence champion mismatch")
        if self.comparability is not None and self.comparability.champion_model != self.candidate.key:
            raise HistoricalReadinessError("comparability champion mismatch")
        if self.shadow is not None and self.shadow.challenger != self.candidate:
            raise HistoricalReadinessError("shadow challenger mismatch")


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    check_id: str
    required: bool
    present: bool
    passed: bool
    evidence_fingerprint: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", _text("check_id", self.check_id))
        for name in ("required", "present", "passed"):
            if not isinstance(getattr(self, name), bool):
                raise HistoricalReadinessError(f"{name} must be boolean")
        if not self.present:
            if self.passed:
                raise HistoricalReadinessError("absent readiness evidence cannot pass")
            if self.evidence_fingerprint is not None:
                raise HistoricalReadinessError("absent readiness evidence cannot carry a fingerprint")
        elif self.evidence_fingerprint is None:
            raise HistoricalReadinessError("present readiness evidence requires a fingerprint")
        else:
            object.__setattr__(
                self,
                "evidence_fingerprint",
                _text("evidence_fingerprint", self.evidence_fingerprint, 256),
            )


@dataclass(frozen=True, slots=True)
class HistoricalReadinessReport:
    candidate: ModelIdentity
    passed: bool
    checks: tuple[ReadinessCheck, ...]
    reasons: tuple[str, ...]
    policy_fingerprint: str
    report_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, ModelIdentity):
            raise HistoricalReadinessError("candidate must be ModelIdentity")
        if not isinstance(self.passed, bool):
            raise HistoricalReadinessError("passed must be boolean")
        checks = tuple(self.checks)
        if not checks or any(not isinstance(item, ReadinessCheck) for item in checks):
            raise HistoricalReadinessError("checks must contain ReadinessCheck values")
        ids = [item.check_id for item in checks]
        if len(ids) != len(set(ids)):
            raise HistoricalReadinessError("readiness check ids must be unique")
        if not any(item.required for item in checks):
            raise HistoricalReadinessError("readiness report must contain at least one required check")
        object.__setattr__(self, "checks", checks)

        reasons = tuple(_text("reason", reason, 256) for reason in self.reasons)
        expected_reasons: list[str] = []
        for check in checks:
            if not check.required:
                continue
            if not check.present:
                expected_reasons.append(f"missing:{check.check_id}")
            elif not check.passed:
                expected_reasons.append(f"failed:{check.check_id}")
        expected = tuple(expected_reasons)
        if reasons != expected:
            raise HistoricalReadinessError("readiness reasons do not match required check outcomes")
        object.__setattr__(self, "reasons", reasons)
        if self.passed != (not expected):
            raise HistoricalReadinessError("readiness pass state does not match required check outcomes")

        policy_fingerprint = _text("policy_fingerprint", self.policy_fingerprint, 256)
        report_fingerprint = _text("report_fingerprint", self.report_fingerprint, 256)
        object.__setattr__(self, "policy_fingerprint", policy_fingerprint)
        object.__setattr__(self, "report_fingerprint", report_fingerprint)
        canonical = canonical_fingerprint(
            _report_payload(
                candidate=self.candidate,
                policy_fingerprint=policy_fingerprint,
                checks=checks,
                reasons=reasons,
            )
        )
        if report_fingerprint != canonical:
            raise HistoricalReadinessError("readiness report fingerprint does not match report content")

    @property
    def failed_count(self) -> int:
        return sum(1 for item in self.checks if item.required and not item.passed)


class HistoricalReadinessGate:
    """Require configured lower-level evidence planes to agree before readiness."""

    def __init__(self, policy: ReadinessPolicy | None = None) -> None:
        self.policy = policy or ReadinessPolicy()
        if not isinstance(self.policy, ReadinessPolicy):
            raise HistoricalReadinessError("policy must be ReadinessPolicy")

    def evaluate(self, evidence: ReadinessEvidence) -> HistoricalReadinessReport:
        if not isinstance(evidence, ReadinessEvidence):
            raise HistoricalReadinessError("evidence must be ReadinessEvidence")

        checks = (
            self._check(
                "assurance",
                required=self.policy.require_assurance,
                report=evidence.assurance,
                passed=evidence.assurance.passed if evidence.assurance is not None else False,
                fingerprint=evidence.assurance.report_fingerprint if evidence.assurance is not None else None,
            ),
            self._check(
                "independence",
                required=self.policy.require_independence,
                report=evidence.independence,
                passed=evidence.independence.passed if evidence.independence is not None else False,
                fingerprint=evidence.independence.report_fingerprint if evidence.independence is not None else None,
            ),
            self._check(
                "comparability",
                required=self.policy.require_comparability,
                report=evidence.comparability,
                passed=evidence.comparability.passed if evidence.comparability is not None else False,
                fingerprint=evidence.comparability.report_fingerprint if evidence.comparability is not None else None,
            ),
            self._check(
                "shadow",
                required=self.policy.require_shadow,
                report=evidence.shadow,
                passed=evidence.shadow.passed if evidence.shadow is not None else False,
                fingerprint=evidence.shadow.report_fingerprint if evidence.shadow is not None else None,
            ),
        )
        reasons: list[str] = []
        for check in checks:
            if not check.required:
                continue
            if not check.present:
                reasons.append(f"missing:{check.check_id}")
            elif not check.passed:
                reasons.append(f"failed:{check.check_id}")

        reason_tuple = tuple(reasons)
        policy_fingerprint = self.policy.fingerprint
        payload = _report_payload(
            candidate=evidence.candidate,
            policy_fingerprint=policy_fingerprint,
            checks=checks,
            reasons=reason_tuple,
        )
        return HistoricalReadinessReport(
            candidate=evidence.candidate,
            passed=not reason_tuple,
            checks=checks,
            reasons=reason_tuple,
            policy_fingerprint=policy_fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )

    @staticmethod
    def _check(
        check_id: str,
        *,
        required: bool,
        report: object | None,
        passed: bool,
        fingerprint: str | None,
    ) -> ReadinessCheck:
        present = report is not None
        return ReadinessCheck(
            check_id=check_id,
            required=required,
            present=present,
            passed=bool(passed) if present else False,
            evidence_fingerprint=fingerprint,
        )


def summarize_readiness(report: HistoricalReadinessReport) -> dict[str, object]:
    return {
        "candidate": report.candidate.key,
        "passed": report.passed,
        "failed_count": report.failed_count,
        "reasons": list(report.reasons),
        "policy_fingerprint": report.policy_fingerprint,
        "report_fingerprint": report.report_fingerprint,
        "checks": [
            {
                "check_id": item.check_id,
                "required": item.required,
                "present": item.present,
                "passed": item.passed,
                "evidence_fingerprint": item.evidence_fingerprint,
            }
            for item in report.checks
        ],
    }