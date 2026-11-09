from __future__ import annotations

import pytest

from skeleton.jeeves.historical_evaluation import (
    BenchmarkSuite,
    HistoricalEvaluationError,
    HistoricalPromotionGate,
    HoldoutWindow,
    PromotionAction,
    PromotionPolicy,
    summarize_promotion,
)
from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelRegistry,
    ModelIdentity,
    make_benchmark_provenance,
)


NOW = 4_000_000.0
WINDOW = HoldoutWindow(start_at=NOW - 1_000.0, end_at=NOW)


def _definition(name: str, domain: BenchmarkDomain, *, revision: str = "v1") -> BenchmarkDefinition:
    return BenchmarkDefinition(
        benchmark_id=name,
        revision=revision,
        domain=domain,
        raw_min=0.0,
        raw_max=100.0,
    )


def _suite(*definitions: BenchmarkDefinition) -> BenchmarkSuite:
    domains = {definition.domain for definition in definitions}
    return BenchmarkSuite(
        suite_id="holdout",
        revision="2026-09",
        benchmark_keys=frozenset(definition.key for definition in definitions),
        domain_weights={domain: 1.0 for domain in domains},
        required_domains=frozenset(domains),
    )


def _ingest(
    registry: HistoricalModelRegistry,
    model: ModelIdentity,
    definition: BenchmarkDefinition,
    score: float,
    *,
    snapshot_id: str,
    samples: int = 100,
    measured_at: float = NOW - 100.0,
) -> None:
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=measured_at,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=definition,
        raw_score=score,
        sample_count=samples,
    )
    registry.ingest(
        BenchmarkSnapshot(
            snapshot_id=snapshot_id,
            model=model,
            benchmark=definition,
            raw_score=score,
            sample_count=samples,
            measured_at=measured_at,
            provenance=provenance,
        )
    )


def _gate(
    registry: HistoricalModelRegistry,
    suite: BenchmarkSuite,
    *,
    policy: PromotionPolicy | None = None,
) -> HistoricalPromotionGate:
    return HistoricalPromotionGate(
        registry=registry,
        suite=suite,
        window=WINDOW,
        policy=policy or PromotionPolicy(
            min_holdout_samples=1,
            min_coverage=1.0,
            min_promotion_margin=0.01,
            max_domain_regression=0.02,
            max_volatility=1.0,
            max_latest_drop=1.0,
        ),
    )


def test_suite_requires_at_least_one_benchmark() -> None:
    with pytest.raises(HistoricalEvaluationError) as exc:
        BenchmarkSuite(
            suite_id="empty",
            revision="v1",
            benchmark_keys=frozenset(),
            domain_weights={BenchmarkDomain.REASONING: 1.0},
            required_domains=frozenset({BenchmarkDomain.REASONING}),
        )
    assert exc.value.context["reason"] == "empty_suite"


def test_required_domain_must_have_weight() -> None:
    definition = _definition("reason", BenchmarkDomain.REASONING)
    with pytest.raises(HistoricalEvaluationError) as exc:
        BenchmarkSuite(
            suite_id="bad",
            revision="v1",
            benchmark_keys=frozenset({definition.key}),
            domain_weights={BenchmarkDomain.REASONING: 1.0},
            required_domains=frozenset({BenchmarkDomain.CODING}),
        )
    assert exc.value.context["reason"] == "missing_weight"


def test_holdout_window_requires_end_after_start() -> None:
    with pytest.raises(HistoricalEvaluationError) as exc:
        HoldoutWindow(start_at=10.0, end_at=10.0)
    assert exc.value.context["reason"] == "invalid_window"


def test_suite_fingerprint_is_stable_across_mapping_order() -> None:
    reason = _definition("reason", BenchmarkDomain.REASONING)
    code = _definition("code", BenchmarkDomain.CODING)
    left = BenchmarkSuite(
        suite_id="suite",
        revision="v1",
        benchmark_keys=frozenset({reason.key, code.key}),
        domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.CODING: 2.0},
        required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
    )
    right = BenchmarkSuite(
        suite_id="suite",
        revision="v1",
        benchmark_keys=frozenset({code.key, reason.key}),
        domain_weights={BenchmarkDomain.CODING: 2.0, BenchmarkDomain.REASONING: 1.0},
        required_domains=frozenset({BenchmarkDomain.CODING, BenchmarkDomain.REASONING}),
    )
    assert left.fingerprint == right.fingerprint


def test_evaluation_uses_only_exact_suite_revision() -> None:
    model = ModelIdentity("provider", "model", "r1")
    v1 = _definition("reason", BenchmarkDomain.REASONING, revision="v1")
    v2 = _definition("reason", BenchmarkDomain.REASONING, revision="v2")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, v1, 80.0, snapshot_id="v1")
    _ingest(registry, model, v2, 99.0, snapshot_id="v2", measured_at=NOW - 90.0)

    evaluation = _gate(registry, _suite(v1)).evaluate(model)

    assert evaluation.score == pytest.approx(0.80)
    assert evaluation.domains[0].snapshot_ids == ("v1",)


def test_evaluation_excludes_snapshots_outside_holdout_window() -> None:
    model = ModelIdentity("provider", "model", "r1")
    reason = _definition("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, reason, 99.0, snapshot_id="before", measured_at=NOW - 1_001.0)
    _ingest(registry, model, reason, 80.0, snapshot_id="inside", measured_at=NOW - 10.0)

    evaluation = _gate(registry, _suite(reason)).evaluate(model)

    assert evaluation.score == pytest.approx(0.80)
    assert evaluation.domains[0].snapshot_ids == ("inside",)


def test_model_without_holdout_evidence_fails_closed() -> None:
    model = ModelIdentity("provider", "model", "r1")
    reason = _definition("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, reason, 80.0, snapshot_id="before", measured_at=NOW - 1_001.0)
    with pytest.raises(HistoricalEvaluationError) as exc:
        _gate(registry, _suite(reason)).evaluate(model)
    assert exc.value.context["reason"] == "no_holdout_evidence"


def test_domain_score_is_sample_weighted() -> None:
    model = ModelIdentity("provider", "model", "r1")
    reason_a = _definition("reason-a", BenchmarkDomain.REASONING)
    reason_b = _definition("reason-b", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, reason_a, 100.0, snapshot_id="a", samples=100)
    _ingest(registry, model, reason_b, 0.0, snapshot_id="b", samples=300, measured_at=NOW - 90.0)

    evaluation = _gate(registry, _suite(reason_a, reason_b)).evaluate(model)

    assert evaluation.score == pytest.approx(0.25)
    assert evaluation.samples == 400


def test_domain_volatility_is_measured() -> None:
    model = ModelIdentity("provider", "model", "r1")
    reason_a = _definition("reason-a", BenchmarkDomain.REASONING)
    reason_b = _definition("reason-b", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, reason_a, 100.0, snapshot_id="a", samples=100)
    _ingest(registry, model, reason_b, 0.0, snapshot_id="b", samples=100, measured_at=NOW - 90.0)

    evaluation = _gate(registry, _suite(reason_a, reason_b)).evaluate(model)

    assert evaluation.max_volatility == pytest.approx(0.5)


def test_latest_drop_detects_recent_regression() -> None:
    model = ModelIdentity("provider", "model", "r1")
    reason_a = _definition("reason-a", BenchmarkDomain.REASONING)
    reason_b = _definition("reason-b", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, model, reason_a, 90.0, snapshot_id="old", measured_at=NOW - 100.0)
    _ingest(registry, model, reason_b, 70.0, snapshot_id="new", measured_at=NOW - 10.0)

    evaluation = _gate(registry, _suite(reason_a, reason_b)).evaluate(model)

    assert evaluation.max_latest_drop == pytest.approx(0.20)


def test_bootstrap_candidate_promotes_when_all_gates_pass() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    reason = _definition("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason, 90.0, snapshot_id="candidate")

    decision = _gate(registry, _suite(reason)).decide(candidate=candidate)

    assert decision.action is PromotionAction.PROMOTE
    assert decision.promotable is True
    assert decision.reasons == ()
    assert decision.margin is None


def test_candidate_must_clear_incumbent_margin() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    incumbent = ModelIdentity("provider", "incumbent", "r1")
    reason = _definition("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason, 90.5, snapshot_id="candidate")
    _ingest(registry, incumbent, reason, 90.0, snapshot_id="incumbent", measured_at=NOW - 90.0)

    decision = _gate(registry, _suite(reason)).decide(candidate=candidate, incumbent=incumbent)

    assert decision.action is PromotionAction.HOLD
    assert "insufficient_promotion_margin" in decision.reasons
    assert decision.margin == pytest.approx(0.005)


def test_candidate_promotes_when_margin_is_large_enough() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    incumbent = ModelIdentity("provider", "incumbent", "r1")
    reason = _definition("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason, 92.0, snapshot_id="candidate")
    _ingest(registry, incumbent, reason, 90.0, snapshot_id="incumbent", measured_at=NOW - 90.0)

    decision = _gate(registry, _suite(reason)).decide(candidate=candidate, incumbent=incumbent)

    assert decision.action is PromotionAction.PROMOTE
    assert decision.margin == pytest.approx(0.02)


def test_required_domain_regression_blocks_promotion_even_when_overall_wins() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    incumbent = ModelIdentity("provider", "incumbent", "r1")
    reason = _definition("reason", BenchmarkDomain.REASONING)
    code = _definition("code", BenchmarkDomain.CODING)
    suite = BenchmarkSuite(
        suite_id="suite",
        revision="v1",
        benchmark_keys=frozenset({reason.key, code.key}),
        domain_weights={BenchmarkDomain.REASONING: 4.0, BenchmarkDomain.CODING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
    )
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason, 99.0, snapshot_id="c-r")
    _ingest(registry, candidate, code, 70.0, snapshot_id="c-c", measured_at=NOW - 90.0)
    _ingest(registry, incumbent, reason, 90.0, snapshot_id="i-r", measured_at=NOW - 80.0)
    _ingest(registry, incumbent, code, 80.0, snapshot_id="i-c", measured_at=NOW - 70.0)

    decision = _gate(registry, suite).decide(candidate=candidate, incumbent=incumbent)

    assert decision.candidate.score > decision.incumbent.score
    assert decision.action is PromotionAction.HOLD
    assert "domain_regression:coding" in decision.reasons


def test_insufficient_samples_blocks_bootstrap_promotion() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    reason = _definition("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason, 95.0, snapshot_id="candidate", samples=10)
    policy = PromotionPolicy(
        min_holdout_samples=64,
        min_coverage=1.0,
        min_promotion_margin=0.0,
        max_domain_regression=1.0,
        max_volatility=1.0,
        max_latest_drop=1.0,
    )

    decision = _gate(registry, _suite(reason), policy=policy).decide(candidate=candidate)

    assert decision.action is PromotionAction.HOLD
    assert "insufficient_holdout_samples" in decision.reasons


def test_missing_required_domain_blocks_promotion() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    reason = _definition("reason", BenchmarkDomain.REASONING)
    code = _definition("code", BenchmarkDomain.CODING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason, 95.0, snapshot_id="candidate")

    decision = _gate(registry, _suite(reason, code)).decide(candidate=candidate)

    assert decision.action is PromotionAction.HOLD
    assert "missing_required_domain" in decision.reasons
    assert "insufficient_suite_coverage" in decision.reasons


def test_excessive_volatility_blocks_promotion() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    reason_a = _definition("reason-a", BenchmarkDomain.REASONING)
    reason_b = _definition("reason-b", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason_a, 100.0, snapshot_id="a")
    _ingest(registry, candidate, reason_b, 0.0, snapshot_id="b", measured_at=NOW - 90.0)
    policy = PromotionPolicy(
        min_holdout_samples=1,
        min_coverage=1.0,
        min_promotion_margin=0.0,
        max_domain_regression=1.0,
        max_volatility=0.10,
        max_latest_drop=1.0,
    )

    decision = _gate(registry, _suite(reason_a, reason_b), policy=policy).decide(candidate=candidate)

    assert decision.action is PromotionAction.HOLD
    assert "excessive_volatility" in decision.reasons


def test_recent_regression_blocks_promotion() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    reason_a = _definition("reason-a", BenchmarkDomain.REASONING)
    reason_b = _definition("reason-b", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason_a, 95.0, snapshot_id="old", measured_at=NOW - 100.0)
    _ingest(registry, candidate, reason_b, 70.0, snapshot_id="new", measured_at=NOW - 10.0)
    policy = PromotionPolicy(
        min_holdout_samples=1,
        min_coverage=1.0,
        min_promotion_margin=0.0,
        max_domain_regression=1.0,
        max_volatility=1.0,
        max_latest_drop=0.05,
    )

    decision = _gate(registry, _suite(reason_a, reason_b), policy=policy).decide(candidate=candidate)

    assert decision.action is PromotionAction.HOLD
    assert "recent_regression" in decision.reasons


def test_decision_fingerprint_is_deterministic() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    reason = _definition("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason, 90.0, snapshot_id="candidate")
    gate = _gate(registry, _suite(reason))

    first = gate.decide(candidate=candidate)
    second = gate.decide(candidate=candidate)

    assert first.decision_fingerprint == second.decision_fingerprint


def test_evidence_fingerprint_changes_when_holdout_evidence_changes() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    reason_a = _definition("reason-a", BenchmarkDomain.REASONING)
    reason_b = _definition("reason-b", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason_a, 90.0, snapshot_id="a")
    first = _gate(registry, _suite(reason_a, reason_b)).evaluate(candidate).evidence_fingerprint
    _ingest(registry, candidate, reason_b, 91.0, snapshot_id="b", measured_at=NOW - 90.0)
    second = _gate(registry, _suite(reason_a, reason_b)).evaluate(candidate).evidence_fingerprint
    assert first != second


def test_summary_is_json_safe_and_contains_gate_evidence() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    reason = _definition("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason, 90.0, snapshot_id="candidate")

    summary = summarize_promotion(_gate(registry, _suite(reason)).decide(candidate=candidate))

    assert summary["action"] == "promote"
    assert summary["promotable"] is True
    assert summary["candidate"] == candidate.key
    assert summary["candidate_score"] == pytest.approx(0.9)
    assert summary["suite_fingerprint"]
    assert summary["policy_fingerprint"]
    assert summary["decision_fingerprint"]


def test_policy_rejects_invalid_margin() -> None:
    with pytest.raises(HistoricalEvaluationError):
        PromotionPolicy(min_promotion_margin=1.1)


def test_policy_rejects_invalid_regression_tolerance() -> None:
    with pytest.raises(HistoricalEvaluationError):
        PromotionPolicy(max_domain_regression=-0.1)


def test_domain_snapshot_ids_are_temporally_ordered() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    reason_a = _definition("reason-a", BenchmarkDomain.REASONING)
    reason_b = _definition("reason-b", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason_a, 90.0, snapshot_id="late", measured_at=NOW - 10.0)
    _ingest(registry, candidate, reason_b, 90.0, snapshot_id="early", measured_at=NOW - 100.0)

    domain = _gate(registry, _suite(reason_a, reason_b)).evaluate(candidate).domains[0]

    assert domain.snapshot_ids == ("early", "late")


def test_single_snapshot_has_zero_latest_drop_and_volatility() -> None:
    candidate = ModelIdentity("provider", "candidate", "r1")
    reason = _definition("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    _ingest(registry, candidate, reason, 90.0, snapshot_id="only")

    domain = _gate(registry, _suite(reason)).evaluate(candidate).domains[0]

    assert domain.volatility == 0.0
    assert domain.latest_drop == 0.0
    assert domain.historical_score == pytest.approx(0.9)