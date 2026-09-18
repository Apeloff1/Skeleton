from __future__ import annotations

import pytest

from skeleton.jeeves.agent.semantic_prediction import (
    PredictionStatus,
    SemanticForecast,
    SemanticPredictionLedger,
)
from skeleton.jeeves.agent.types import AgentContractError
from skeleton.jeeves.science.chronological_frontier import (
    ForecastFamily,
    default_prediction_lineage,
)
from skeleton.jeeves.science.predictive_exchange import (
    ExpertIdentity,
    ForecastExpertRegistry,
    ForecastRequest,
    ForecastShape,
    PredictiveTarget,
    PredictiveTargetKind,
)
from skeleton.jeeves.science.semantic_exchange import SemanticForecastExpert


def _semantic_forecast(*, created_at: float = 100.0) -> SemanticForecast:
    return SemanticForecast(
        forecast_id="semantic-1",
        proposition="The next scene will repeat the warning motif after the player breaks sequence.",
        probability=0.72,
        created_at=created_at,
        horizon="next-scene",
        source_finding_ids=("finding-1",),
        source_lens_keys=("intellectual_montage", "sequence_break"),
        observation_ids=("obs-1", "obs-2"),
        evidence_ids=("ev-1",),
        falsifiers=("No warning motif appears in the next scene.",),
        calibration_group="semantic:film-game",
        ambiguity=0.40,
        epistemic_strength=0.65,
        metadata={"is_evidence": False},
    )


def _target(*, window: str = "scene-window-v1") -> PredictiveTarget:
    return PredictiveTarget(
        target_id="target-1",
        kind=PredictiveTargetKind.BINARY,
        target_time=200.0,
        domain="interactive-narrative",
        benchmark_id="semantic-ablation-v1",
        target_window_fingerprint=window,
    )


def _expert(ledger: SemanticPredictionLedger) -> SemanticForecastExpert:
    identity = ExpertIdentity(
        expert_id="semantic-bayesian-adapter-v1",
        technique_id="bayes_inverse_1763",
        model_version="semantic-adapter-v1",
        family=ForecastFamily.BAYESIAN,
        code_fingerprint="code-v1",
        configuration_fingerprint="config-v1",
        training_data_fingerprint="no-training-data",
        metadata={"semantic_interpretive_adapter": True},
    )
    expert = SemanticForecastExpert(identity, ledger)
    registry = ForecastExpertRegistry(default_prediction_lineage())
    registry.register(expert)
    return expert


def _request(target: PredictiveTarget, *, provenance=("ev-1",), cutoff: float = 140.0) -> ForecastRequest:
    return ForecastRequest(
        request_id="request-1",
        target=target,
        issued_at=150.0,
        information_cutoff=cutoff,
        as_of_year=2026,
        provenance_ids=tuple(provenance),
    )


def test_semantic_forecast_enters_exchange_as_target_bound_non_evidence_probability() -> None:
    ledger = SemanticPredictionLedger(clock=lambda: 100.0)
    semantic = ledger.add(_semantic_forecast())
    expert = _expert(ledger)
    binding = expert.bind(semantic, _target())

    envelope = expert.forecast(_request(_target()))

    assert binding.semantic_forecast_id == semantic.forecast_id
    assert envelope.distribution.shape is ForecastShape.BERNOULLI
    assert envelope.distribution.probability_value == semantic.probability
    assert envelope.diagnostics["semantic_forecast_is_evidence"] is False
    assert envelope.distribution.metadata["interpretive_only"] is True
    assert envelope.evidence_ids == ("ev-1",)
    assert envelope.target_id == "target-1"


def test_semantic_exchange_rejects_evidence_outside_information_custody() -> None:
    ledger = SemanticPredictionLedger()
    semantic = ledger.add(_semantic_forecast())
    expert = _expert(ledger)
    expert.bind(semantic, _target())

    with pytest.raises(AgentContractError, match="outside request custody"):
        expert.forecast(_request(_target(), provenance=()))


def test_semantic_exchange_rejects_target_window_drift() -> None:
    ledger = SemanticPredictionLedger()
    semantic = ledger.add(_semantic_forecast())
    expert = _expert(ledger)
    expert.bind(semantic, _target(window="scene-window-v1"))

    mutated_target = _target(window="scene-window-v2")
    with pytest.raises(AgentContractError, match="mutated after semantic binding"):
        expert.forecast(_request(mutated_target))


def test_semantic_exchange_rejects_forecast_created_after_information_cutoff() -> None:
    ledger = SemanticPredictionLedger()
    semantic = ledger.add(_semantic_forecast(created_at=145.0))
    expert = _expert(ledger)
    expert.bind(semantic, _target())

    with pytest.raises(AgentContractError, match="after request information cutoff"):
        expert.forecast(_request(_target(), cutoff=140.0))


def test_semantic_exchange_rejects_resolved_or_mutated_forecast_after_binding() -> None:
    ledger = SemanticPredictionLedger(clock=lambda: 170.0)
    semantic = ledger.add(_semantic_forecast())
    expert = _expert(ledger)
    expert.bind(semantic, _target())

    resolved = ledger.resolve(semantic.forecast_id, outcome=True, observation_id="future-obs")
    assert resolved.status is PredictionStatus.RESOLVED

    with pytest.raises(AgentContractError, match="no longer open"):
        expert.forecast(_request(_target()))


def test_semantic_exchange_refuses_continuous_target_binding() -> None:
    ledger = SemanticPredictionLedger()
    semantic = ledger.add(_semantic_forecast())
    expert = _expert(ledger)
    continuous = PredictiveTarget(
        target_id="continuous-target",
        kind=PredictiveTargetKind.CONTINUOUS,
        target_time=200.0,
        domain="interactive-narrative",
        benchmark_id="semantic-ablation-v1",
        target_window_fingerprint="window",
    )

    with pytest.raises(AgentContractError, match="only to binary targets"):
        expert.bind(semantic, continuous)
