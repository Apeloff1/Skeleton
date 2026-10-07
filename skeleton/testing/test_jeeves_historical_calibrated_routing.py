from __future__ import annotations

import pytest

from skeleton.jeeves.historical_calibrated_routing import (
    CalibratedPortfolioRouter,
    CalibratedRoutingPolicy,
    HistoricalCalibratedRoutingError,
    summarize_calibrated_route,
)
from skeleton.jeeves.historical_calibration import CalibrationModel
from skeleton.jeeves.historical_evaluation import BenchmarkSuite, HoldoutWindow
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    make_benchmark_provenance,
)
from skeleton.jeeves.historical_portfolio import HistoricalExpertPortfolioBuilder, PortfolioPolicy
from skeleton.jeeves.historical_routing import ProviderCatalog


NOW = 1_000.0
REASON = BenchmarkDefinition("route-reason", "v1", BenchmarkDomain.REASONING, 0.0, 100.0)
CODE = BenchmarkDefinition("route-code", "v1", BenchmarkDomain.CODING, 0.0, 100.0)
SUITE = BenchmarkSuite(
    suite_id="route-suite",
    revision="v1",
    benchmark_keys=frozenset({REASON.key, CODE.key}),
    domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.CODING: 1.0},
    required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
)
WINDOW = HoldoutWindow(100.0, 200.0)


class FakeProvider:
    supports_system_prompt = True

    def __init__(self, name: str, *, available: bool = True) -> None:
        self.name = name
        self._available = available

    def available(self) -> bool:
        return self._available

    def complete(self, prompt: str, context=None, max_tokens: int = 512, system=None) -> str:
        return f"{self.name}:{prompt}"


def _snapshot(snapshot_id, model, benchmark, score):
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=150.0,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
    )
    return BenchmarkSnapshot(
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
        measured_at=150.0,
        provenance=provenance,
    )


def _fixture(*, specialist_available=True, fallback_available=True):
    general = ModelIdentity("provider", "general", "r1")
    coder = ModelIdentity("provider", "coder", "r1")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    for model, scores, prefix in [
        (general, (90.0, 90.0), "g"),
        (coder, (80.0, 98.0), "c"),
    ]:
        registry.ingest(_snapshot(f"{prefix}-r", model, REASON, scores[0]))
        registry.ingest(_snapshot(f"{prefix}-c", model, CODE, scores[1]))
    portfolio = HistoricalExpertPortfolioBuilder(
        registry=registry,
        suite=SUITE,
        window=WINDOW,
        policy=PortfolioPolicy(max_models=2, min_specialist_margin=0.05),
    ).build(models=[general, coder])
    catalog = ProviderCatalog()
    catalog.bind(general, lambda: FakeProvider("general", available=fallback_available))
    catalog.bind(coder, lambda: FakeProvider("coder", available=specialist_available))
    identity_general = CalibrationModel(1.0, 0.0, "cal-general")
    identity_coder = CalibrationModel(1.0, 0.0, "cal-coder")
    return portfolio, catalog, general, coder, identity_general, identity_coder


def test_identity_calibration_preserves_material_specialist() -> None:
    portfolio, catalog, general, coder, cal_general, cal_coder = _fixture()
    decision = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: cal_general, coder: cal_coder},
        policy=CalibratedRoutingPolicy(min_calibrated_specialist_margin=0.05),
    ).route(BenchmarkDomain.CODING)
    assert decision.selected_model == coder
    assert decision.used_specialist is True
    assert decision.reason == "specialist_selected"
    assert decision.calibrated_margin == pytest.approx(0.08)
    assert decision.provider.name == "coder"


def test_missing_specialist_calibration_falls_back_by_default() -> None:
    portfolio, catalog, general, _, cal_general, _ = _fixture()
    decision = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: cal_general},
    ).route(BenchmarkDomain.CODING)
    assert decision.selected_model == general
    assert decision.reason == "missing_specialist_calibration"


def test_policy_can_allow_uncalibrated_specialist() -> None:
    portfolio, catalog, _, coder, _, _ = _fixture()
    decision = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={},
        policy=CalibratedRoutingPolicy(
            min_calibrated_specialist_margin=0.05,
            require_specialist_calibration=False,
        ),
    ).route(BenchmarkDomain.CODING)
    assert decision.selected_model == coder


def test_calibration_can_collapse_raw_specialist_advantage() -> None:
    portfolio, catalog, general, _, cal_general, _ = _fixture()
    coder = portfolio.model_for(BenchmarkDomain.CODING)
    pessimistic = CalibrationModel(slope=0.5, intercept=0.2, source_fingerprint="cal-coder-pessimistic")
    decision = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: cal_general, coder: pessimistic},
        policy=CalibratedRoutingPolicy(min_calibrated_specialist_margin=0.01),
    ).route(BenchmarkDomain.CODING)
    assert decision.selected_model == general
    assert decision.reason == "calibrated_margin_below_threshold"
    assert decision.calibrated_margin < 0.01


def test_fallback_calibration_can_raise_required_specialist_bar() -> None:
    portfolio, catalog, general, coder, _, cal_coder = _fixture()
    optimistic_fallback = CalibrationModel(slope=1.0, intercept=0.07, source_fingerprint="cal-general-up")
    decision = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: optimistic_fallback, coder: cal_coder},
        policy=CalibratedRoutingPolicy(min_calibrated_specialist_margin=0.02),
    ).route(BenchmarkDomain.CODING)
    assert decision.selected_model == general
    assert decision.reason == "calibrated_margin_below_threshold"


def test_unavailable_specialist_falls_back() -> None:
    portfolio, catalog, general, coder, cal_general, cal_coder = _fixture(specialist_available=False)
    decision = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: cal_general, coder: cal_coder},
    ).route(BenchmarkDomain.CODING)
    assert decision.selected_model == general
    assert decision.reason == "specialist_unavailable"
    assert decision.provider.name == "general"


def test_strict_unavailable_specialist_policy_fails_closed() -> None:
    portfolio, catalog, general, coder, cal_general, cal_coder = _fixture(specialist_available=False)
    router = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: cal_general, coder: cal_coder},
        policy=CalibratedRoutingPolicy(fallback_on_specialist_unavailable=False),
    )
    with pytest.raises(HistoricalCalibratedRoutingError) as exc:
        router.route(BenchmarkDomain.CODING)
    assert exc.value.context["reason"] == "specialist_unavailable"


def test_unavailable_fallback_always_fails_closed() -> None:
    portfolio, catalog, general, coder, cal_general, cal_coder = _fixture(fallback_available=False)
    router = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: cal_general, coder: cal_coder},
    )
    with pytest.raises(HistoricalCalibratedRoutingError) as exc:
        router.route(BenchmarkDomain.REASONING)
    assert exc.value.context["reason"] == "fallback_unavailable"


def test_unknown_portfolio_domain_routes_general_fallback() -> None:
    portfolio, catalog, general, coder, cal_general, cal_coder = _fixture()
    decision = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: cal_general, coder: cal_coder},
    ).route(BenchmarkDomain.RESEARCH)
    assert decision.selected_model == general
    assert decision.reason == "fallback_assignment"


def test_calibration_fingerprints_are_bound_into_decision() -> None:
    portfolio, catalog, general, coder, cal_general, cal_coder = _fixture()
    decision = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: cal_general, coder: cal_coder},
    ).route(BenchmarkDomain.CODING)
    assert decision.calibration_fingerprints == ("cal-coder", "cal-general")
    assert decision.decision_fingerprint


def test_decision_fingerprint_changes_when_calibration_changes() -> None:
    portfolio, catalog, general, coder, cal_general, cal_coder = _fixture()
    first = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: cal_general, coder: cal_coder},
    ).route(BenchmarkDomain.CODING)
    changed = CalibrationModel(0.9, 0.0, "changed-cal")
    second = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: cal_general, coder: changed},
    ).route(BenchmarkDomain.CODING)
    assert first.decision_fingerprint != second.decision_fingerprint


def test_summary_exposes_calibrated_route_evidence() -> None:
    portfolio, catalog, general, coder, cal_general, cal_coder = _fixture()
    decision = CalibratedPortfolioRouter(
        portfolio=portfolio,
        catalog=catalog,
        calibrations={general: cal_general, coder: cal_coder},
    ).route(BenchmarkDomain.CODING)
    summary = summarize_calibrated_route(decision)
    assert summary["selected_model"] == coder.key
    assert summary["used_specialist"] is True
    assert summary["decision_fingerprint"] == decision.decision_fingerprint