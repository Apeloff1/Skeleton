"""Evidence-safe bridge from semantic forecasts into the predictive exchange.

Semantic interpretation can generate useful falsifiable predictions, but an
interpretation is not empirical evidence and a probability cannot be reused
across arbitrary targets. This module enforces that boundary.

A semantic forecast may enter the historical predictive exchange only when:

* it is still open;
* it is explicitly bound to one binary predictive target;
* the target domain, benchmark and target-window fingerprint still match;
* the semantic forecast existed by the request information cutoff;
* every supporting evidence id was already in request provenance;
* the supplied expert identity is independently validated by the exchange's
  lineage-aware expert registry.

The adapter therefore makes semantic forecasts scoreable without laundering
semantic readings into factual evidence.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Mapping

from ..agent.semantic_prediction import PredictionStatus, SemanticForecast, SemanticPredictionLedger
from ..agent.types import AgentContractError, json_safe, stable_fingerprint, stable_id
from .chronological_frontier import ForecastFamily
from .predictive_exchange import (
    ExpertIdentity,
    ForecastEnvelope,
    ForecastRequest,
    ForecastShape,
    PredictiveDistribution,
    PredictiveTarget,
    PredictiveTargetKind,
)


@dataclass(frozen=True, slots=True)
class SemanticTargetBinding:
    binding_id: str
    semantic_forecast_id: str
    semantic_forecast_fingerprint: str
    target_id: str
    target_fingerprint: str
    domain: str
    benchmark_id: str
    target_window_fingerprint: str
    metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        for name in (
            "binding_id",
            "semantic_forecast_id",
            "semantic_forecast_fingerprint",
            "target_id",
            "target_fingerprint",
            "benchmark_id",
            "target_window_fingerprint",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise AgentContractError(f"{name} is required")
            object.__setattr__(self, name, value)
        domain = str(self.domain).strip().casefold()
        if not domain:
            raise AgentContractError("binding domain is required")
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "binding": self.binding_id,
                "semantic_forecast": self.semantic_forecast_id,
                "semantic_fingerprint": self.semantic_forecast_fingerprint,
                "target": self.target_id,
                "target_fingerprint": self.target_fingerprint,
                "domain": self.domain,
                "benchmark": self.benchmark_id,
                "window": self.target_window_fingerprint,
                "metadata": dict(self.metadata),
            }
        )


SEMANTIC_EXCHANGE_TECHNIQUE_ID = "semantic_adapter_2026"


class SemanticForecastExpert:
    """Expose bound semantic forecasts through the ForecastExpert protocol.

    The identity is supplied by the caller and must later be registered with a
    ForecastExpertRegistry. This adapter deliberately does not invent a
    historical forecasting technique for semantic reasoning.
    """

    def __init__(
        self,
        identity: ExpertIdentity,
        ledger: SemanticPredictionLedger,
    ) -> None:
        if not isinstance(identity, ExpertIdentity):
            raise TypeError("identity must be ExpertIdentity")
        if identity.technique_id != SEMANTIC_EXCHANGE_TECHNIQUE_ID:
            raise AgentContractError(
                "semantic exchange requires the dedicated semantic_adapter_2026 technique"
            )
        if identity.family is not ForecastFamily.PROBABILISTIC:
            raise AgentContractError(
                "semantic exchange expert family must be probabilistic"
            )
        if not isinstance(ledger, SemanticPredictionLedger):
            raise TypeError("ledger must be SemanticPredictionLedger")
        self._identity = identity
        self.ledger = ledger
        self._bindings: dict[str, SemanticTargetBinding] = {}
        self._lock = threading.RLock()

    @property
    def identity(self) -> ExpertIdentity:
        return self._identity

    def bind(
        self,
        forecast: SemanticForecast,
        target: PredictiveTarget,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> SemanticTargetBinding:
        if not isinstance(forecast, SemanticForecast):
            raise TypeError("forecast must be SemanticForecast")
        if not isinstance(target, PredictiveTarget):
            raise TypeError("target must be PredictiveTarget")
        if target.kind is not PredictiveTargetKind.BINARY:
            raise AgentContractError("semantic forecasts can bind only to binary targets")
        if forecast.status is not PredictionStatus.OPEN:
            raise AgentContractError("only open semantic forecasts can be bound")
        stored = self.ledger.get(forecast.forecast_id)
        if stored is None:
            raise AgentContractError("semantic forecast must already exist in its ledger")
        if stored.fingerprint != forecast.fingerprint:
            raise AgentContractError("semantic forecast differs from ledger custody")

        binding_id = stable_id(
            "semantic-target-binding",
            {
                "expert": self.identity.fingerprint,
                "semantic_forecast": forecast.fingerprint,
                "target": target.fingerprint,
            },
            length=32,
        )
        binding = SemanticTargetBinding(
            binding_id=binding_id,
            semantic_forecast_id=forecast.forecast_id,
            semantic_forecast_fingerprint=forecast.fingerprint,
            target_id=target.target_id,
            target_fingerprint=target.fingerprint,
            domain=target.domain,
            benchmark_id=target.benchmark_id,
            target_window_fingerprint=target.target_window_fingerprint,
            metadata={
                "interpretive_only": True,
                "semantic_forecast_is_evidence": False,
                **dict(metadata or {}),
            },
        )
        with self._lock:
            existing = self._bindings.get(target.target_id)
            if existing is not None and existing.fingerprint != binding.fingerprint:
                raise AgentContractError(
                    f"semantic target already bound differently: {target.target_id}"
                )
            self._bindings[target.target_id] = binding
        return binding

    def binding(self, target_id: str) -> SemanticTargetBinding | None:
        with self._lock:
            return self._bindings.get(str(target_id))

    @staticmethod
    def _validate_target(
        binding: SemanticTargetBinding,
        target: PredictiveTarget,
    ) -> None:
        if target.kind is not PredictiveTargetKind.BINARY:
            raise AgentContractError("semantic exchange requires a binary target")
        if target.target_id != binding.target_id:
            raise AgentContractError("request target id does not match semantic binding")
        if target.fingerprint != binding.target_fingerprint:
            raise AgentContractError("request target mutated after semantic binding")
        if target.domain != binding.domain:
            raise AgentContractError("semantic binding domain mismatch")
        if target.benchmark_id != binding.benchmark_id:
            raise AgentContractError("semantic binding benchmark mismatch")
        if target.target_window_fingerprint != binding.target_window_fingerprint:
            raise AgentContractError("semantic binding target window mismatch")

    @staticmethod
    def _validate_information_custody(
        forecast: SemanticForecast,
        request: ForecastRequest,
    ) -> None:
        if forecast.created_at > request.information_cutoff:
            raise AgentContractError(
                "semantic forecast was created after request information cutoff"
            )
        missing = set(forecast.evidence_ids) - set(request.provenance_ids)
        if missing:
            raise AgentContractError(
                "semantic forecast references evidence outside request custody: "
                + ",".join(sorted(missing))
            )

    def forecast(self, request: ForecastRequest) -> ForecastEnvelope:
        if not isinstance(request, ForecastRequest):
            raise TypeError("request must be ForecastRequest")
        with self._lock:
            binding = self._bindings.get(request.target.target_id)
        if binding is None:
            raise AgentContractError("no semantic forecast is bound to request target")
        self._validate_target(binding, request.target)

        semantic = self.ledger.get(binding.semantic_forecast_id)
        if semantic is None:
            raise AgentContractError("bound semantic forecast is missing from ledger")
        if semantic.status is not PredictionStatus.OPEN:
            raise AgentContractError("bound semantic forecast is no longer open")
        if semantic.fingerprint != binding.semantic_forecast_fingerprint:
            raise AgentContractError("bound semantic forecast mutated after target binding")
        self._validate_information_custody(semantic, request)

        distribution = PredictiveDistribution(
            shape=ForecastShape.BERNOULLI,
            probability_value=semantic.probability,
            metadata={
                "semantic_forecast_id": semantic.forecast_id,
                "semantic_forecast_fingerprint": semantic.fingerprint,
                "calibration_group": semantic.calibration_group,
                "ambiguity": semantic.ambiguity,
                "epistemic_strength": semantic.epistemic_strength,
                "source_lens_keys": list(semantic.source_lens_keys),
                "interpretive_only": True,
                "semantic_forecast_is_evidence": False,
            },
        )
        forecast_id = stable_id(
            "semantic-exchange-forecast",
            {
                "request": request.fingerprint,
                "expert": self.identity.fingerprint,
                "binding": binding.fingerprint,
                "distribution": distribution.fingerprint,
            },
            length=32,
        )
        return ForecastEnvelope(
            forecast_id=forecast_id,
            request_fingerprint=request.fingerprint,
            target_id=request.target.target_id,
            expert=self.identity,
            issued_at=request.issued_at,
            information_cutoff=request.information_cutoff,
            distribution=distribution,
            evidence_ids=semantic.evidence_ids,
            diagnostics={
                "binding_id": binding.binding_id,
                "binding_fingerprint": binding.fingerprint,
                "semantic_forecast_id": semantic.forecast_id,
                "semantic_proposition": semantic.proposition,
                "semantic_horizon": semantic.horizon,
                "semantic_falsifiers": list(semantic.falsifiers),
                "semantic_forecast_is_evidence": False,
                "supporting_evidence_is_not_forecast_evidence": True,
            },
        )

    @property
    def fingerprint(self) -> str:
        with self._lock:
            bindings = [
                (target_id, binding.fingerprint)
                for target_id, binding in sorted(self._bindings.items())
            ]
        return stable_fingerprint(
            {
                "identity": self.identity.fingerprint,
                "semantic_ledger": self.ledger.fingerprint,
                "bindings": bindings,
            }
        )
