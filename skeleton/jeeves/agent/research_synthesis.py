"""Anti-collapse hypothesis synthesis contracts for Jeeves.

Generative models can produce many hypotheses that are only stylistic variants
of one idea.  This module prevents that failure mode by validating a candidate
hypothesis set before it can enter a falsification tournament.

The gate requires mechanism diversity, a null/baseline alternative, predictive
coverage across probes, and measurable predictive separation.  It does not
score prose quality.  Only explicit structure and divergent predictions count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .hypothesis_tournament import (
    CompetingHypothesis,
    DiscriminatingProbe,
    HypothesisPrediction,
    HypothesisTournament,
    TournamentPolicy,
)
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


class SynthesisSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class HypothesisProposal:
    hypothesis_id: str
    statement: str
    mechanism_family: str
    prior_weight: float
    predictions: tuple[HypothesisPrediction, ...]
    is_null: bool = False
    assumptions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "hypothesis_id",
            require_id("hypothesis_id", self.hypothesis_id),
        )
        object.__setattr__(
            self,
            "statement",
            bounded_text("statement", self.statement, maximum=8192),
        )
        object.__setattr__(
            self,
            "mechanism_family",
            require_id("mechanism_family", self.mechanism_family),
        )
        object.__setattr__(
            self,
            "prior_weight",
            probability("prior_weight", self.prior_weight),
        )
        predictions = tuple(self.predictions)
        if not predictions:
            raise AgentContractError("proposal requires at least one prediction")
        if any(not isinstance(item, HypothesisPrediction) for item in predictions):
            raise AgentContractError("predictions must contain HypothesisPrediction")
        ids = [item.probe_id for item in predictions]
        if len(ids) != len(set(ids)):
            raise AgentContractError("proposal contains duplicate probe predictions")
        object.__setattr__(
            self,
            "predictions",
            tuple(sorted(predictions, key=lambda item: item.probe_id)),
        )
        if not isinstance(self.is_null, bool):
            raise AgentContractError("is_null must be boolean")
        object.__setattr__(
            self,
            "assumptions",
            tuple(
                bounded_text("assumption", item, maximum=2048)
                for item in self.assumptions
            ),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            tuple(
                sorted(
                    set(
                        require_id("evidence_ref", item)
                        for item in self.evidence_refs
                    )
                )
            ),
        )
        object.__setattr__(
            self,
            "provenance",
            tuple(
                sorted(
                    set(
                        require_id("provenance", item)
                        for item in self.provenance
                    )
                )
            ),
        )
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "hypothesis_id": self.hypothesis_id,
                "statement": self.statement,
                "mechanism_family": self.mechanism_family,
                "prior_weight": self.prior_weight,
                "predictions": [item.fingerprint for item in self.predictions],
                "is_null": self.is_null,
                "assumptions": self.assumptions,
                "evidence_refs": self.evidence_refs,
                "provenance": self.provenance,
                "metadata": self.metadata,
            }
        )

    def to_competing_hypothesis(self) -> CompetingHypothesis:
        return CompetingHypothesis(
            hypothesis_id=self.hypothesis_id,
            statement=self.statement,
            prior_weight=self.prior_weight,
            predictions=self.predictions,
            assumptions=self.assumptions,
            evidence_refs=self.evidence_refs,
            provenance=self.provenance,
            metadata={
                **dict(self.metadata),
                "mechanism_family": self.mechanism_family,
                "is_null": self.is_null,
            },
        )


@dataclass(frozen=True, slots=True)
class HypothesisSynthesisPolicy:
    minimum_hypotheses: int = 3
    minimum_mechanism_families: int = 3
    require_null_hypothesis: bool = True
    minimum_probe_coverage: float = 0.75
    minimum_pairwise_separation: float = 0.20
    minimum_discriminating_probes: int = 1
    maximum_shared_assumption_fraction: float = 0.80
    require_provenance: bool = True

    def __post_init__(self) -> None:
        for name in (
            "minimum_hypotheses",
            "minimum_mechanism_families",
            "minimum_discriminating_probes",
        ):
            object.__setattr__(
                self,
                name,
                positive_int(name, getattr(self, name), maximum=10_000),
            )
        for name in (
            "minimum_probe_coverage",
            "minimum_pairwise_separation",
            "maximum_shared_assumption_fraction",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in ("require_null_hypothesis", "require_provenance"):
            if not isinstance(getattr(self, name), bool):
                raise AgentContractError(f"{name} must be boolean")


@dataclass(frozen=True, slots=True)
class SynthesisFinding:
    finding_id: str
    severity: SynthesisSeverity
    code: str
    message: str
    observed: Any = None
    required: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", require_id("finding_id", self.finding_id))
        if not isinstance(self.severity, SynthesisSeverity):
            object.__setattr__(self, "severity", SynthesisSeverity(str(self.severity)))
        object.__setattr__(self, "code", require_id("code", self.code))
        object.__setattr__(
            self,
            "message",
            bounded_text("message", self.message, maximum=4096),
        )
        object.__setattr__(self, "observed", json_safe(self.observed))
        object.__setattr__(self, "required", json_safe(self.required))


@dataclass(frozen=True, slots=True)
class ProbeSeparation:
    probe_id: str
    maximum_total_variation: float
    mean_total_variation: float
    prediction_coverage: float
    discriminating: bool
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SynthesisReport:
    accepted: bool
    proposals: tuple[HypothesisProposal, ...]
    findings: tuple[SynthesisFinding, ...]
    probe_separation: tuple[ProbeSeparation, ...]
    mechanism_families: tuple[str, ...]
    null_hypothesis_ids: tuple[str, ...]
    fingerprint: str

    @property
    def errors(self) -> tuple[SynthesisFinding, ...]:
        return tuple(
            item for item in self.findings
            if item.severity is SynthesisSeverity.ERROR
        )

    @property
    def warnings(self) -> tuple[SynthesisFinding, ...]:
        return tuple(
            item for item in self.findings
            if item.severity is SynthesisSeverity.WARNING
        )


class HypothesisSynthesisGate:
    """Reject redundant or non-falsifiable hypothesis sets before research."""

    def __init__(
        self,
        *,
        policy: HypothesisSynthesisPolicy | None = None,
    ) -> None:
        self.policy = policy or HypothesisSynthesisPolicy()

    def assess(
        self,
        proposals: Sequence[HypothesisProposal],
        probes: Sequence[DiscriminatingProbe],
    ) -> SynthesisReport:
        checked = tuple(sorted(proposals, key=lambda item: item.hypothesis_id))
        checked_probes = tuple(sorted(probes, key=lambda item: item.probe_id))
        if not checked_probes:
            raise AgentContractError("synthesis assessment requires probes")
        if len({item.hypothesis_id for item in checked}) != len(checked):
            raise AgentContractError("duplicate hypothesis_id")
        findings: list[SynthesisFinding] = []

        self._minimum(
            findings,
            "hypothesis-count",
            len(checked),
            self.policy.minimum_hypotheses,
            "too few competing hypotheses",
        )
        families = tuple(sorted({item.mechanism_family for item in checked}))
        self._minimum(
            findings,
            "mechanism-diversity",
            len(families),
            self.policy.minimum_mechanism_families,
            "hypothesis set lacks mechanism diversity",
        )
        null_ids = tuple(
            item.hypothesis_id for item in checked if item.is_null
        )
        if self.policy.require_null_hypothesis and not null_ids:
            self._finding(
                findings,
                SynthesisSeverity.ERROR,
                "missing-null",
                "a null or baseline hypothesis is required",
                observed=[],
                required="at least one null hypothesis",
            )

        if self.policy.require_provenance:
            missing = tuple(
                item.hypothesis_id for item in checked
                if not item.provenance
            )
            if missing:
                self._finding(
                    findings,
                    SynthesisSeverity.ERROR,
                    "missing-provenance",
                    "all hypotheses require proposal provenance",
                    observed=list(missing),
                    required=[],
                )

        shared_fraction = self._shared_assumption_fraction(checked)
        if shared_fraction > self.policy.maximum_shared_assumption_fraction:
            self._finding(
                findings,
                SynthesisSeverity.ERROR,
                "shared-assumption-collapse",
                "hypotheses share too much assumption debt",
                observed=shared_fraction,
                required=self.policy.maximum_shared_assumption_fraction,
            )
        else:
            self._finding(
                findings,
                SynthesisSeverity.INFO,
                "shared-assumption-ok",
                "shared assumption fraction is bounded",
                observed=shared_fraction,
                required=self.policy.maximum_shared_assumption_fraction,
            )

        separations = tuple(
            self._probe_separation(probe, checked)
            for probe in checked_probes
        )
        low_coverage = tuple(
            item.probe_id
            for item in separations
            if item.prediction_coverage < self.policy.minimum_probe_coverage
        )
        if low_coverage:
            self._finding(
                findings,
                SynthesisSeverity.ERROR,
                "prediction-coverage",
                "candidate hypotheses do not cover enough probes",
                observed=list(low_coverage),
                required=self.policy.minimum_probe_coverage,
            )
        discriminating = tuple(
            item.probe_id for item in separations if item.discriminating
        )
        self._minimum(
            findings,
            "discriminating-probes",
            len(discriminating),
            self.policy.minimum_discriminating_probes,
            "too few probes materially separate hypotheses",
        )

        accepted = not any(
            item.severity is SynthesisSeverity.ERROR
            for item in findings
        )
        fingerprint = stable_fingerprint(
            {
                "proposals": [item.fingerprint for item in checked],
                "probes": [item.fingerprint for item in checked_probes],
                "findings": [
                    (
                        item.severity.value,
                        item.code,
                        item.observed,
                        item.required,
                    )
                    for item in findings
                ],
                "separations": [item.fingerprint for item in separations],
                "accepted": accepted,
            }
        )
        return SynthesisReport(
            accepted=accepted,
            proposals=checked,
            findings=tuple(findings),
            probe_separation=separations,
            mechanism_families=families,
            null_hypothesis_ids=null_ids,
            fingerprint=fingerprint,
        )

    def build_tournament(
        self,
        proposals: Sequence[HypothesisProposal],
        probes: Sequence[DiscriminatingProbe],
        *,
        tournament_policy: TournamentPolicy | None = None,
        decision_impact: float = 1.0,
    ) -> tuple[SynthesisReport, HypothesisTournament]:
        report = self.assess(proposals, probes)
        if not report.accepted:
            codes = ",".join(item.code for item in report.errors)
            raise AgentContractError(
                f"hypothesis synthesis gate rejected candidate set: {codes}"
            )
        tournament = HypothesisTournament(
            tuple(
                proposal.to_competing_hypothesis()
                for proposal in report.proposals
            ),
            probes,
            policy=tournament_policy,
            decision_impact=decision_impact,
        )
        return report, tournament

    def _probe_separation(
        self,
        probe: DiscriminatingProbe,
        proposals: Sequence[HypothesisProposal],
    ) -> ProbeSeparation:
        distributions: list[Mapping[str, float]] = []
        for proposal in proposals:
            prediction = next(
                (
                    item for item in proposal.predictions
                    if item.probe_id == probe.probe_id
                ),
                None,
            )
            if prediction is None:
                continue
            if set(prediction.distribution) != set(probe.outcome_support):
                raise AgentContractError(
                    f"prediction support mismatch for "
                    f"{proposal.hypothesis_id}/{probe.probe_id}"
                )
            distributions.append(prediction.distribution)
        coverage = len(distributions) / max(1, len(proposals))
        pairwise: list[float] = []
        for index, left in enumerate(distributions):
            for right in distributions[index + 1:]:
                pairwise.append(
                    0.5
                    * sum(
                        abs(left[outcome] - right[outcome])
                        for outcome in probe.outcome_support
                    )
                )
        maximum = max(pairwise, default=0.0)
        mean = sum(pairwise) / len(pairwise) if pairwise else 0.0
        discriminating = (
            coverage >= self.policy.minimum_probe_coverage
            and maximum >= self.policy.minimum_pairwise_separation
        )
        fingerprint = stable_fingerprint(
            {
                "probe_id": probe.probe_id,
                "maximum": maximum,
                "mean": mean,
                "coverage": coverage,
                "discriminating": discriminating,
            }
        )
        return ProbeSeparation(
            probe_id=probe.probe_id,
            maximum_total_variation=maximum,
            mean_total_variation=mean,
            prediction_coverage=coverage,
            discriminating=discriminating,
            fingerprint=fingerprint,
        )

    @staticmethod
    def _shared_assumption_fraction(
        proposals: Sequence[HypothesisProposal],
    ) -> float:
        if not proposals:
            return 0.0
        sets = [set(item.assumptions) for item in proposals]
        union = set().union(*sets)
        if not union:
            return 0.0
        intersection = set.intersection(*sets) if sets else set()
        return len(intersection) / len(union)

    @staticmethod
    def _minimum(
        findings: list[SynthesisFinding],
        code: str,
        observed: int | float,
        required: int | float,
        message: str,
    ) -> None:
        if observed >= required:
            HypothesisSynthesisGate._finding(
                findings,
                SynthesisSeverity.INFO,
                f"{code}-ok",
                f"{message}: threshold satisfied",
                observed=observed,
                required=required,
            )
        else:
            HypothesisSynthesisGate._finding(
                findings,
                SynthesisSeverity.ERROR,
                code,
                message,
                observed=observed,
                required=required,
            )

    @staticmethod
    def _finding(
        findings: list[SynthesisFinding],
        severity: SynthesisSeverity,
        code: str,
        message: str,
        *,
        observed: Any,
        required: Any,
    ) -> None:
        finding_id = stable_id(
            "hypothesis-synthesis",
            {
                "severity": severity.value,
                "code": code,
                "observed": observed,
                "required": required,
            },
            length=28,
        )
        findings.append(
            SynthesisFinding(
                finding_id=finding_id,
                severity=severity,
                code=code,
                message=message,
                observed=observed,
                required=required,
            )
        )
