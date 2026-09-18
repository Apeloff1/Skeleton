from __future__ import annotations

import pytest

from skeleton.jeeves.historical_authorization import HistoricalActivationAuthorizer
from skeleton.jeeves.historical_evaluation import (
    BenchmarkSuite,
    HistoricalPromotionGate,
    HoldoutWindow,
    PromotionPolicy,
)
from skeleton.jeeves.historical_governance import HistoricalChampionLedger
from skeleton.jeeves.historical_lifecycle import HistoricalLifecycleError, HistoricalModelLifecycle
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    SelectionPolicy,
    canonical_fingerprint,
    make_benchmark_provenance,
)
from skeleton.jeeves.historical_readiness import HistoricalReadinessReport, ReadinessCheck
from skeleton.jeeves.historical_routing import HistoricalChampionRouter, ProviderCatalog


NOW = 9_000_000.0


class FakeProvider:
    supports_system_prompt = True

    def available(self) -> bool:
        return True

    def complete(self, prompt: str, context=None, max_tokens: int = 512, system=None) -> str:
        return prompt


def _ingest(
    registry: HistoricalModelRegistry,
    model: ModelIdentity,
    benchmark: BenchmarkDefinition,
    *,
    snapshot_id: str,
    score: float,
    measured_at: float,
) -> None:
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=measured_at,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=100,
    )
    registry.ingest(
        BenchmarkSnapshot(
            snapshot_id=snapshot_id,
            model=model,
            benchmark=benchmark,
            raw_score=score,
            sample_count=100,
            measured_at=measured_at,
            provenance=provenance,
        )
    )


def _fixture():
    model = ModelIdentity("provider", "guarded", "r1")
    benchmark = BenchmarkDefinition(
        benchmark_id="authorization-reasoning",
        revision="v1",
        domain=BenchmarkDomain.REASONING,
        raw_min=0.0,
        raw_max=100.0,
    )
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(
        registry,
        model,
        benchmark,
        snapshot_id="initial",
        score=90.0,
        measured_at=NOW - 30.0,
    )
    provider = FakeProvider()
    catalog = ProviderCatalog()
    catalog.bind(model, lambda: provider)
    router = HistoricalChampionRouter(
        registry=registry,
        policy=SelectionPolicy(
            domain_weights={BenchmarkDomain.REASONING: 1.0},
            required_domains=frozenset({BenchmarkDomain.REASONING}),
            minimum_sample_count=1,
            confidence_z=0.0,
            max_snapshot_age_seconds=10_000.0,
        ),
        catalog=catalog,
    )
    promotion_gate = HistoricalPromotionGate(
        registry=registry,
        suite=BenchmarkSuite(
            suite_id="authorization-suite",
            revision="v1",
            benchmark_keys=frozenset({benchmark.key}),
            domain_weights={BenchmarkDomain.REASONING: 1.0},
            required_domains=frozenset({BenchmarkDomain.REASONING}),
        ),
        window=HoldoutWindow(NOW - 1_000.0, NOW),
        policy=PromotionPolicy(
            min_holdout_samples=1,
            min_coverage=1.0,
            min_promotion_margin=0.0,
            max_domain_regression=1.0,
            max_volatility=1.0,
            max_latest_drop=1.0,
        ),
    )
    lifecycle = HistoricalModelLifecycle(
        router=router,
        promotion_gate=promotion_gate,
        ledger=HistoricalChampionLedger(clock=lambda: NOW),
        catalog=catalog,
    )
    return lifecycle, registry, model, benchmark, provider


def _readiness(model: ModelIdentity) -> HistoricalReadinessReport:
    check = ReadinessCheck(
        check_id="fixture",
        required=True,
        present=True,
        passed=True,
        evidence_fingerprint="fixture-evidence",
    )
    policy_fingerprint = "readiness-policy"
    payload = {
        "candidate": model.key,
        "policy": policy_fingerprint,
        "checks": [
            {
                "id": check.check_id,
                "required": check.required,
                "present": check.present,
                "passed": check.passed,
                "evidence": check.evidence_fingerprint,
            }
        ],
        "reasons": [],
    }
    return HistoricalReadinessReport(
        candidate=model,
        passed=True,
        checks=(check,),
        reasons=(),
        policy_fingerprint=policy_fingerprint,
        report_fingerprint=canonical_fingerprint(payload),
    )


def test_guarded_lifecycle_rejects_direct_activation() -> None:
    lifecycle, _, _, _, _ = _fixture()
    proposal = lifecycle.propose()

    with pytest.raises(HistoricalLifecycleError) as exc:
        lifecycle.activate(proposal)

    assert exc.value.context["reason"] == "activation_authorization_required"
    assert lifecycle.ledger.active_model is None


def test_authorizer_can_activate_guarded_lifecycle() -> None:
    lifecycle, _, model, _, provider = _fixture()
    proposal = lifecycle.propose()
    readiness = _readiness(model)
    authorization = HistoricalActivationAuthorizer.authorize(
        proposal=proposal,
        readiness=readiness,
    )

    activation = HistoricalActivationAuthorizer.activate(
        lifecycle=lifecycle,
        proposal=proposal,
        readiness=readiness,
        authorization=authorization,
    )

    assert activation.state.model == model
    assert activation.route.provider is provider
    assert lifecycle.ledger.active_model == model


def test_authorized_but_stale_proposal_still_cannot_mutate_ledger() -> None:
    lifecycle, registry, model, benchmark, _ = _fixture()
    proposal = lifecycle.propose()
    readiness = _readiness(model)
    authorization = HistoricalActivationAuthorizer.authorize(
        proposal=proposal,
        readiness=readiness,
    )
    _ingest(
        registry,
        model,
        benchmark,
        snapshot_id="new-evidence",
        score=95.0,
        measured_at=NOW - 10.0,
    )

    with pytest.raises(HistoricalLifecycleError) as exc:
        HistoricalActivationAuthorizer.activate(
            lifecycle=lifecycle,
            proposal=proposal,
            readiness=readiness,
            authorization=authorization,
        )

    assert exc.value.context["reason"] == "stale_proposal"
    assert lifecycle.ledger.active_model is None