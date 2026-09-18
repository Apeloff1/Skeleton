from __future__ import annotations

import pytest

from skeleton.jeeves.historical_models import (
    BenchmarkDefinition,
    BenchmarkDomain,
    BenchmarkSnapshot,
    HistoricalModelError,
    HistoricalModelRegistry,
    MetricDirection,
    MissingDomainPolicy,
    ModelIdentity,
    SelectionPolicy,
    balanced_frontier_policy,
    make_benchmark_provenance,
    summarize_decision,
)


NOW = 2_000_000.0


def _benchmark(
    name: str,
    domain: BenchmarkDomain,
    *,
    revision: str = "v1",
    raw_min: float = 0.0,
    raw_max: float = 100.0,
    direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER,
    weight_hint: float = 1.0,
) -> BenchmarkDefinition:
    return BenchmarkDefinition(
        benchmark_id=name,
        revision=revision,
        domain=domain,
        raw_min=raw_min,
        raw_max=raw_max,
        direction=direction,
        weight_hint=weight_hint,
    )


def _snapshot(
    snapshot_id: str,
    model: ModelIdentity,
    benchmark: BenchmarkDefinition,
    score: float,
    *,
    samples: int = 100,
    measured_at: float = NOW - 10.0,
) -> BenchmarkSnapshot:
    provenance = make_benchmark_provenance(
        source_id=f"fixture:{snapshot_id}",
        source_kind="benchmark",
        measured_at=measured_at,
        clock_version=1,
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=samples,
        uri=f"fixture://{snapshot_id}",
    )
    return BenchmarkSnapshot(
        snapshot_id=snapshot_id,
        model=model,
        benchmark=benchmark,
        raw_score=score,
        sample_count=samples,
        measured_at=measured_at,
        provenance=provenance,
    )


def _policy(*domains: BenchmarkDomain, confidence_z: float = 0.0) -> SelectionPolicy:
    return SelectionPolicy(
        domain_weights={domain: 1.0 for domain in domains},
        required_domains=frozenset(domains),
        minimum_sample_count=1,
        confidence_z=confidence_z,
        max_snapshot_age_seconds=10_000.0,
    )


def test_higher_is_better_normalization() -> None:
    benchmark = _benchmark("reason", BenchmarkDomain.REASONING)
    assert benchmark.normalize(0.0) == 0.0
    assert benchmark.normalize(50.0) == 0.5
    assert benchmark.normalize(100.0) == 1.0


def test_lower_is_better_normalization() -> None:
    benchmark = _benchmark(
        "latency",
        BenchmarkDomain.LATENCY,
        raw_min=100.0,
        raw_max=1_100.0,
        direction=MetricDirection.LOWER_IS_BETTER,
    )
    assert benchmark.normalize(100.0) == 1.0
    assert benchmark.normalize(600.0) == 0.5
    assert benchmark.normalize(1_100.0) == 0.0


def test_raw_score_outside_declared_bounds_fails_closed() -> None:
    benchmark = _benchmark("reason", BenchmarkDomain.REASONING)
    with pytest.raises(HistoricalModelError):
        benchmark.normalize(101.0)


def test_model_identity_is_provider_neutral_and_stable() -> None:
    identity = ModelIdentity(provider=" OpenAI ", model="model-x", revision="2026-01")
    assert identity.provider == "openai"
    assert identity.key == "openai:model-x@2026-01"


def test_snapshot_requires_matching_canonical_provenance() -> None:
    model = ModelIdentity("local", "candidate", "r1")
    benchmark = _benchmark("code", BenchmarkDomain.CODING)
    provenance = make_benchmark_provenance(
        source_id="fixture:bad",
        source_kind="benchmark",
        measured_at=NOW,
        clock_version=1,
        snapshot_id="different-id",
        model=model,
        benchmark=benchmark,
        raw_score=80.0,
        sample_count=100,
    )
    with pytest.raises(HistoricalModelError) as exc:
        BenchmarkSnapshot(
            snapshot_id="actual-id",
            model=model,
            benchmark=benchmark,
            raw_score=80.0,
            sample_count=100,
            measured_at=NOW,
            provenance=provenance,
        )
    assert exc.value.context["reason"] == "fingerprint_mismatch"


def test_snapshot_requires_provenance_timestamp_to_match_measurement() -> None:
    model = ModelIdentity("local", "candidate", "r1")
    benchmark = _benchmark("code", BenchmarkDomain.CODING)
    provenance = make_benchmark_provenance(
        source_id="fixture:bad-time",
        source_kind="benchmark",
        measured_at=NOW - 1.0,
        clock_version=1,
        snapshot_id="s1",
        model=model,
        benchmark=benchmark,
        raw_score=80.0,
        sample_count=100,
    )
    with pytest.raises(HistoricalModelError) as exc:
        BenchmarkSnapshot(
            snapshot_id="s1",
            model=model,
            benchmark=benchmark,
            raw_score=80.0,
            sample_count=100,
            measured_at=NOW,
            provenance=provenance,
        )
    assert exc.value.context["reason"] == "timestamp_mismatch"


def test_future_snapshot_is_rejected_on_ingest() -> None:
    model = ModelIdentity("local", "candidate", "r1")
    benchmark = _benchmark("code", BenchmarkDomain.CODING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    future = _snapshot("future", model, benchmark, 80.0, measured_at=NOW + 1.0)
    with pytest.raises(HistoricalModelError) as exc:
        registry.ingest(future)
    assert exc.value.context["reason"] == "future_snapshot"


def test_identical_snapshot_ingest_is_idempotent() -> None:
    model = ModelIdentity("local", "candidate", "r1")
    benchmark = _benchmark("code", BenchmarkDomain.CODING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    snapshot = _snapshot("s1", model, benchmark, 80.0)
    registry.ingest(snapshot)
    registry.ingest(snapshot)
    assert registry.snapshots() == (snapshot,)


def test_duplicate_snapshot_id_with_changed_content_is_rejected() -> None:
    model = ModelIdentity("local", "candidate", "r1")
    benchmark = _benchmark("code", BenchmarkDomain.CODING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("s1", model, benchmark, 80.0, measured_at=NOW - 10.0))
    with pytest.raises(HistoricalModelError) as exc:
        registry.ingest(_snapshot("s1", model, benchmark, 81.0, measured_at=NOW - 9.0))
    assert exc.value.context["reason"] == "duplicate_snapshot"


def test_logical_duplicate_with_conflicting_score_is_rejected() -> None:
    model = ModelIdentity("local", "candidate", "r1")
    benchmark = _benchmark("code", BenchmarkDomain.CODING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("s1", model, benchmark, 80.0, measured_at=NOW - 10.0))
    with pytest.raises(HistoricalModelError) as exc:
        registry.ingest(_snapshot("s2", model, benchmark, 81.0, measured_at=NOW - 10.0))
    assert exc.value.context["reason"] == "contradictory_snapshot"


def test_history_limit_prevents_unbounded_benchmark_growth() -> None:
    model = ModelIdentity("local", "candidate", "r1")
    benchmark = _benchmark("code", BenchmarkDomain.CODING)
    registry = HistoricalModelRegistry(clock=lambda: NOW, max_snapshots_per_benchmark=2)
    registry.ingest(_snapshot("s1", model, benchmark, 80.0, measured_at=NOW - 30.0))
    registry.ingest(_snapshot("s2", model, benchmark, 81.0, measured_at=NOW - 20.0))
    with pytest.raises(HistoricalModelError) as exc:
        registry.ingest(_snapshot("s3", model, benchmark, 82.0, measured_at=NOW - 10.0))
    assert exc.value.context["reason"] == "history_limit"


def test_stronger_historical_record_wins_single_domain() -> None:
    a = ModelIdentity("provider-a", "a", "r1")
    b = ModelIdentity("provider-b", "b", "r1")
    benchmark = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("a", a, benchmark, 92.0))
    registry.ingest(_snapshot("b", b, benchmark, 86.0))

    decision = registry.select_champion(_policy(BenchmarkDomain.REASONING))

    assert decision.champion.model == a
    assert decision.historical_best_percent == 92.0
    assert [candidate.model for candidate in decision.candidates] == [a, b]


def test_workload_weights_can_change_champion() -> None:
    a = ModelIdentity("provider-a", "a", "r1")
    b = ModelIdentity("provider-b", "b", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    code = _benchmark("code", BenchmarkDomain.CODING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("a-r", a, reason, 95.0))
    registry.ingest(_snapshot("a-c", a, code, 70.0))
    registry.ingest(_snapshot("b-r", b, reason, 82.0))
    registry.ingest(_snapshot("b-c", b, code, 94.0))

    reasoning_heavy = SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 4.0, BenchmarkDomain.CODING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
        minimum_sample_count=1,
        confidence_z=0.0,
        max_snapshot_age_seconds=10_000.0,
    )
    coding_heavy = SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.CODING: 4.0},
        required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
        minimum_sample_count=1,
        confidence_z=0.0,
        max_snapshot_age_seconds=10_000.0,
    )

    assert registry.select_champion(reasoning_heavy).champion.model == a
    assert registry.select_champion(coding_heavy).champion.model == b


def test_required_domain_missing_rejects_candidate() -> None:
    complete = ModelIdentity("provider-a", "complete", "r1")
    partial = ModelIdentity("provider-b", "partial", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    code = _benchmark("code", BenchmarkDomain.CODING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("c-r", complete, reason, 80.0))
    registry.ingest(_snapshot("c-c", complete, code, 80.0))
    registry.ingest(_snapshot("p-r", partial, reason, 99.0))

    decision = registry.select_champion(_policy(BenchmarkDomain.REASONING, BenchmarkDomain.CODING))

    assert decision.champion.model == complete
    assert len(decision.candidates) == 1


def test_penalty_policy_keeps_optional_missing_domain_candidate() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("r", model, reason, 90.0))
    policy = SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.RESEARCH: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING}),
        minimum_sample_count=1,
        confidence_z=0.0,
        max_snapshot_age_seconds=10_000.0,
        missing_domain_policy=MissingDomainPolicy.PENALIZE,
        missing_domain_score=0.2,
    )

    score = registry.select_champion(policy).champion

    assert score.model == model
    assert score.score == pytest.approx(0.55)
    assert score.coverage == pytest.approx(0.5)
    assert score.missing_domains == (BenchmarkDomain.RESEARCH,)


def test_reject_policy_requires_every_weighted_domain() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("r", model, reason, 90.0))
    policy = SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.RESEARCH: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING}),
        minimum_sample_count=1,
        confidence_z=0.0,
        max_snapshot_age_seconds=10_000.0,
        missing_domain_policy=MissingDomainPolicy.REJECT,
    )
    with pytest.raises(HistoricalModelError) as exc:
        registry.select_champion(policy)
    assert exc.value.context["reason"] == "no_eligible_candidates"


def test_stale_snapshots_do_not_participate() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("old", model, reason, 99.0, measured_at=NOW - 10_001.0))
    with pytest.raises(HistoricalModelError) as exc:
        registry.select_champion(_policy(BenchmarkDomain.REASONING))
    assert exc.value.context["reason"] == "no_eligible_candidates"


def test_minimum_sample_count_filters_thin_evidence() -> None:
    thin = ModelIdentity("provider-a", "thin", "r1")
    solid = ModelIdentity("provider-b", "solid", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("thin", thin, reason, 100.0, samples=4))
    registry.ingest(_snapshot("solid", solid, reason, 80.0, samples=100))
    policy = SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING}),
        minimum_sample_count=32,
        confidence_z=0.0,
        max_snapshot_age_seconds=10_000.0,
    )

    decision = registry.select_champion(policy)

    assert decision.champion.model == solid
    assert len(decision.candidates) == 1


def test_uncertainty_penalty_rewards_better_supported_record() -> None:
    thin = ModelIdentity("provider-a", "thin", "r1")
    solid = ModelIdentity("provider-b", "solid", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("thin", thin, reason, 92.0, samples=32))
    registry.ingest(_snapshot("solid", solid, reason, 90.0, samples=1_000))
    policy = SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING}),
        minimum_sample_count=1,
        confidence_z=1.96,
        max_snapshot_age_seconds=10_000.0,
    )

    decision = registry.select_champion(policy)

    assert decision.champion.model == solid
    assert decision.candidates[0].conservative_score > decision.candidates[1].conservative_score


def test_zero_uncertainty_penalty_preserves_observed_score() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("r", model, reason, 73.0, samples=10))

    score = registry.select_champion(_policy(BenchmarkDomain.REASONING)).champion

    assert score.score == pytest.approx(0.73)
    assert score.conservative_score == pytest.approx(0.73)


def test_recency_half_life_downweights_old_snapshot() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("old", model, reason, 100.0, samples=100, measured_at=NOW - 100.0))
    registry.ingest(_snapshot("new", model, reason, 50.0, samples=100, measured_at=NOW))
    no_decay = SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING}),
        minimum_sample_count=1,
        confidence_z=0.0,
        max_snapshot_age_seconds=1_000.0,
    )
    decay = SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 1.0},
        required_domains=frozenset({BenchmarkDomain.REASONING}),
        minimum_sample_count=1,
        confidence_z=0.0,
        max_snapshot_age_seconds=1_000.0,
        recency_half_life_seconds=100.0,
    )

    assert registry.select_champion(no_decay).champion.score == pytest.approx(0.75)
    assert registry.select_champion(decay).champion.score == pytest.approx(2.0 / 3.0)


def test_benchmark_weight_hint_changes_domain_aggregate() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    broad = _benchmark("broad", BenchmarkDomain.REASONING, weight_hint=2.0)
    narrow = _benchmark("narrow", BenchmarkDomain.REASONING, weight_hint=1.0)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("broad", model, broad, 90.0, samples=100))
    registry.ingest(_snapshot("narrow", model, narrow, 30.0, samples=100, measured_at=NOW - 5.0))

    score = registry.select_champion(_policy(BenchmarkDomain.REASONING)).champion

    assert score.score == pytest.approx(0.70)


def test_deterministic_tie_break_uses_stable_model_key() -> None:
    a = ModelIdentity("a-provider", "same", "r1")
    z = ModelIdentity("z-provider", "same", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("z", z, reason, 80.0))
    registry.ingest(_snapshot("a", a, reason, 80.0, measured_at=NOW - 5.0))

    decision = registry.select_champion(_policy(BenchmarkDomain.REASONING))

    assert decision.champion.model == a
    assert [candidate.model for candidate in decision.candidates] == [a, z]


def test_selection_can_be_limited_to_explicit_candidate_set() -> None:
    a = ModelIdentity("provider-a", "a", "r1")
    b = ModelIdentity("provider-b", "b", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("a", a, reason, 95.0))
    registry.ingest(_snapshot("b", b, reason, 80.0))

    decision = registry.select_champion(_policy(BenchmarkDomain.REASONING), models=[b])

    assert decision.champion.model == b
    assert len(decision.candidates) == 1


def test_policy_fingerprint_is_deterministic_across_mapping_order() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    code = _benchmark("code", BenchmarkDomain.CODING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("r", model, reason, 80.0))
    registry.ingest(_snapshot("c", model, code, 80.0, measured_at=NOW - 5.0))
    left = SelectionPolicy(
        domain_weights={BenchmarkDomain.REASONING: 1.0, BenchmarkDomain.CODING: 2.0},
        required_domains=frozenset({BenchmarkDomain.REASONING, BenchmarkDomain.CODING}),
        minimum_sample_count=1,
        confidence_z=0.0,
        max_snapshot_age_seconds=10_000.0,
    )
    right = SelectionPolicy(
        domain_weights={BenchmarkDomain.CODING: 2.0, BenchmarkDomain.REASONING: 1.0},
        required_domains=frozenset({BenchmarkDomain.CODING, BenchmarkDomain.REASONING}),
        minimum_sample_count=1,
        confidence_z=0.0,
        max_snapshot_age_seconds=10_000.0,
    )

    assert registry.select_champion(left).policy_fingerprint == registry.select_champion(right).policy_fingerprint


def test_evidence_fingerprint_changes_when_candidate_evidence_changes() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("r1", model, reason, 80.0, measured_at=NOW - 20.0))
    before = registry.select_champion(_policy(BenchmarkDomain.REASONING)).evidence_fingerprint
    registry.ingest(_snapshot("r2", model, reason, 81.0, measured_at=NOW - 10.0))
    after = registry.select_champion(_policy(BenchmarkDomain.REASONING)).evidence_fingerprint
    assert before != after


def test_models_and_snapshots_are_returned_in_deterministic_order() -> None:
    z = ModelIdentity("z", "model", "r1")
    a = ModelIdentity("a", "model", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("late", z, reason, 80.0, measured_at=NOW - 1.0))
    registry.ingest(_snapshot("early", a, reason, 80.0, measured_at=NOW - 2.0))
    assert registry.models() == (a, z)
    assert [snapshot.snapshot_id for snapshot in registry.snapshots()] == ["early", "late"]


def test_balanced_frontier_policy_has_quality_domains_required() -> None:
    policy = balanced_frontier_policy()
    assert BenchmarkDomain.REASONING in policy.required_domains
    assert BenchmarkDomain.CODING in policy.required_domains
    assert BenchmarkDomain.INSTRUCTION_FOLLOWING in policy.required_domains
    assert BenchmarkDomain.RESEARCH in policy.domain_weights
    assert BenchmarkDomain.TOOL_USE in policy.domain_weights


def test_summary_exposes_historical_best_percentage_and_fingerprints() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("r", model, reason, 88.0))

    summary = summarize_decision(registry.select_champion(_policy(BenchmarkDomain.REASONING)))

    assert summary["historical_champion"] == model.key
    assert summary["historical_best_percent"] == 88.0
    assert summary["policy_fingerprint"]
    assert summary["evidence_fingerprint"]
    assert summary["domains"][0]["domain"] == "reasoning"


def test_empty_registry_fails_closed() -> None:
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    with pytest.raises(HistoricalModelError) as exc:
        registry.select_champion(_policy(BenchmarkDomain.REASONING))
    assert exc.value.context["reason"] == "no_candidates"


def test_policy_rejects_required_domain_without_weight() -> None:
    with pytest.raises(HistoricalModelError) as exc:
        SelectionPolicy(
            domain_weights={BenchmarkDomain.REASONING: 1.0},
            required_domains=frozenset({BenchmarkDomain.CODING}),
        )
    assert exc.value.context["reason"] == "missing_weight"


def test_policy_rejects_non_positive_weights() -> None:
    with pytest.raises(HistoricalModelError):
        SelectionPolicy(domain_weights={BenchmarkDomain.REASONING: 0.0})


def test_policy_rejects_impossible_confidence_z() -> None:
    with pytest.raises(HistoricalModelError):
        SelectionPolicy(domain_weights={BenchmarkDomain.REASONING: 1.0}, confidence_z=9.0)


def test_benchmark_revision_is_part_of_logical_history_key() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    v1 = _benchmark("reason", BenchmarkDomain.REASONING, revision="v1")
    v2 = _benchmark("reason", BenchmarkDomain.REASONING, revision="v2")
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("v1", model, v1, 80.0, measured_at=NOW - 10.0))
    registry.ingest(_snapshot("v2", model, v2, 90.0, measured_at=NOW - 10.0))
    assert len(registry.snapshots_for(model)) == 2


def test_model_revision_is_part_of_candidate_identity() -> None:
    old = ModelIdentity("provider-a", "candidate", "old")
    new = ModelIdentity("provider-a", "candidate", "new")
    reason = _benchmark("reason", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("old", old, reason, 70.0))
    registry.ingest(_snapshot("new", new, reason, 90.0, measured_at=NOW - 5.0))
    decision = registry.select_champion(_policy(BenchmarkDomain.REASONING))
    assert decision.champion.model == new


def test_domain_score_records_all_snapshot_ids_used() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    reason_a = _benchmark("reason-a", BenchmarkDomain.REASONING)
    reason_b = _benchmark("reason-b", BenchmarkDomain.REASONING)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("z-id", model, reason_a, 80.0))
    registry.ingest(_snapshot("a-id", model, reason_b, 90.0, measured_at=NOW - 5.0))
    domain = registry.select_champion(_policy(BenchmarkDomain.REASONING)).champion.domains[0]
    assert domain.snapshot_ids == ("a-id", "z-id")
    assert domain.effective_samples == 200


def test_conservative_percent_is_rounded_for_ui() -> None:
    model = ModelIdentity("provider-a", "candidate", "r1")
    reason = _benchmark("reason", BenchmarkDomain.REASONING, raw_min=0.0, raw_max=1.0)
    registry = HistoricalModelRegistry(clock=lambda: NOW)
    registry.ingest(_snapshot("r", model, reason, 0.87654, samples=100))
    decision = registry.select_champion(_policy(BenchmarkDomain.REASONING))
    assert decision.historical_best_percent == 87.65