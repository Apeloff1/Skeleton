"""Regression tests for build observability and budgets (#807 B009)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.build.build_observability import (
    BuildObservabilityError,
    BuildRegressionBudget,
    NodeObservation,
    NodeRegressionBudget,
    evaluate_build_budget,
    observe_build,
)
from skeleton.build.incremental_graph import build_incremental_graph
from skeleton.build.parallel_scheduler import (
    ResourceCapacity,
    ResourceRequest,
    plan_parallel_build,
)


def _graph():
    return build_incremental_graph(
        [
            {"id": "src-a", "inputs": {"blob": "a"}},
            {"id": "src-b", "inputs": {"blob": "b"}},
            {"id": "compile-a", "dependencies": ["src-a"], "cost": 2},
            {"id": "compile-b", "dependencies": ["src-b"], "cost": 2},
            {
                "id": "link",
                "dependencies": ["compile-a", "compile-b"],
                "cost": 3,
            },
            {"id": "docs", "inputs": {"blob": "docs"}},
        ]
    )


def _plan():
    return plan_parallel_build(
        _graph(),
        resources={
            "src-a": ResourceRequest(cpu_units=1, memory_mib=128),
            "src-b": ResourceRequest(cpu_units=1, memory_mib=128),
            "compile-a": ResourceRequest(cpu_units=2, memory_mib=512),
            "compile-b": ResourceRequest(cpu_units=2, memory_mib=512),
            "link": ResourceRequest(cpu_units=3, memory_mib=1024),
            "docs": ResourceRequest(cpu_units=1, memory_mib=64),
        },
        capacity=ResourceCapacity(
            cpu_units=4,
            memory_mib=4096,
            io_units=4,
            weight=8,
        ),
        max_parallel=4,
    )


def _observations() -> list[NodeObservation]:
    return [
        NodeObservation("src-a", 5, 10, "hit"),
        NodeObservation("src-b", 7, 20, "miss"),
        NodeObservation("docs", 2, 5, "disabled"),
        NodeObservation("compile-a", 20, 100, "hit"),
        NodeObservation("compile-b", 10, 80, "miss"),
        NodeObservation("link", 8, 50, "hit"),
    ]


def test_observed_critical_path_and_wave_metrics_are_deterministic() -> None:
    graph = _graph()
    plan = _plan()

    telemetry = observe_build(graph, plan, _observations())

    assert telemetry.critical_path == ("src-a", "compile-a", "link")
    assert telemetry.critical_path_ms == 33
    assert telemetry.wave_elapsed_ms == 35
    assert telemetry.peak_parallel_memory_bytes == 180
    assert telemetry.cache_hits == 3
    assert telemetry.cache_misses == 2
    assert telemetry.cache_disabled == 1
    assert telemetry.cache_hit_ratio_ppm == 600_000


def test_observation_declaration_order_does_not_change_evidence() -> None:
    graph = _graph()
    plan = _plan()

    left = observe_build(graph, plan, _observations())
    right = observe_build(graph, plan, list(reversed(_observations())))

    assert left == right
    assert left.telemetry_digest == right.telemetry_digest
    assert left.serialize() == right.serialize()


def test_observations_must_cover_exact_plan_once() -> None:
    graph = _graph()
    plan = _plan()
    rows = _observations()

    with pytest.raises(BuildObservabilityError, match="exact build plan"):
        observe_build(graph, plan, rows[:-1])

    with pytest.raises(BuildObservabilityError, match="duplicate"):
        observe_build(graph, plan, [*rows, rows[0]])

    with pytest.raises(BuildObservabilityError, match="unscheduled"):
        observe_build(
            graph,
            plan,
            [*rows, NodeObservation("other", 1, 1, "miss")],
        )


def test_tampered_plan_derived_fields_fail_closed() -> None:
    graph = _graph()
    plan = _plan()

    with pytest.raises(BuildObservabilityError, match="derived fields drifted"):
        observe_build(
            graph,
            replace(plan, plan_fingerprint="0" * 64),
            _observations(),
        )

    with pytest.raises(BuildObservabilityError, match="derived fields drifted"):
        observe_build(
            graph,
            replace(plan, waves=tuple(reversed(plan.waves))),
            _observations(),
        )


def test_plan_must_bind_exact_graph_fingerprint() -> None:
    plan = _plan()
    other_graph = build_incremental_graph(
        [{"id": "only", "inputs": {"blob": "other"}}]
    )

    with pytest.raises(BuildObservabilityError, match="fingerprint"):
        observe_build(other_graph, plan, _observations())


def test_global_and_node_budgets_accept_clean_telemetry() -> None:
    telemetry = observe_build(_graph(), _plan(), _observations())
    budget = BuildRegressionBudget(
        max_critical_path_ms=40,
        max_wave_elapsed_ms=40,
        max_peak_parallel_memory_bytes=200,
        min_cache_hit_ratio_ppm=500_000,
        node_budgets=(
            NodeRegressionBudget(
                node_id="compile-a",
                max_duration_ms=25,
                max_peak_memory_bytes=120,
            ),
        ),
    )

    decision = evaluate_build_budget(telemetry, budget, graph=_graph(), plan=_plan())

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.telemetry_digest == telemetry.telemetry_digest
    assert len(decision.budget_digest) == 64


def test_regression_budget_reports_each_exceeded_dimension() -> None:
    telemetry = observe_build(_graph(), _plan(), _observations())
    budget = BuildRegressionBudget(
        max_critical_path_ms=30,
        max_wave_elapsed_ms=30,
        max_peak_parallel_memory_bytes=150,
        min_cache_hit_ratio_ppm=700_000,
        node_budgets=(
            NodeRegressionBudget(
                node_id="compile-a",
                max_duration_ms=10,
                max_peak_memory_bytes=90,
            ),
            NodeRegressionBudget(
                node_id="not-in-plan",
                max_duration_ms=10,
                max_peak_memory_bytes=90,
            ),
        ),
    )

    decision = evaluate_build_budget(telemetry, budget, graph=_graph(), plan=_plan())

    assert decision.accepted is False
    assert any(reason.startswith("critical-path-budget:") for reason in decision.reasons)
    assert any(reason.startswith("wave-elapsed-budget:") for reason in decision.reasons)
    assert any(reason.startswith("parallel-memory-budget:") for reason in decision.reasons)
    assert any(reason.startswith("cache-hit-budget:") for reason in decision.reasons)
    assert any(reason.startswith("node-duration-budget:compile-a") for reason in decision.reasons)
    assert any(reason.startswith("node-memory-budget:compile-a") for reason in decision.reasons)
    assert "node-budget-missing:not-in-plan" in decision.reasons


@pytest.mark.parametrize(
    "row",
    [
        NodeObservation("src-a", -1, 1, "hit"),
        NodeObservation("src-a", 1, -1, "hit"),
        NodeObservation("src-a", 1, 1, "unknown"),
    ],
)
def test_invalid_observation_metrics_fail_closed(row: NodeObservation) -> None:
    plan = _plan()
    rows = _observations()
    rows[0] = row

    with pytest.raises(BuildObservabilityError):
        observe_build(_graph(), plan, rows)


def test_tampered_derived_telemetry_fails_closed() -> None:
    graph = _graph()
    plan = _plan()
    telemetry = observe_build(graph, plan, _observations())
    tampered = type(telemetry)(
        graph_fingerprint=telemetry.graph_fingerprint,
        plan_fingerprint=telemetry.plan_fingerprint,
        records=telemetry.records,
        critical_path=telemetry.critical_path,
        critical_path_ms=1,
        wave_elapsed_ms=telemetry.wave_elapsed_ms,
        peak_parallel_memory_bytes=telemetry.peak_parallel_memory_bytes,
        cache_hits=telemetry.cache_hits,
        cache_misses=telemetry.cache_misses,
        cache_disabled=telemetry.cache_disabled,
        cache_hit_ratio_ppm=telemetry.cache_hit_ratio_ppm,
    )
    budget = BuildRegressionBudget(
        max_critical_path_ms=100,
        max_wave_elapsed_ms=100,
        max_peak_parallel_memory_bytes=1000,
    )

    with pytest.raises(BuildObservabilityError, match="derived metrics drifted"):
        evaluate_build_budget(tampered, budget, graph=graph, plan=plan)


def test_duplicate_node_budgets_fail_closed() -> None:
    telemetry = observe_build(_graph(), _plan(), _observations())
    duplicate = NodeRegressionBudget("src-a", 10, 10)
    budget = BuildRegressionBudget(
        max_critical_path_ms=100,
        max_wave_elapsed_ms=100,
        max_peak_parallel_memory_bytes=1000,
        node_budgets=(duplicate, duplicate),
    )

    with pytest.raises(BuildObservabilityError, match="duplicate node"):
        evaluate_build_budget(telemetry, budget, graph=_graph(), plan=_plan())


def test_cache_ratio_is_zero_when_cache_is_disabled_everywhere() -> None:
    rows = [
        NodeObservation(
            row.node_id,
            row.duration_ms,
            row.peak_memory_bytes,
            "disabled",
        )
        for row in _observations()
    ]

    telemetry = observe_build(_graph(), _plan(), rows)

    assert telemetry.cache_hits == 0
    assert telemetry.cache_misses == 0
    assert telemetry.cache_disabled == len(rows)
    assert telemetry.cache_hit_ratio_ppm == 0
