"""Scientific validation plane for cinematic, literary, ludic and semantic lenses.

A rich interpretive catalog is dangerous if every coherent reading is treated
as equally useful. This module makes each lens earn influence through recorded
predictions, calibration, transfer across domains, independent repetitions and
negative controls.

The key separation is:

    observation/evidence -> semantic hypothesis -> falsifiable forecast
      -> observed outcome -> lens reliability update

No amount of narrative coherence can skip that chain. A lens can remain useful
for hypothesis generation while being restricted or rejected as a predictor.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .probability_lenses import brier_score, expected_calibration_error, log_loss, wilson_interval
from .semantic_lenses import SemanticFinding
from .types import AgentContractError, bounded_text, json_safe, positive_int, probability, stable_fingerprint, stable_id


class ScientificLensStatus(str, Enum):
    SHADOW = "shadow"
    CANDIDATE = "candidate"
    ACTIVE = "active"
    RESTRICTED = "restricted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class LensOutcomeTrial:
    trial_id: str
    lens_key: str
    probability: float
    outcome: bool
    domain: str
    independent_run: str
    proposition: str
    negative_control: bool = False
    source_finding_id: str | None = None
    source_forecast_id: str | None = None
    source_forecast_fingerprint: str | None = None
    observation_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.trial_id).strip():
            raise AgentContractError("trial_id is required")
        key = str(self.lens_key).strip().casefold()
        if not key:
            raise AgentContractError("lens_key is required")
        object.__setattr__(self, "lens_key", key)
        object.__setattr__(self, "probability", probability("trial probability", self.probability))
        if not isinstance(self.outcome, bool):
            raise AgentContractError("trial outcome must be boolean")
        domain = str(self.domain).strip().casefold()
        run = str(self.independent_run).strip()
        if not domain or not run:
            raise AgentContractError("domain and independent_run are required")
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "independent_run", run)
        object.__setattr__(self, "proposition", bounded_text("trial proposition", self.proposition, maximum=8192))
        if self.source_finding_id is not None:
            object.__setattr__(
                self,
                "source_finding_id",
                str(self.source_finding_id).strip(),
            )
        if (self.source_forecast_id is None) != (
            self.source_forecast_fingerprint is None
        ):
            raise AgentContractError(
                "source forecast id and fingerprint must be supplied together"
            )
        if self.source_forecast_id is not None:
            forecast_id = str(self.source_forecast_id).strip()
            forecast_fingerprint = str(
                self.source_forecast_fingerprint
            ).strip()
            if not forecast_id or not forecast_fingerprint:
                raise AgentContractError(
                    "source forecast id/fingerprint cannot be empty"
                )
            object.__setattr__(self, "source_forecast_id", forecast_id)
            object.__setattr__(
                self,
                "source_forecast_fingerprint",
                forecast_fingerprint,
            )
        object.__setattr__(self, "observation_ids", tuple(sorted({str(x) for x in self.observation_ids if str(x)})))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "lens": self.lens_key,
                "probability": self.probability,
                "outcome": self.outcome,
                "domain": self.domain,
                "run": self.independent_run,
                "proposition": self.proposition,
                "negative_control": self.negative_control,
                "finding": self.source_finding_id,
                "forecast": self.source_forecast_id,
                "forecast_fingerprint": self.source_forecast_fingerprint,
                "observations": self.observation_ids,
                "evidence": self.evidence_ids,
            }
        )


@dataclass(frozen=True, slots=True)
class JuxtapositionTrial:
    trial_id: str
    lens_key: str
    target_fingerprint: str
    context_a_fingerprint: str
    context_b_fingerprint: str
    predicted_change_probability: float
    observed_interpretation_changed: bool
    independent_run: str
    domain: str = "film"
    same_target_verified: bool = True
    negative_control: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "trial_id",
            "lens_key",
            "target_fingerprint",
            "context_a_fingerprint",
            "context_b_fingerprint",
            "independent_run",
        ):
            if not str(getattr(self, name)).strip():
                raise AgentContractError(f"{name} is required")
        object.__setattr__(self, "lens_key", str(self.lens_key).strip().casefold())
        object.__setattr__(self, "domain", str(self.domain).strip().casefold())
        object.__setattr__(
            self,
            "predicted_change_probability",
            probability("predicted_change_probability", self.predicted_change_probability),
        )
        if not isinstance(self.observed_interpretation_changed, bool):
            raise AgentContractError("observed_interpretation_changed must be boolean")
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    def as_outcome_trial(self) -> LensOutcomeTrial:
        return LensOutcomeTrial(
            trial_id=self.trial_id,
            lens_key=self.lens_key,
            probability=self.predicted_change_probability,
            outcome=self.observed_interpretation_changed,
            domain=self.domain,
            independent_run=self.independent_run,
            proposition="Changing adjacent context changes interpretation of the unchanged target.",
            negative_control=self.negative_control,
            metadata={
                **dict(self.metadata),
                "same_target_verified": self.same_target_verified,
                "target_fingerprint": self.target_fingerprint,
                "context_a_fingerprint": self.context_a_fingerprint,
                "context_b_fingerprint": self.context_b_fingerprint,
                "paired_context_trial": True,
            },
        )


@dataclass(frozen=True, slots=True)
class ScientificLensPolicy:
    minimum_trials: int = 24
    minimum_independent_runs: int = 3
    minimum_domains_for_transfer: int = 2
    maximum_brier: float = 0.25
    maximum_ece: float = 0.15
    minimum_brier_gain_over_base_rate: float = 0.01
    maximum_negative_control_positive_rate: float = 0.20
    minimum_control_trials: int = 5
    minimum_transfer_trials_per_domain: int = 4
    reject_brier: float = 0.40
    reject_ece: float = 0.30

    def __post_init__(self) -> None:
        for name in (
            "minimum_trials",
            "minimum_independent_runs",
            "minimum_domains_for_transfer",
            "minimum_control_trials",
            "minimum_transfer_trials_per_domain",
        ):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1_000_000))
        for name in (
            "maximum_brier",
            "maximum_ece",
            "minimum_brier_gain_over_base_rate",
            "maximum_negative_control_positive_rate",
            "reject_brier",
            "reject_ece",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if self.reject_brier < self.maximum_brier or self.reject_ece < self.maximum_ece:
            raise AgentContractError("reject thresholds must be at least as permissive as active thresholds")


@dataclass(frozen=True, slots=True)
class DomainCalibration:
    domain: str
    count: int
    brier: float
    log_loss: float
    ece: float
    mean_probability: float
    empirical_rate: float

    def as_json(self) -> dict[str, float | int | str]:
        return {
            "domain": self.domain,
            "count": self.count,
            "brier": self.brier,
            "log_loss": self.log_loss,
            "ece": self.ece,
            "mean_probability": self.mean_probability,
            "empirical_rate": self.empirical_rate,
        }


@dataclass(frozen=True, slots=True)
class ScientificLensReport:
    lens_key: str
    status: ScientificLensStatus
    trial_count: int
    independent_runs: int
    domains: tuple[str, ...]
    brier: float
    baseline_brier: float
    brier_gain: float
    log_loss: float
    ece: float
    mean_probability: float
    empirical_rate: float
    control_count: int
    negative_control_positive_rate: float | None
    domain_calibration: tuple[DomainCalibration, ...]
    reasons: tuple[str, ...]
    predictive_weight: float
    fingerprint: str


class ScientificLensLab:
    """Append-only outcome ledger and conservative semantic-lens promotion gate."""

    def __init__(self, *, policy: ScientificLensPolicy | None = None, max_trials: int = 1_000_000) -> None:
        self.policy = policy or ScientificLensPolicy()
        self.max_trials = positive_int("max_trials", max_trials, maximum=10_000_000)
        self._trials: dict[str, LensOutcomeTrial] = {}
        self._by_lens: defaultdict[str, list[str]] = defaultdict(list)

    def record(self, trial: LensOutcomeTrial | JuxtapositionTrial) -> LensOutcomeTrial:
        normalized = trial.as_outcome_trial() if isinstance(trial, JuxtapositionTrial) else trial
        if not isinstance(normalized, LensOutcomeTrial):
            raise TypeError("trial must be LensOutcomeTrial or JuxtapositionTrial")
        existing = self._trials.get(normalized.trial_id)
        if existing is not None:
            if existing.fingerprint != normalized.fingerprint:
                raise AgentContractError(f"trial id collision: {normalized.trial_id}")
            return existing
        if len(self._trials) >= self.max_trials:
            raise AgentContractError("scientific lens trial ledger is full")
        self._trials[normalized.trial_id] = normalized
        self._by_lens[normalized.lens_key].append(normalized.trial_id)
        return normalized

    def record_finding_outcome(
        self,
        finding: SemanticFinding,
        *,
        probability_value: float,
        outcome: bool,
        domain: str,
        independent_run: str,
        negative_control: bool = False,
        source_forecast_id: str | None = None,
        source_forecast_fingerprint: str | None = None,
    ) -> LensOutcomeTrial:
        if not isinstance(finding, SemanticFinding):
            raise TypeError("finding must be SemanticFinding")
        trial_id = stable_id(
            "lens-trial",
            {
                "finding": finding.fingerprint,
                "probability": probability_value,
                "outcome": bool(outcome),
                "domain": domain,
                "run": independent_run,
                "control": negative_control,
                "forecast": source_forecast_id,
                "forecast_fingerprint": source_forecast_fingerprint,
            },
            length=32,
        )
        trial = LensOutcomeTrial(
            trial_id=trial_id,
            lens_key=finding.lens_key,
            probability=probability_value,
            outcome=bool(outcome),
            domain=domain,
            independent_run=independent_run,
            proposition=finding.prediction or finding.interpretation,
            negative_control=negative_control,
            source_finding_id=finding.finding_id,
            source_forecast_id=source_forecast_id,
            source_forecast_fingerprint=source_forecast_fingerprint,
            observation_ids=finding.observation_ids,
            evidence_ids=finding.evidence_ids,
            metadata={
                "finding_status": finding.status.value,
                "finding_confidence": finding.confidence,
                "finding_ambiguity": finding.ambiguity,
            },
        )
        return self.record(trial)

    def trials(self, lens_key: str) -> tuple[LensOutcomeTrial, ...]:
        key = str(lens_key).strip().casefold()
        return tuple(self._trials[trial_id] for trial_id in self._by_lens.get(key, ()))

    @staticmethod
    def _domain_report(domain: str, trials: Sequence[LensOutcomeTrial]) -> DomainCalibration:
        probabilities = [item.probability for item in trials]
        outcomes = [item.outcome for item in trials]
        mean_p = sum(probabilities) / len(probabilities)
        rate = sum(outcomes) / len(outcomes)
        bins = min(10, max(1, len(trials)))
        return DomainCalibration(
            domain=domain,
            count=len(trials),
            brier=brier_score(probabilities, outcomes),
            log_loss=log_loss(probabilities, outcomes),
            ece=expected_calibration_error(probabilities, outcomes, bins=bins),
            mean_probability=mean_p,
            empirical_rate=rate,
        )

    def report(self, lens_key: str) -> ScientificLensReport:
        key = str(lens_key).strip().casefold()
        trials = list(self.trials(key))
        if not trials:
            raise AgentContractError(f"no scientific trials for lens: {key}")
        probabilities = [item.probability for item in trials]
        outcomes = [item.outcome for item in trials]
        count = len(trials)
        empirical_rate = sum(outcomes) / count
        mean_probability = sum(probabilities) / count
        brier = brier_score(probabilities, outcomes)
        baseline_brier = brier_score([empirical_rate] * count, outcomes)
        brier_gain = baseline_brier - brier
        ece = expected_calibration_error(probabilities, outcomes, bins=min(10, count))
        ll = log_loss(probabilities, outcomes)
        runs = {item.independent_run for item in trials}
        domains = sorted({item.domain for item in trials})
        controls = [item for item in trials if item.negative_control]
        control_positive = None
        if controls:
            control_positive = sum(item.outcome for item in controls) / len(controls)
        domain_reports = tuple(
            self._domain_report(domain, [item for item in trials if item.domain == domain]) for domain in domains
        )
        transfer_domains = sum(
            report.count >= self.policy.minimum_transfer_trials_per_domain for report in domain_reports
        )

        reasons: list[str] = []
        if brier >= self.policy.reject_brier or ece >= self.policy.reject_ece:
            status = ScientificLensStatus.REJECTED
            reasons.append("predictive calibration exceeds rejection threshold")
        elif (
            controls
            and len(controls) >= self.policy.minimum_control_trials
            and control_positive is not None
            and control_positive > self.policy.maximum_negative_control_positive_rate
        ):
            status = ScientificLensStatus.RESTRICTED
            reasons.append("negative controls indicate an over-sensitive lens")
        elif count < self.policy.minimum_trials or len(runs) < self.policy.minimum_independent_runs:
            status = ScientificLensStatus.SHADOW
            reasons.append("insufficient replicated outcome data")
        elif brier > self.policy.maximum_brier or ece > self.policy.maximum_ece:
            status = ScientificLensStatus.RESTRICTED
            reasons.append("lens has enough data but insufficient calibration")
        elif brier_gain < self.policy.minimum_brier_gain_over_base_rate:
            status = ScientificLensStatus.CANDIDATE
            reasons.append("lens does not yet beat a base-rate forecast by the required margin")
        elif transfer_domains < self.policy.minimum_domains_for_transfer:
            status = ScientificLensStatus.CANDIDATE
            reasons.append("lens has not yet demonstrated cross-domain transfer")
        else:
            status = ScientificLensStatus.ACTIVE
            reasons.append("lens is replicated, calibrated, base-rate improving, and transfer-tested")

        status_cap = {
            ScientificLensStatus.SHADOW: 0.20,
            ScientificLensStatus.CANDIDATE: 0.35,
            ScientificLensStatus.ACTIVE: 0.60,
            ScientificLensStatus.RESTRICTED: 0.15,
            ScientificLensStatus.REJECTED: 0.0,
        }[status]
        calibration_quality = max(0.0, 1.0 - min(1.0, 2.0 * brier + ece))
        replication_quality = min(1.0, count / max(1, self.policy.minimum_trials)) * min(
            1.0, len(runs) / max(1, self.policy.minimum_independent_runs)
        )
        predictive_weight = min(
            status_cap,
            status_cap * (0.55 * calibration_quality + 0.45 * replication_quality),
        )

        payload = {
            "lens": key,
            "status": status.value,
            "count": count,
            "runs": sorted(runs),
            "domains": domains,
            "brier": brier,
            "baseline_brier": baseline_brier,
            "brier_gain": brier_gain,
            "ece": ece,
            "log_loss": ll,
            "controls": len(controls),
            "control_positive": control_positive,
            "domain_reports": [report.as_json() for report in domain_reports],
            "reasons": reasons,
            "predictive_weight": predictive_weight,
        }
        return ScientificLensReport(
            lens_key=key,
            status=status,
            trial_count=count,
            independent_runs=len(runs),
            domains=tuple(domains),
            brier=brier,
            baseline_brier=baseline_brier,
            brier_gain=brier_gain,
            log_loss=ll,
            ece=ece,
            mean_probability=mean_probability,
            empirical_rate=empirical_rate,
            control_count=len(controls),
            negative_control_positive_rate=control_positive,
            domain_calibration=domain_reports,
            reasons=tuple(reasons),
            predictive_weight=predictive_weight,
            fingerprint=stable_fingerprint(payload),
        )

    def routing_weight(self, lens_key: str, *, default_shadow_weight: float = 0.10) -> float:
        key = str(lens_key).strip().casefold()
        if not self._by_lens.get(key):
            return probability("default_shadow_weight", default_shadow_weight)
        return self.report(key).predictive_weight

    def status_map(self) -> Mapping[str, ScientificLensStatus]:
        return {key: self.report(key).status for key in sorted(self._by_lens)}

    def juxtaposition_effect_report(self, lens_key: str) -> Mapping[str, Any]:
        """Return paired-context diagnostics without manufacturing a causal claim."""

        trials = [item for item in self.trials(lens_key) if item.metadata.get("paired_context_trial")]
        if not trials:
            raise AgentContractError("no paired juxtaposition trials")
        changed = sum(item.outcome for item in trials)
        lower, upper = wilson_interval(changed, len(trials))
        controls = [item for item in trials if item.negative_control]
        control_rate = None if not controls else sum(item.outcome for item in controls) / len(controls)
        return {
            "lens_key": str(lens_key).casefold(),
            "trial_count": len(trials),
            "observed_change_rate": changed / len(trials),
            "wilson_95": (lower, upper),
            "negative_control_count": len(controls),
            "negative_control_change_rate": control_rate,
            "causal_claim_authorized": False,
            "fingerprint": stable_fingerprint([(item.trial_id, item.fingerprint) for item in trials]),
        }

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            [(trial_id, trial.fingerprint) for trial_id, trial in sorted(self._trials.items())]
        )
