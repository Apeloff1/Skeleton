from skeleton.jeeves.agent.historical_synthesis import (
    ChronologicalScientificFrontier,
    EvidenceProfile,
    HistoricalContextAdapter,
    HistoricalMethod,
    HistoricalReference,
    MethodEvaluation,
    MethodFamily,
    QualityVector,
    foundational_seed_methods,
)
from skeleton.jeeves.agent.memory_game_index import MemoryGameIndex


def _method(method_id, year):
    return HistoricalMethod(
        method_id=method_id,
        name=method_id,
        introduced_year=year,
        families=(MethodFamily.COMPILER,),
        thesis=f"{method_id} thesis",
        evidence=EvidenceProfile(
            formal_strength=0.9,
            empirical_strength=0.8,
            replication=0.8,
            external_validity=0.8,
            reproducibility=0.9,
            falsifiability=0.9,
        ),
        references=(
            HistoricalReference(
                reference_id=f"ref-{method_id}",
                title=f"Reference {method_id}",
                publication_year=year,
                locator=f"fixture:{method_id}",
                contribution="fixture",
            ),
        ),
    )


def _evaluation(evaluation_id, method_id, year, correctness, robustness, *, failure=()):
    return MethodEvaluation(
        evaluation_id=evaluation_id,
        method_id=method_id,
        evaluation_year=year,
        benchmark_id="shared-benchmark",
        quality=QualityVector(
            correctness=correctness,
            calibration=0.8,
            robustness=robustness,
            compute_efficiency=0.7,
            sample_efficiency=0.7,
            memory_efficiency=0.7,
            interpretability=0.8,
            auditability=0.9,
            transfer=0.75,
            reproducibility=0.9,
        ),
        confidence=1.0,
        hard_failures=tuple(failure),
        independent_run=evaluation_id,
    )


def test_year_by_year_replay_has_no_future_leakage():
    frontier = ChronologicalScientificFrontier()
    old = frontier.register_method(_method("old", 2000))
    future = frontier.register_method(_method("future", 2002))
    frontier.record_evaluation(_evaluation("old-2000", old.method_id, 2000, 0.8, 0.8))
    frontier.record_evaluation(_evaluation("future-2002", future.method_id, 2002, 0.95, 0.95))

    y2001 = frontier.annual(2001)
    assert "old" in y2001.pareto_method_ids
    assert "future" not in y2001.eligible_method_ids

    y2002 = frontier.annual(2002, previous=y2001)
    assert "future" in y2002.eligible_method_ids
    assert "future" in y2002.pareto_method_ids


def test_newer_method_does_not_replace_older_method_when_it_is_dominated():
    frontier = ChronologicalScientificFrontier()
    frontier.register_method(_method("old", 2000))
    frontier.register_method(_method("new", 2026))
    frontier.record_evaluation(_evaluation("old-e", "old", 2000, 0.95, 0.95))
    frontier.record_evaluation(_evaluation("new-e", "new", 2026, 0.70, 0.70))
    result = frontier.annual(2026)
    assert result.pareto_method_ids == ("old",)


def test_perpendicular_tradeoffs_remain_on_pareto_frontier():
    frontier = ChronologicalScientificFrontier()
    frontier.register_method(_method("accurate", 2000))
    frontier.register_method(_method("robust", 2001))
    frontier.record_evaluation(_evaluation("a", "accurate", 2000, 0.99, 0.55))
    frontier.record_evaluation(_evaluation("r", "robust", 2001, 0.75, 0.99))
    result = frontier.annual(2001)
    assert set(result.pareto_method_ids) == {"accurate", "robust"}


def test_hard_regression_removes_method_even_when_scalar_metrics_are_high():
    frontier = ChronologicalScientificFrontier()
    frontier.register_method(_method("safe", 2000))
    frontier.register_method(_method("broken", 2001))
    frontier.record_evaluation(_evaluation("safe-e", "safe", 2000, 0.85, 0.85))
    frontier.record_evaluation(
        _evaluation("broken-e", "broken", 2001, 0.99, 0.99, failure=("semantic-preservation",))
    )
    result = frontier.annual(2001)
    assert "broken" in result.hard_failed_method_ids
    assert "broken" not in result.pareto_method_ids
    assert "safe" in result.pareto_method_ids


def test_seed_catalog_is_chronological_and_explicitly_retrievable_as_canonical_chronicle():
    frontier = ChronologicalScientificFrontier()
    for method in foundational_seed_methods():
        frontier.register_method(method)
    adapter = HistoricalContextAdapter(frontier, knowledge_year=2026)
    results = adapter.search(
        "tenant/user/work/session",
        "compiler static single assignment dataflow",
        max_records=5,
        max_tokens=5000,
    )
    assert results
    assert all(record.canonical for record in results)
    assert any("ssa-1991" in record.source_ref for record in results)


def test_historical_cards_are_only_fast_indices_for_canonical_chronicle_records():
    frontier = ChronologicalScientificFrontier()
    for method in foundational_seed_methods():
        frontier.register_method(method)
    adapter = HistoricalContextAdapter(frontier, knowledge_year=2026)
    index = MemoryGameIndex()
    card_ids = adapter.index_cards(index, "tenant/user/work/session")
    assert card_ids
    packet = index.query("tenant/user/work/session", "Bayesian probability", touch=False)
    assert packet.all_hits
    hit = packet.all_hits[0]
    records = adapter.fetch_refs(
        "tenant/user/work/session",
        (hit.card.source_ref,),
        max_records=1,
        max_tokens=5000,
    )
    assert len(records) == 1
    assert records[0].canonical is True
    assert records[0].source_fingerprint == hit.card.source_fingerprint
