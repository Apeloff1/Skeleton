from __future__ import annotations

import math

import pytest

from skeleton.jeeves.agent.types import AgentContractError
from skeleton.jeeves.science.chronological_frontier import ForecastFamily, default_prediction_lineage
from skeleton.jeeves.science.predictive_exchange import (
    ExpertIdentity,
    ForecastArbiter,
    ForecastExpertRegistry,
    ForecastRequest,
    ForecastShape,
    FunctionalForecastExpert,
    HistoricalEvidenceBuilder,
    HistoricalEvidencePolicy,
    PredictiveDistribution,
    PredictiveTarget,
    PredictiveTargetKind,
    PrequentialExpertRouter,
    PrequentialScoreLedger,
    RouterPolicy,
)


def _identity(expert_id: str, technique_id: str, family: ForecastFamily, *, kind: str = "continuous") -> ExpertIdentity:
    return ExpertIdentity(
        expert_id=expert_id,
        technique_id=technique_id,
        model_version="1",
        family=family,
        code_fingerprint=f"code:{expert_id}",
        configuration_fingerprint=f"config:{expert_id}",
        training_data_fingerprint=f"data:{expert_id}",
        metadata={"target_kinds": [kind]},
    )


def _continuous_request(index: int, *, issued_at: float | None = None, year: int = 2024) -> ForecastRequest:
    issued = float(index * 10 if issued_at is None else issued_at)
    return ForecastRequest(
        request_id=f"request-{index}",
        target=PredictiveTarget(
            target_id=f"target-{index}",
            kind=PredictiveTargetKind.CONTINUOUS,
            target_time=issued + 5.0,
            domain="synthetic",
            benchmark_id="benchmark-v1",
            target_window_fingerprint="window-v1",
        ),
        issued_at=issued,
        information_cutoff=issued,
        as_of_year=year,
        features={"x": index},
        provenance_ids=(f"source-{index}",),
    )


def _binary_request(index: int, *, issued_at: float | None = None, year: int = 2024) -> ForecastRequest:
    issued = float(index * 10 if issued_at is None else issued_at)
    return ForecastRequest(
        request_id=f"binary-request-{index}",
        target=PredictiveTarget(
            target_id=f"binary-target-{index}",
            kind=PredictiveTargetKind.BINARY,
            target_time=issued + 5.0,
            domain="binary",
            benchmark_id="binary-benchmark",
            target_window_fingerprint="binary-window",
        ),
        issued_at=issued,
        information_cutoff=issued,
        as_of_year=year,
    )


def _continuous_expert(identity: ExpertIdentity, *, bias: float = 0.0, sd: float = 1.0) -> FunctionalForecastExpert:
    return FunctionalForecastExpert(
        identity,
        lambda request: PredictiveDistribution(
            shape=ForecastShape.GAUSSIAN,
            mean=float(request.features.get("x", 0.0)) + bias,
            standard_deviation=sd,
        ),
    )


def test_request_refuses_future_information_and_post_target_issuance() -> None:
    target = PredictiveTarget(
        target_id="t",
        kind=PredictiveTargetKind.CONTINUOUS,
        target_time=10.0,
        domain="test",
        benchmark_id="b",
        target_window_fingerprint="w",
    )
    with pytest.raises(AgentContractError, match="information_cutoff"):
        ForecastRequest("r", target, issued_at=5.0, information_cutoff=6.0, as_of_year=2024)
    with pytest.raises(AgentContractError, match="precede target_time"):
        ForecastRequest("r", target, issued_at=10.0, information_cutoff=9.0, as_of_year=2024)


def test_registry_rejects_expert_whose_family_disagrees_with_lineage() -> None:
    registry = ForecastExpertRegistry(default_prediction_lineage())
    wrong = _identity("wrong", "holt_smoothing_1957", ForecastFamily.NEURAL)
    expert = _continuous_expert(wrong)
    with pytest.raises(AgentContractError, match="does not match lineage family"):
        registry.register(expert)


def test_historical_availability_filters_future_experts() -> None:
    registry = ForecastExpertRegistry(default_prediction_lineage())
    holt = _continuous_expert(_identity("holt", "holt_smoothing_1957", ForecastFamily.SMOOTHING))
    timesfm = _continuous_expert(_identity("timesfm", "timesfm_2024", ForecastFamily.FOUNDATION))
    registry.register(holt)
    registry.register(timesfm)
    ids_2023 = {expert.identity.expert_id for expert in registry.eligible(2023, kind=PredictiveTargetKind.CONTINUOUS)}
    ids_2024 = {expert.identity.expert_id for expert in registry.eligible(2024, kind=PredictiveTargetKind.CONTINUOUS)}
    assert "holt" in ids_2023
    assert "timesfm" not in ids_2023
    assert {"holt", "timesfm"}.issubset(ids_2024)


def test_forecast_custody_requires_exact_request_and_target_identity() -> None:
    ledger = PrequentialScoreLedger()
    identity = _identity("kalman", "kalman_1960", ForecastFamily.STATE_SPACE)
    expert = _continuous_expert(identity)
    request = _continuous_request(1)
    envelope = expert.forecast(request)
    ledger.record(request, envelope)
    altered = _continuous_request(2)
    with pytest.raises(AgentContractError, match="request fingerprint mismatch"):
        ledger.record(altered, envelope)


def test_binary_scoring_uses_brier_and_log_loss_after_target_resolves() -> None:
    registry = ForecastExpertRegistry(default_prediction_lineage())
    identity = _identity("bayes", "bayes_inverse_1763", ForecastFamily.BAYESIAN, kind="binary")
    expert = FunctionalForecastExpert(
        identity,
        lambda request: PredictiveDistribution(shape=ForecastShape.BERNOULLI, probability_value=0.8),
    )
    registry.register(expert)
    request = _binary_request(1)
    ledger = PrequentialScoreLedger()
    envelope = expert.forecast(request)
    ledger.record(request, envelope)
    with pytest.raises(AgentContractError, match="before target_time"):
        ledger.resolve(envelope.forecast_id, True, resolved_at=request.target.target_time - 0.1)
    score = ledger.resolve(envelope.forecast_id, True, resolved_at=request.target.target_time)
    assert score.brier == pytest.approx(0.04)
    assert score.log_score_loss == pytest.approx(-math.log(0.8))
    assert score.absolute_error == pytest.approx(0.2)


def test_gaussian_scoring_records_proper_score_crps_and_standardized_residual() -> None:
    identity = _identity("kalman", "kalman_1960", ForecastFamily.STATE_SPACE)
    expert = _continuous_expert(identity, bias=0.0, sd=2.0)
    request = _continuous_request(3)
    ledger = PrequentialScoreLedger()
    envelope = expert.forecast(request)
    ledger.record(request, envelope)
    score = ledger.resolve(envelope.forecast_id, 32.0, resolved_at=request.target.target_time + 1.0)
    assert score.absolute_error == pytest.approx(2.0)
    assert score.squared_error == pytest.approx(4.0)
    assert score.standardized_residual == pytest.approx(1.0)
    assert score.log_score_loss is not None and score.log_score_loss > 0.0
    assert score.gaussian_crps is not None and score.gaussian_crps > 0.0


def test_future_resolved_score_is_invisible_to_earlier_routing_snapshot() -> None:
    registry = ForecastExpertRegistry(default_prediction_lineage())
    holt = _continuous_expert(_identity("holt", "holt_smoothing_1957", ForecastFamily.SMOOTHING), bias=0.0)
    kalman = _continuous_expert(_identity("kalman", "kalman_1960", ForecastFamily.STATE_SPACE), bias=5.0)
    registry.register(holt)
    registry.register(kalman)
    ledger = PrequentialScoreLedger()

    for index in range(1, 6):
        request = _continuous_request(index)
        for expert in (holt, kalman):
            envelope = expert.forecast(request)
            ledger.record(request, envelope)
            ledger.resolve(envelope.forecast_id, float(index), resolved_at=request.target.target_time + 1.0)

    late_request = _continuous_request(7, issued_at=70.0)
    late = kalman.forecast(late_request)
    ledger.record(late_request, late)
    ledger.resolve(late.forecast_id, 1000.0, resolved_at=101.0)

    # Caps are intentionally disabled for this test so a newly available bad
    # score can change the numerical weight instead of being hidden by a floor
    # induced by cap redistribution.
    router = PrequentialExpertRouter(
        registry,
        ledger,
        policy=RouterPolicy(minimum_resolved_scores=5, expert_weight_cap=1.0, family_weight_cap=1.0),
    )
    before = router.snapshot(_continuous_request(20, issued_at=100.0))
    after = router.snapshot(_continuous_request(21, issued_at=102.0))
    before_kalman = next(item for item in before.weights if item.expert_id == "kalman")
    after_kalman = next(item for item in after.weights if item.expert_id == "kalman")
    assert before_kalman.resolved_scores_used == 5
    assert after_kalman.resolved_scores_used == 6
    assert after_kalman.weight < before_kalman.weight


def test_arbiter_preserves_component_forecasts_and_epistemic_disagreement() -> None:
    registry = ForecastExpertRegistry(default_prediction_lineage())
    holt = _continuous_expert(_identity("holt", "holt_smoothing_1957", ForecastFamily.SMOOTHING), bias=-2.0)
    kalman = _continuous_expert(_identity("kalman", "kalman_1960", ForecastFamily.STATE_SPACE), bias=2.0)
    registry.register(holt)
    registry.register(kalman)
    ledger = PrequentialScoreLedger()
    router = PrequentialExpertRouter(
        registry,
        ledger,
        policy=RouterPolicy(minimum_resolved_scores=5, expert_weight_cap=0.95, family_weight_cap=0.95),
    )
    arbiter = ForecastArbiter(registry, ledger, router)
    request = _continuous_request(30)
    result = arbiter.predict(request)
    assert result.distribution.shape is ForecastShape.MIXTURE
    assert len(result.component_forecast_ids) == 2
    assert len(result.component_fingerprints) == 2
    assert result.epistemic_disagreement > 0.0
    assert len(ledger.unresolved()) == 2
    assert sum(component.weight for component in result.distribution.components) == pytest.approx(1.0)


def test_router_weights_sum_to_one_and_cold_start_is_symmetric() -> None:
    registry = ForecastExpertRegistry(default_prediction_lineage())
    holt = _continuous_expert(_identity("holt", "holt_smoothing_1957", ForecastFamily.SMOOTHING))
    kalman = _continuous_expert(_identity("kalman", "kalman_1960", ForecastFamily.STATE_SPACE))
    registry.register(holt)
    registry.register(kalman)
    router = PrequentialExpertRouter(
        registry,
        PrequentialScoreLedger(),
        policy=RouterPolicy(expert_weight_cap=0.95, family_weight_cap=0.95),
    )
    snapshot = router.snapshot(_continuous_request(1, issued_at=1000.0))
    assert sum(item.weight for item in snapshot.weights) == pytest.approx(1.0)
    assert snapshot.weights[0].weight == pytest.approx(snapshot.weights[1].weight)
    assert all(item.resolved_scores_used == 0 for item in snapshot.weights)


def test_historical_evidence_builder_uses_only_scores_available_before_cutoff() -> None:
    identity = _identity("kalman", "kalman_1960", ForecastFamily.STATE_SPACE)
    expert = _continuous_expert(identity, sd=1.5)
    ledger = PrequentialScoreLedger()
    for index in range(1, 7):
        request = _continuous_request(index)
        envelope = expert.forecast(request)
        ledger.record(request, envelope)
        resolved_at = 50.0 if index <= 5 else 500.0
        ledger.resolve(envelope.forecast_id, float(index), resolved_at=max(resolved_at, request.target.target_time))

    builder = HistoricalEvidenceBuilder(
        ledger,
        policy=HistoricalEvidencePolicy(minimum_scores=5, minimum_domains=1, minimum_independent_runs=1),
    )
    evidence = builder.build(
        identity,
        as_of_year=2024,
        benchmark_id="benchmark-v1",
        target_window_fingerprint="window-v1",
        knowledge_year=2024,
        data_cutoff_year=2024,
        available_before=100.0,
        domain_count=1,
        independent_runs=1,
        calibration_ece=0.05,
        calibration_checked=True,
        provenance_ids=("benchmark-manifest",),
    )
    assert evidence.folds == 5
    assert evidence.temporal_custody_verified is True
    assert evidence.leakage_audited is True
    assert evidence.metrics["calibration_ece"] == pytest.approx(0.05)
    assert evidence.metadata["prequential"] is True


def test_forecast_and_score_fingerprints_are_deterministic() -> None:
    identity = _identity("holt", "holt_smoothing_1957", ForecastFamily.SMOOTHING)
    expert = _continuous_expert(identity)
    request = _continuous_request(2)
    first = expert.forecast(request)
    second = expert.forecast(request)
    assert first.fingerprint == second.fingerprint
    ledger = PrequentialScoreLedger()
    ledger.record(request, first)
    score = ledger.resolve(first.forecast_id, 2.0, resolved_at=request.target.target_time)
    assert score.fingerprint
    assert ledger.fingerprint
