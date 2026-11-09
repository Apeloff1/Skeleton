"""Research assurance and epistemic completion certificates for Jeeves.

This module defines when Jeeves is allowed to stop researching a decision-
relevant question.  A dominant hypothesis is not enough.  Resolution requires
evidence coverage, source independence, low contradiction, adequate freshness,
predictive track record, and bounded residual hypothesis entropy.

The result is an auditable completion certificate rather than a vague "I am
confident" signal.  High-impact questions automatically receive stricter gates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .types import (
    AgentContractError,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class ResearchResolution(str, Enum):
    CONTINUE = "continue"
    PROVISIONAL = "provisional"
    RESOLVED = "resolved"
    BLOCKED = "blocked"


class AssuranceSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ResearchStopPolicy:
    minimum_evidence_coverage: float = 0.80
    minimum_freshness: float = 0.70
    maximum_contradiction: float = 0.20
    minimum_independent_sources: int = 2
    maximum_effective_hypotheses: float = 1.35
    minimum_leading_posterior: float = 0.85
    minimum_predictive_trials: int = 2
    maximum_mean_brier: float = 0.30
    maximum_mean_surprise_bits: float = 2.50
    maximum_unresolved_assumptions: int = 0
    high_impact_threshold: float = 0.80
    high_impact_coverage_bonus: float = 0.10
    high_impact_source_bonus: int = 1
    high_impact_posterior_bonus: float = 0.08
    allow_provisional_without_prediction_history: bool = True

    def __post_init__(self) -> None:
        for name in (
            "minimum_evidence_coverage",
            "minimum_freshness",
            "maximum_contradiction",
            "minimum_leading_posterior",
            "maximum_mean_brier",
            "high_impact_threshold",
            "high_impact_coverage_bonus",
            "high_impact_posterior_bonus",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in (
            "minimum_independent_sources",
            "minimum_predictive_trials",
        ):
            object.__setattr__(
                self,
                name,
                positive_int(name, getattr(self, name), maximum=1_000_000),
            )
        if (
            isinstance(self.maximum_unresolved_assumptions, bool)
            or not isinstance(self.maximum_unresolved_assumptions, int)
            or self.maximum_unresolved_assumptions < 0
        ):
            raise AgentContractError(
                "maximum_unresolved_assumptions must be non-negative integer"
            )
        if (
            isinstance(self.high_impact_source_bonus, bool)
            or not isinstance(self.high_impact_source_bonus, int)
            or self.high_impact_source_bonus < 0
        ):
            raise AgentContractError("high_impact_source_bonus must be non-negative integer")
        for name in ("maximum_effective_hypotheses", "maximum_mean_surprise_bits"):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class ResearchEvidenceSummary:
    obligation_id: str
    decision_impact: float
    evidence_coverage: float
    freshness: float
    contradiction_strength: float
    independent_source_count: int
    leading_hypothesis_id: str | None = None
    leading_posterior: float = 0.0
    effective_hypotheses: float = 1.0
    unresolved_assumptions: tuple[str, ...] = ()
    predictive_brier_scores: tuple[float, ...] = ()
    predictive_surprise_bits: tuple[float, ...] = ()
    open_gap_ids: tuple[str, ...] = ()
    unresolved_high_severity_gap_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "obligation_id",
            require_id("obligation_id", self.obligation_id),
        )
        for name in (
            "decision_impact",
            "evidence_coverage",
            "freshness",
            "contradiction_strength",
            "leading_posterior",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if (
            isinstance(self.independent_source_count, bool)
            or not isinstance(self.independent_source_count, int)
            or self.independent_source_count < 0
        ):
            raise AgentContractError("independent_source_count must be non-negative integer")
        value = finite_number("effective_hypotheses", self.effective_hypotheses)
        if value < 1.0:
            raise AgentContractError("effective_hypotheses must be >= 1")
        object.__setattr__(self, "effective_hypotheses", value)
        if self.leading_hypothesis_id is not None:
            object.__setattr__(
                self,
                "leading_hypothesis_id",
                require_id("leading_hypothesis_id", self.leading_hypothesis_id),
            )
        object.__setattr__(
            self,
            "unresolved_assumptions",
            tuple(
                bounded_text("unresolved_assumption", item, maximum=2048)
                for item in self.unresolved_assumptions
            ),
        )
        brier: list[float] = []
        for score in self.predictive_brier_scores:
            value = finite_number("predictive_brier_score", score)
            if value < 0 or value > 2.0:
                raise AgentContractError("predictive Brier score must be in [0, 2]")
            brier.append(value)
        object.__setattr__(self, "predictive_brier_scores", tuple(brier))
        surprise: list[float] = []
        for score in self.predictive_surprise_bits:
            value = finite_number("predictive_surprise_bits", score)
            if value < 0:
                raise AgentContractError("predictive surprise must be non-negative")
            surprise.append(value)
        object.__setattr__(self, "predictive_surprise_bits", tuple(surprise))
        for name in ("open_gap_ids", "unresolved_high_severity_gap_ids", "evidence_refs"):
            values = tuple(
                sorted(
                    set(
                        require_id(name[:-1] if name.endswith("s") else name, item)
                        for item in getattr(self, name)
                    )
                )
            )
            object.__setattr__(self, name, values)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def predictive_trials(self) -> int:
        return min(
            len(self.predictive_brier_scores),
            len(self.predictive_surprise_bits),
        ) if self.predictive_surprise_bits else len(self.predictive_brier_scores)

    @property
    def mean_brier(self) -> float | None:
        if not self.predictive_brier_scores:
            return None
        return sum(self.predictive_brier_scores) / len(self.predictive_brier_scores)

    @property
    def mean_surprise_bits(self) -> float | None:
        if not self.predictive_surprise_bits:
            return None
        return sum(self.predictive_surprise_bits) / len(self.predictive_surprise_bits)

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self.as_json())

    def as_json(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "decision_impact": self.decision_impact,
            "evidence_coverage": self.evidence_coverage,
            "freshness": self.freshness,
            "contradiction_strength": self.contradiction_strength,
            "independent_source_count": self.independent_source_count,
            "leading_hypothesis_id": self.leading_hypothesis_id,
            "leading_posterior": self.leading_posterior,
            "effective_hypotheses": self.effective_hypotheses,
            "unresolved_assumptions": list(self.unresolved_assumptions),
            "predictive_brier_scores": list(self.predictive_brier_scores),
            "predictive_surprise_bits": list(self.predictive_surprise_bits),
            "open_gap_ids": list(self.open_gap_ids),
            "unresolved_high_severity_gap_ids": list(
                self.unresolved_high_severity_gap_ids
            ),
            "evidence_refs": list(self.evidence_refs),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class AssuranceFinding:
    finding_id: str
    severity: AssuranceSeverity
    code: str
    message: str
    observed: Any = None
    required: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", require_id("finding_id", self.finding_id))
        if not isinstance(self.severity, AssuranceSeverity):
            object.__setattr__(self, "severity", AssuranceSeverity(str(self.severity)))
        object.__setattr__(self, "code", require_id("code", self.code))
        object.__setattr__(
            self,
            "message",
            bounded_text("message", self.message, maximum=4096),
        )
        object.__setattr__(self, "observed", json_safe(self.observed))
        object.__setattr__(self, "required", json_safe(self.required))


@dataclass(frozen=True, slots=True)
class CompletionCertificate:
    certificate_id: str
    obligation_id: str
    resolution: ResearchResolution
    accepted: bool
    provisional: bool
    high_impact: bool
    findings: tuple[AssuranceFinding, ...]
    proof_debt: tuple[str, ...]
    evidence_fingerprint: str
    policy_fingerprint: str
    fingerprint: str

    @property
    def errors(self) -> tuple[AssuranceFinding, ...]:
        return tuple(
            item for item in self.findings
            if item.severity is AssuranceSeverity.ERROR
        )

    @property
    def warnings(self) -> tuple[AssuranceFinding, ...]:
        return tuple(
            item for item in self.findings
            if item.severity is AssuranceSeverity.WARNING
        )

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "CompletionCertificate":
        payload = json_safe(dict(value))
        findings = tuple(
            AssuranceFinding(
                finding_id=item["finding_id"],
                severity=AssuranceSeverity(item["severity"]),
                code=item["code"],
                message=item["message"],
                observed=item.get("observed"),
                required=item.get("required"),
            )
            for item in payload.get("findings", ())
        )
        certificate = cls(
            certificate_id=payload["certificate_id"],
            obligation_id=payload["obligation_id"],
            resolution=ResearchResolution(payload["resolution"]),
            accepted=bool(payload["accepted"]),
            provisional=bool(payload["provisional"]),
            high_impact=bool(payload["high_impact"]),
            findings=findings,
            proof_debt=tuple(payload.get("proof_debt", ())),
            evidence_fingerprint=payload["evidence_fingerprint"],
            policy_fingerprint=payload["policy_fingerprint"],
            fingerprint=payload["fingerprint"],
        )
        expected = stable_fingerprint(
            {
                "certificate": certificate.certificate_id,
                "resolution": certificate.resolution.value,
                "accepted": certificate.accepted,
                "provisional": certificate.provisional,
                "high_impact": certificate.high_impact,
                "findings": [
                    (
                        item.severity.value,
                        item.code,
                        item.observed,
                        item.required,
                    )
                    for item in certificate.findings
                ],
                "proof_debt": tuple(sorted(set(certificate.proof_debt))),
            }
        )
        if expected != certificate.fingerprint:
            raise AgentContractError(
                "research completion certificate fingerprint mismatch"
            )
        return certificate

    def as_json(self) -> dict[str, Any]:
        return {
            "certificate_id": self.certificate_id,
            "obligation_id": self.obligation_id,
            "resolution": self.resolution.value,
            "accepted": self.accepted,
            "provisional": self.provisional,
            "high_impact": self.high_impact,
            "findings": [
                {
                    "finding_id": item.finding_id,
                    "severity": item.severity.value,
                    "code": item.code,
                    "message": item.message,
                    "observed": item.observed,
                    "required": item.required,
                }
                for item in self.findings
            ],
            "proof_debt": list(self.proof_debt),
            "evidence_fingerprint": self.evidence_fingerprint,
            "policy_fingerprint": self.policy_fingerprint,
            "fingerprint": self.fingerprint,
        }


class ResearchAssuranceGate:
    """Fail-closed stop condition for decision-relevant Jeeves research."""

    def __init__(self, *, policy: ResearchStopPolicy | None = None) -> None:
        self.policy = policy or ResearchStopPolicy()

    def evaluate(self, summary: ResearchEvidenceSummary) -> CompletionCertificate:
        if not isinstance(summary, ResearchEvidenceSummary):
            raise TypeError("summary must be ResearchEvidenceSummary")
        high_impact = summary.decision_impact >= self.policy.high_impact_threshold
        coverage_required = min(
            1.0,
            self.policy.minimum_evidence_coverage
            + (self.policy.high_impact_coverage_bonus if high_impact else 0.0),
        )
        sources_required = (
            self.policy.minimum_independent_sources
            + (self.policy.high_impact_source_bonus if high_impact else 0)
        )
        posterior_required = min(
            0.999999,
            self.policy.minimum_leading_posterior
            + (self.policy.high_impact_posterior_bonus if high_impact else 0.0),
        )
        findings: list[AssuranceFinding] = []
        debt: list[str] = []

        self._minimum(
            findings,
            debt,
            code="coverage",
            observed=summary.evidence_coverage,
            required=coverage_required,
            message="evidence coverage is below the research stop threshold",
        )
        self._minimum(
            findings,
            debt,
            code="freshness",
            observed=summary.freshness,
            required=self.policy.minimum_freshness,
            message="evidence freshness is below the research stop threshold",
        )
        self._maximum(
            findings,
            debt,
            code="contradiction",
            observed=summary.contradiction_strength,
            required=self.policy.maximum_contradiction,
            message="unresolved contradiction remains too strong",
        )
        self._minimum(
            findings,
            debt,
            code="source-independence",
            observed=summary.independent_source_count,
            required=sources_required,
            message="too few independent evidence sources",
        )
        self._minimum(
            findings,
            debt,
            code="leading-posterior",
            observed=summary.leading_posterior,
            required=posterior_required,
            message="no hypothesis has earned enough posterior support",
        )
        self._maximum(
            findings,
            debt,
            code="hypothesis-entropy",
            observed=summary.effective_hypotheses,
            required=self.policy.maximum_effective_hypotheses,
            message="too many effective hypotheses remain live",
        )
        self._maximum(
            findings,
            debt,
            code="assumption-debt",
            observed=len(summary.unresolved_assumptions),
            required=self.policy.maximum_unresolved_assumptions,
            message="untested assumptions remain",
        )

        if summary.unresolved_high_severity_gap_ids:
            self._finding(
                findings,
                AssuranceSeverity.ERROR,
                "frontier-gap",
                "high-severity epistemic gaps remain unresolved",
                observed=list(summary.unresolved_high_severity_gap_ids),
                required=[],
            )
            debt.append("resolve high-severity epistemic gaps")

        predictive_trials = len(summary.predictive_brier_scores)
        predictive_ready = predictive_trials >= self.policy.minimum_predictive_trials
        if not predictive_ready:
            severity = (
                AssuranceSeverity.WARNING
                if self.policy.allow_provisional_without_prediction_history
                else AssuranceSeverity.ERROR
            )
            self._finding(
                findings,
                severity,
                "prediction-history",
                "insufficient precommitted predictive trials",
                observed=predictive_trials,
                required=self.policy.minimum_predictive_trials,
            )
            debt.append(
                f"collect {max(0, self.policy.minimum_predictive_trials - predictive_trials)} "
                "additional precommitted predictive trials"
            )
        else:
            mean_brier = summary.mean_brier
            if mean_brier is not None:
                self._maximum(
                    findings,
                    debt,
                    code="predictive-brier",
                    observed=mean_brier,
                    required=self.policy.maximum_mean_brier,
                    message="predictive Brier score is too weak for resolution",
                )
            mean_surprise = summary.mean_surprise_bits
            if mean_surprise is not None:
                self._maximum(
                    findings,
                    debt,
                    code="predictive-surprise",
                    observed=mean_surprise,
                    required=self.policy.maximum_mean_surprise_bits,
                    message="recent predictions remain too surprising",
                )

        has_errors = any(
            item.severity is AssuranceSeverity.ERROR for item in findings
        )
        has_warnings = any(
            item.severity is AssuranceSeverity.WARNING for item in findings
        )
        if has_errors:
            resolution = ResearchResolution.CONTINUE
            accepted = False
            provisional = False
        elif has_warnings:
            resolution = ResearchResolution.PROVISIONAL
            accepted = False
            provisional = True
        else:
            resolution = ResearchResolution.RESOLVED
            accepted = True
            provisional = False

        policy_payload = {
            name: getattr(self.policy, name)
            for name in self.policy.__dataclass_fields__
        }
        policy_fingerprint = stable_fingerprint(policy_payload)
        certificate_id = stable_id(
            "research-certificate",
            {
                "obligation": summary.obligation_id,
                "evidence": summary.fingerprint,
                "policy": policy_fingerprint,
                "resolution": resolution.value,
            },
            length=30,
        )
        fingerprint = stable_fingerprint(
            {
                "certificate": certificate_id,
                "resolution": resolution.value,
                "accepted": accepted,
                "provisional": provisional,
                "high_impact": high_impact,
                "findings": [
                    (
                        item.severity.value,
                        item.code,
                        item.observed,
                        item.required,
                    )
                    for item in findings
                ],
                "proof_debt": tuple(sorted(set(debt))),
            }
        )
        return CompletionCertificate(
            certificate_id=certificate_id,
            obligation_id=summary.obligation_id,
            resolution=resolution,
            accepted=accepted,
            provisional=provisional,
            high_impact=high_impact,
            findings=tuple(findings),
            proof_debt=tuple(sorted(set(debt))),
            evidence_fingerprint=summary.fingerprint,
            policy_fingerprint=policy_fingerprint,
            fingerprint=fingerprint,
        )

    def _minimum(
        self,
        findings: list[AssuranceFinding],
        debt: list[str],
        *,
        code: str,
        observed: float | int,
        required: float | int,
        message: str,
    ) -> None:
        if observed >= required:
            self._finding(
                findings,
                AssuranceSeverity.INFO,
                f"{code}-ok",
                f"{message}: threshold satisfied",
                observed=observed,
                required=required,
            )
            return
        self._finding(
            findings,
            AssuranceSeverity.ERROR,
            code,
            message,
            observed=observed,
            required=required,
        )
        debt.append(f"{code}: raise {observed} to at least {required}")

    def _maximum(
        self,
        findings: list[AssuranceFinding],
        debt: list[str],
        *,
        code: str,
        observed: float | int,
        required: float | int,
        message: str,
    ) -> None:
        if observed <= required:
            self._finding(
                findings,
                AssuranceSeverity.INFO,
                f"{code}-ok",
                f"{message}: threshold satisfied",
                observed=observed,
                required=required,
            )
            return
        self._finding(
            findings,
            AssuranceSeverity.ERROR,
            code,
            message,
            observed=observed,
            required=required,
        )
        debt.append(f"{code}: reduce {observed} to at most {required}")

    @staticmethod
    def _finding(
        findings: list[AssuranceFinding],
        severity: AssuranceSeverity,
        code: str,
        message: str,
        *,
        observed: Any,
        required: Any,
    ) -> None:
        finding_id = stable_id(
            "research-assurance",
            {
                "severity": severity.value,
                "code": code,
                "observed": observed,
                "required": required,
            },
            length=28,
        )
        findings.append(
            AssuranceFinding(
                finding_id=finding_id,
                severity=severity,
                code=code,
                message=message,
                observed=observed,
                required=required,
            )
        )
