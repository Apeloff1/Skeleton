"""Conservative arbitration for semantic-lens forecasts.

Semantic forecasts may share a proposition while coming from different lenses.
This module lets Jeeves combine only those forecasts whose proposition and
horizon are textually identical after whitespace/case normalization.

It deliberately does *not* perform semantic-entailment clustering. Different
wording may encode different targets, and combining those automatically would
manufacture certainty. Multi-lens interaction forecasts are also left separate
because they do not have one unambiguous family/reliability identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .lens_fusion import LensFusionEngine, LensFusionResult, LensSignal
from .semantic_governance import SemanticLensGovernanceSnapshot
from .semantic_lenses import SemanticLensRegistry
from .semantic_prediction import PredictionStatus, SemanticForecast
from .types import stable_fingerprint, stable_id


@dataclass(frozen=True, slots=True)
class SemanticForecastFusion:
    fusion_id: str
    proposition: str
    horizon: str
    forecast_ids: tuple[str, ...]
    lens_keys: tuple[str, ...]
    result: LensFusionResult
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SemanticForecastFusionSnapshot:
    fusions: tuple[SemanticForecastFusion, ...]
    excluded_forecast_ids: tuple[str, ...]
    fingerprint: str

    @property
    def abstaining_fusion_ids(self) -> tuple[str, ...]:
        return tuple(
            item.fusion_id for item in self.fusions if item.result.abstain
        )


class SemanticForecastFusionEngine:
    """Fuse compatible lens forecasts with governance-weighted reliability."""

    def __init__(
        self,
        registry: SemanticLensRegistry,
        *,
        fusion: LensFusionEngine | None = None,
        default_reliability: float = 0.10,
    ) -> None:
        if not isinstance(registry, SemanticLensRegistry):
            raise TypeError("registry must be SemanticLensRegistry")
        if not 0.0 <= float(default_reliability) <= 1.0:
            raise ValueError("default_reliability must lie in [0,1]")
        self.registry = registry
        self.fusion = fusion or LensFusionEngine()
        self.default_reliability = float(default_reliability)

    @staticmethod
    def _target_key(forecast: SemanticForecast) -> tuple[str, str]:
        proposition = " ".join(forecast.proposition.split()).casefold()
        horizon = " ".join(forecast.horizon.split()).casefold()
        return proposition, horizon

    def _signal(
        self,
        forecast: SemanticForecast,
        governance: SemanticLensGovernanceSnapshot | None,
    ) -> LensSignal | None:
        if forecast.status is not PredictionStatus.OPEN:
            return None
        if len(forecast.source_lens_keys) != 1:
            return None
        lens_key = forecast.source_lens_keys[0]
        try:
            spec = self.registry.get(lens_key)
        except KeyError:
            return None
        reliability = self.default_reliability
        if governance is not None:
            record = governance.record_for(lens_key)
            if record is not None:
                reliability = (
                    record.domain_predictive_weight
                    if record.domain_predictive_weight is not None
                    else record.decision.predictive_weight
                )
        return LensSignal.from_forecast(
            forecast,
            family=spec.family,
            reliability=reliability,
        )

    def fuse(
        self,
        forecasts: Sequence[SemanticForecast],
        *,
        governance: SemanticLensGovernanceSnapshot | None = None,
    ) -> SemanticForecastFusionSnapshot:
        groups: dict[tuple[str, str], list[tuple[SemanticForecast, LensSignal]]] = {}
        excluded: list[str] = []
        for forecast in forecasts:
            if not isinstance(forecast, SemanticForecast):
                raise TypeError("forecasts must contain SemanticForecast values")
            signal = self._signal(forecast, governance)
            if signal is None:
                excluded.append(forecast.forecast_id)
                continue
            groups.setdefault(self._target_key(forecast), []).append(
                (forecast, signal)
            )

        fusions: list[SemanticForecastFusion] = []
        for target_key, rows in sorted(groups.items()):
            rows.sort(key=lambda row: row[0].forecast_id)
            source_forecasts = [row[0] for row in rows]
            signals = [row[1] for row in rows]
            result = self.fusion.fuse(signals, base_rate=0.5)
            proposition = source_forecasts[0].proposition
            horizon = source_forecasts[0].horizon
            forecast_ids = tuple(item.forecast_id for item in source_forecasts)
            lens_keys = tuple(
                sorted(
                    {
                        key
                        for item in source_forecasts
                        for key in item.source_lens_keys
                    }
                )
            )
            fusion_id = stable_id(
                "semantic-forecast-fusion",
                {
                    "target": target_key,
                    "forecasts": forecast_ids,
                    "result": result.fingerprint,
                },
                length=30,
            )
            fingerprint = stable_fingerprint(
                {
                    "fusion_id": fusion_id,
                    "proposition": proposition,
                    "horizon": horizon,
                    "forecast_ids": forecast_ids,
                    "lens_keys": lens_keys,
                    "result": result.fingerprint,
                }
            )
            fusions.append(
                SemanticForecastFusion(
                    fusion_id=fusion_id,
                    proposition=proposition,
                    horizon=horizon,
                    forecast_ids=forecast_ids,
                    lens_keys=lens_keys,
                    result=result,
                    fingerprint=fingerprint,
                )
            )

        snapshot_fingerprint = stable_fingerprint(
            {
                "fusions": [item.fingerprint for item in fusions],
                "excluded": sorted(excluded),
            }
        )
        return SemanticForecastFusionSnapshot(
            fusions=tuple(fusions),
            excluded_forecast_ids=tuple(sorted(set(excluded))),
            fingerprint=snapshot_fingerprint,
        )

    @property
    def fingerprint(self) -> str:
        policy = self.fusion.policy
        return stable_fingerprint(
            {
                "registry": [spec.key for spec in self.registry.all()],
                "default_reliability": self.default_reliability,
                "fusion_policy": {
                    "dependence_discount": policy.dependence_discount,
                    "maximum_family_weight": policy.maximum_family_weight,
                    "maximum_single_weight": policy.maximum_single_weight,
                    "minimum_total_weight": policy.minimum_total_weight,
                    "minimum_effective_lenses": policy.minimum_effective_lenses,
                    "conflict_threshold": policy.conflict_threshold,
                },
            }
        )


__all__ = [
    "SemanticForecastFusion",
    "SemanticForecastFusionEngine",
    "SemanticForecastFusionSnapshot",
]
