"""Deterministic selection-sensitivity analysis for Jeeves historical models.

A model that wins only under one narrow set of domain weights is a fragile
champion. This module perturbs each configured domain weight up and down by a
bounded relative amount, re-runs the exact historical selector, and reports
champion flip rate plus the base champion's regret when it loses.

No random sampling is used, so results are reproducible and fingerprintable.
The analysis is descriptive; it does not mutate the selection policy or champion
state.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from skeleton.jeeves.historical_models import (
    BenchmarkDomain,
    ChampionDecision,
    HistoricalModelRegistry,
    ModelIdentity,
    SelectionPolicy,
    canonical_fingerprint,
)


class HistoricalSensitivityError(ValueError):
    """Fail-closed sensitivity-analysis contract violation."""


@dataclass(frozen=True, slots=True)
class SensitivityPolicy:
    relative_weight_shift: float = 0.10
    min_champion_share: float = 0.80
    max_base_champion_regret: float = 0.02

    def __post_init__(self) -> None:
        for name in ("relative_weight_shift", "min_champion_share", "max_base_champion_regret"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise HistoricalSensitivityError(f"{name} must be finite numeric")
            value = float(value)
            if not 0.0 <= value <= 1.0:
                raise HistoricalSensitivityError(f"{name} must be between 0 and 1")
            object.__setattr__(self, name, value)
        if not 0.0 < self.relative_weight_shift < 1.0:
            raise HistoricalSensitivityError("relative_weight_shift must be strictly between 0 and 1")

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "relative_weight_shift": self.relative_weight_shift,
                "min_champion_share": self.min_champion_share,
                "max_base_champion_regret": self.max_base_champion_regret,
            }
        )


@dataclass(frozen=True, slots=True)
class SensitivityScenarioResult:
    scenario_id: str
    perturbed_domain: BenchmarkDomain | None
    direction: str
    weights: tuple[tuple[BenchmarkDomain, float], ...]
    decision: ChampionDecision
    winner_margin: float
    base_champion_score: float
    base_champion_regret: float

    @property
    def champion(self) -> ModelIdentity:
        return self.decision.champion.model


@dataclass(frozen=True, slots=True)
class SelectionSensitivityReport:
    base_champion: ModelIdentity
    scenarios: tuple[SensitivityScenarioResult, ...]
    champion_counts: tuple[tuple[ModelIdentity, int], ...]
    champion_share: float
    flip_rate: float
    max_base_champion_regret: float
    mean_base_champion_regret: float
    minimum_winner_margin: float
    robust: bool
    base_policy_fingerprint: str
    sensitivity_policy_fingerprint: str
    report_fingerprint: str

    @property
    def scenario_count(self) -> int:
        return len(self.scenarios)


class HistoricalSelectionSensitivityAnalyzer:
    """Stress-test champion identity under bounded domain-weight changes."""

    def __init__(
        self,
        *,
        registry: HistoricalModelRegistry,
        selection_policy: SelectionPolicy,
        sensitivity_policy: SensitivityPolicy | None = None,
    ) -> None:
        if not isinstance(registry, HistoricalModelRegistry):
            raise HistoricalSensitivityError("registry must be HistoricalModelRegistry")
        if not isinstance(selection_policy, SelectionPolicy):
            raise HistoricalSensitivityError("selection_policy must be SelectionPolicy")
        self.registry = registry
        self.selection_policy = selection_policy
        self.sensitivity_policy = sensitivity_policy or SensitivityPolicy()
        if not isinstance(self.sensitivity_policy, SensitivityPolicy):
            raise HistoricalSensitivityError("sensitivity_policy must be SensitivityPolicy")

    def analyze(self, *, models: Iterable[ModelIdentity] | None = None) -> SelectionSensitivityReport:
        scope = None if models is None else tuple(sorted(set(models)))
        if scope is not None and any(not isinstance(model, ModelIdentity) for model in scope):
            raise HistoricalSensitivityError("models must contain ModelIdentity values")

        base = self.registry.select_champion(self.selection_policy, models=scope)
        base_champion = base.champion.model
        scenarios: list[SensitivityScenarioResult] = [
            self._result_for("base", None, "base", self.selection_policy, base, base_champion)
        ]
        shift = self.sensitivity_policy.relative_weight_shift
        for domain in sorted(self.selection_policy.domain_weights, key=lambda item: item.value):
            for direction, factor in (("down", 1.0 - shift), ("up", 1.0 + shift)):
                weights = dict(self.selection_policy.domain_weights)
                weights[domain] *= factor
                scenario_policy = SelectionPolicy(
                    domain_weights=weights,
                    required_domains=self.selection_policy.required_domains,
                    minimum_sample_count=self.selection_policy.minimum_sample_count,
                    confidence_z=self.selection_policy.confidence_z,
                    max_snapshot_age_seconds=self.selection_policy.max_snapshot_age_seconds,
                    missing_domain_policy=self.selection_policy.missing_domain_policy,
                    missing_domain_score=self.selection_policy.missing_domain_score,
                    recency_half_life_seconds=self.selection_policy.recency_half_life_seconds,
                )
                decision = self.registry.select_champion(scenario_policy, models=scope)
                scenarios.append(
                    self._result_for(
                        f"{domain.value}:{direction}:{shift:.6f}",
                        domain,
                        direction,
                        scenario_policy,
                        decision,
                        base_champion,
                    )
                )

        scenario_tuple = tuple(scenarios)
        counts = Counter(item.champion for item in scenario_tuple)
        champion_counts = tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0].key)))
        base_wins = counts[base_champion]
        champion_share = base_wins / len(scenario_tuple)
        flip_rate = 1.0 - champion_share
        regrets = [item.base_champion_regret for item in scenario_tuple]
        max_regret = max(regrets)
        mean_regret = sum(regrets) / len(regrets)
        minimum_margin = min(item.winner_margin for item in scenario_tuple)
        robust = (
            champion_share + 1e-12 >= self.sensitivity_policy.min_champion_share
            and max_regret <= self.sensitivity_policy.max_base_champion_regret + 1e-12
        )
        base_policy_fingerprint = canonical_fingerprint(
            HistoricalModelRegistry._policy_payload(self.selection_policy)
        )
        payload = {
            "base_champion": base_champion.key,
            "base_policy": base_policy_fingerprint,
            "sensitivity_policy": self.sensitivity_policy.fingerprint,
            "scenarios": [
                {
                    "id": item.scenario_id,
                    "champion": item.champion.key,
                    "winner_margin": item.winner_margin,
                    "base_regret": item.base_champion_regret,
                    "weights": [(domain.value, weight) for domain, weight in item.weights],
                }
                for item in scenario_tuple
            ],
            "robust": robust,
        }
        return SelectionSensitivityReport(
            base_champion=base_champion,
            scenarios=scenario_tuple,
            champion_counts=champion_counts,
            champion_share=champion_share,
            flip_rate=flip_rate,
            max_base_champion_regret=max_regret,
            mean_base_champion_regret=mean_regret,
            minimum_winner_margin=minimum_margin,
            robust=robust,
            base_policy_fingerprint=base_policy_fingerprint,
            sensitivity_policy_fingerprint=self.sensitivity_policy.fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )

    @staticmethod
    def _result_for(
        scenario_id: str,
        perturbed_domain: BenchmarkDomain | None,
        direction: str,
        policy: SelectionPolicy,
        decision: ChampionDecision,
        base_champion: ModelIdentity,
    ) -> SensitivityScenarioResult:
        winner_score = decision.champion.conservative_score
        runner_score = decision.candidates[1].conservative_score if len(decision.candidates) > 1 else winner_score
        winner_margin = max(0.0, winner_score - runner_score)
        base_candidate = next((item for item in decision.candidates if item.model == base_champion), None)
        if base_candidate is None:
            base_score = 0.0
            regret = winner_score
        else:
            base_score = base_candidate.conservative_score
            regret = max(0.0, winner_score - base_score)
        return SensitivityScenarioResult(
            scenario_id=scenario_id,
            perturbed_domain=perturbed_domain,
            direction=direction,
            weights=tuple(sorted(policy.domain_weights.items(), key=lambda item: item[0].value)),
            decision=decision,
            winner_margin=winner_margin,
            base_champion_score=base_score,
            base_champion_regret=regret,
        )


def summarize_sensitivity(report: SelectionSensitivityReport) -> dict[str, object]:
    return {
        "base_champion": report.base_champion.key,
        "scenario_count": report.scenario_count,
        "champion_share": report.champion_share,
        "flip_rate": report.flip_rate,
        "max_base_champion_regret": report.max_base_champion_regret,
        "mean_base_champion_regret": report.mean_base_champion_regret,
        "minimum_winner_margin": report.minimum_winner_margin,
        "robust": report.robust,
        "base_policy_fingerprint": report.base_policy_fingerprint,
        "sensitivity_policy_fingerprint": report.sensitivity_policy_fingerprint,
        "report_fingerprint": report.report_fingerprint,
        "champion_counts": [
            {"model": model.key, "count": count} for model, count in report.champion_counts
        ],
        "scenarios": [
            {
                "scenario_id": item.scenario_id,
                "perturbed_domain": item.perturbed_domain.value if item.perturbed_domain is not None else None,
                "direction": item.direction,
                "champion": item.champion.key,
                "winner_margin": item.winner_margin,
                "base_champion_regret": item.base_champion_regret,
            }
            for item in report.scenarios
        ],
    }