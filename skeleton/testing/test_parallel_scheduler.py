"""Regression tests for deterministic parallel build scheduling (#807 B005)."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from skeleton.build.incremental_graph import build_incremental_graph
from skeleton.build.parallel_scheduler import (
    ParallelSchedulerError,
    ResourceCapacity,
    ResourceRequest,
    TargetEvidence,
    aggregate_build_evidence,
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


def _capacity() -> ResourceCapacity:
    return ResourceCapacity(
        cpu_units=4,
        memory_mib=4096,
        io_units=4,
        weight=8,
    )


def _resources():
    return {
        "src-a": ResourceRequest(cpu_units=1, memory_mib=128, weight=1),
        "src-b": ResourceRequest(cpu_units=1, memory_mib=128, weight=1),
        "compile-a": ResourceRequest(cpu_units=2, memory_mib=512, weight=3),
        "compile-b": ResourceRequest(cpu_units=2, memory_mib=512, weight=3),
        "link": ResourceRequest(cpu_units=3, memory_mib=1024, weight=5),
        "docs": ResourceRequest(cpu_units=1, memory_mib=64, weight=1),
    }


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _evidence(plan, node_id: str, *, status: str = "success") -> TargetEvidence:
    target = next(
        target
        for wave in plan.waves
        for target in wave.targets
        if target.node_id == node_id
    )
    return TargetEvidence(
        node_id=node_id,
        node_fingerprint=target.fingerprint,
        graph_fingerprint=plan.graph_fingerprint,
        plan_fingerprint=plan.plan_fingerprint,
        status=status,
        output_digest=_digest(f"output:{node_id}"),
        log_digest=_digest(f"log:{node_id}"),
    )


def test_independent_targets_fan_out_and_dependencies_wait_for_later_waves() -> None:
    graph = _graph()
    plan = plan_parallel_build(
        graph,
        resources=_resources(),
        capacity=_capacity(),
        max_parallel=4,
    )

    waves = [[target.node_id for target in wave.targets] for wave in plan.waves]

    assert set(waves[0]) == {"src-a", "src-b", "docs"}
    assert set(waves[1]) == {"compile-a", "compile-b"}
    assert waves[2] == ["link"]
    assert plan.selected_targets == graph.topological_order


def test_target_selection_is_dependency_closed_without_unrelated_work() -> None:
    plan = plan_parallel_build(
        _graph(),
        resources=_resources(),
        targets=["link"],
        capacity=_capacity(),
        max_parallel=4,
    )

    assert plan.requested_targets == ("link",)
    assert set(plan.selected_targets) == {
        "src-a",
        "src-b",
        "compile-a",
        "compile-b",
        "link",
    }
    assert "docs" not in plan.selected_targets


def test_capacity_and_parallelism_bound_each_wave() -> None:
    plan = plan_parallel_build(
        _graph(),
        resources=_resources(),
        capacity=ResourceCapacity(
            cpu_units=2,
            memory_mib=1024,
            io_units=4,
            weight=4,
        ),
        max_parallel=1,
    )

    assert all(len(wave.targets) == 1 for wave in plan.waves)
    assert all(wave.used.cpu_units <= 2 for wave in plan.waves)
    assert all(wave.used.memory_mib <= 1024 for wave in plan.waves)
    assert all(wave.used.weight <= 4 for wave in plan.waves)


def test_impossible_target_request_fails_closed() -> None:
    resources = _resources()
    resources["compile-a"] = ResourceRequest(
        cpu_units=8,
        memory_mib=512,
        weight=3,
    )

    with pytest.raises(ParallelSchedulerError, match="exceeds wave capacity"):
        plan_parallel_build(
            _graph(),
            resources=resources,
            capacity=_capacity(),
        )


def test_unknown_duplicate_and_malformed_targets_fail_closed() -> None:
    graph = _graph()

    with pytest.raises(ParallelSchedulerError, match="unknown requested"):
        plan_parallel_build(
            graph,
            targets=["missing"],
            capacity=_capacity(),
        )

    with pytest.raises(ParallelSchedulerError, match="duplicate requested"):
        plan_parallel_build(
            graph,
            targets=["link", "link"],
            capacity=_capacity(),
        )

    with pytest.raises(ParallelSchedulerError, match="sequence"):
        plan_parallel_build(
            graph,
            targets="link",  # type: ignore[arg-type]
            capacity=_capacity(),
        )


def test_unknown_or_malformed_resource_requests_fail_closed() -> None:
    graph = _graph()

    with pytest.raises(ParallelSchedulerError, match="resources must be a mapping"):
        plan_parallel_build(
            graph,
            resources=[],  # type: ignore[arg-type]
            capacity=_capacity(),
        )

    with pytest.raises(ParallelSchedulerError, match="unknown target"):
        plan_parallel_build(
            graph,
            resources={"missing": ResourceRequest()},
            capacity=_capacity(),
        )

    with pytest.raises(ParallelSchedulerError, match="unknown keys"):
        plan_parallel_build(
            graph,
            resources={"src-a": {"shell": "rm -rf /"}},
            capacity=_capacity(),
        )

    with pytest.raises(ParallelSchedulerError, match="cpu_units is out of range"):
        plan_parallel_build(
            graph,
            resources={"src-a": {"cpu_units": 0}},
            capacity=_capacity(),
        )


def test_plan_is_deterministic_across_mapping_declaration_order() -> None:
    resources = _resources()
    reversed_resources = dict(reversed(list(resources.items())))

    left = plan_parallel_build(
        _graph(),
        resources=resources,
        capacity=_capacity(),
        max_parallel=4,
    )
    right = plan_parallel_build(
        _graph(),
        resources=reversed_resources,
        capacity=_capacity(),
        max_parallel=4,
    )

    assert left.plan_fingerprint == right.plan_fingerprint
    assert left.serialize() == right.serialize()
    parsed = json.loads(left.serialize())
    assert left.serialize() == json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def test_evidence_aggregation_is_order_independent_and_content_addressed() -> None:
    plan = plan_parallel_build(
        _graph(),
        resources=_resources(),
        targets=["link"],
        capacity=_capacity(),
        max_parallel=4,
    )
    records = [_evidence(plan, node_id) for node_id in plan.selected_targets]

    left = aggregate_build_evidence(plan, records)
    right = aggregate_build_evidence(plan, list(reversed(records)))

    assert left.success is True
    assert left.evidence_fingerprint == right.evidence_fingerprint
    assert left.serialize() == right.serialize()
    assert [record.node_id for record in left.records] == list(plan.selected_targets)


def test_failed_target_is_preserved_in_evidence_and_marks_aggregate_failed() -> None:
    plan = plan_parallel_build(
        _graph(),
        targets=["link"],
        capacity=_capacity(),
    )
    records = [
        _evidence(
            plan,
            node_id,
            status="failure" if node_id == "compile-a" else "success",
        )
        for node_id in plan.selected_targets
    ]

    evidence = aggregate_build_evidence(plan, records)

    assert evidence.success is False
    failed = [record.node_id for record in evidence.records if record.status == "failure"]
    assert failed == ["compile-a"]


def test_missing_duplicate_unknown_and_mismatched_evidence_fail_closed() -> None:
    plan = plan_parallel_build(
        _graph(),
        targets=["link"],
        capacity=_capacity(),
    )
    records = [_evidence(plan, node_id) for node_id in plan.selected_targets]

    with pytest.raises(ParallelSchedulerError, match="incomplete"):
        aggregate_build_evidence(plan, records[:-1])

    with pytest.raises(ParallelSchedulerError, match="duplicate target evidence"):
        aggregate_build_evidence(plan, [*records, records[0]])

    extra = TargetEvidence(
        node_id="not-scheduled",
        node_fingerprint=_digest("node"),
        graph_fingerprint=plan.graph_fingerprint,
        plan_fingerprint=plan.plan_fingerprint,
        status="success",
        output_digest=_digest("out"),
        log_digest=_digest("log"),
    )
    with pytest.raises(ParallelSchedulerError, match="unscheduled"):
        aggregate_build_evidence(plan, [*records, extra])

    first = records[0]
    bad = TargetEvidence(
        node_id=first.node_id,
        node_fingerprint=_digest("wrong"),
        graph_fingerprint=first.graph_fingerprint,
        plan_fingerprint=first.plan_fingerprint,
        status=first.status,
        output_digest=first.output_digest,
        log_digest=first.log_digest,
    )
    with pytest.raises(ParallelSchedulerError, match="node fingerprint mismatch"):
        aggregate_build_evidence(plan, [bad, *records[1:]])


def test_forged_plan_fails_closed_before_evidence_processing() -> None:
    plan = plan_parallel_build(
        _graph(),
        targets=["link"],
        capacity=_capacity(),
    )
    forged = replace(
        plan,
        selected_targets=(*plan.selected_targets, "ghost"),
    )

    with pytest.raises(
        ParallelSchedulerError,
        match="selected targets do not match scheduled targets",
    ):
        aggregate_build_evidence(forged, [])


def test_forged_requested_targets_fail_closed() -> None:
    plan = plan_parallel_build(
        _graph(),
        targets=["link"],
        capacity=_capacity(),
    )
    forged = replace(plan, requested_targets=("ghost",))

    with pytest.raises(
        ParallelSchedulerError,
        match="requested targets are not contained",
    ):
        aggregate_build_evidence(forged, [])


def test_forged_wave_accounting_type_fails_closed() -> None:
    plan = plan_parallel_build(
        _graph(),
        targets=["src-a"],
        capacity=_capacity(),
    )
    bad_wave = replace(plan.waves[0], used="invalid")  # type: ignore[arg-type]
    forged = replace(plan, waves=(bad_wave,))

    with pytest.raises(
        ParallelSchedulerError,
        match="used resources are invalid",
    ):
        aggregate_build_evidence(forged, [])


def test_evidence_digest_and_status_are_strict() -> None:
    plan = plan_parallel_build(
        _graph(),
        targets=["src-a"],
        capacity=_capacity(),
    )
    record = _evidence(plan, "src-a")

    malformed = {
        **record.to_dict(),
        "status": "maybe",
    }
    with pytest.raises(ParallelSchedulerError, match="unsupported evidence status"):
        aggregate_build_evidence(plan, [malformed])

    malformed = {
        **record.to_dict(),
        "status": ["success"],
    }
    with pytest.raises(ParallelSchedulerError, match="unsupported evidence status"):
        aggregate_build_evidence(plan, [malformed])

    malformed = {
        **record.to_dict(),
        "output_digest": "ABC",
    }
    with pytest.raises(ParallelSchedulerError, match="lowercase SHA-256"):
        aggregate_build_evidence(plan, [malformed])
