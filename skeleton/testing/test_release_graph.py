"""Regression tests for the reproducible release graph (#807 B010)."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from skeleton.build.incremental_graph import build_incremental_graph
from skeleton.build.release_graph import (
    NamedDigest,
    ReleaseGraphError,
    build_release_graph,
    compare_release_runs,
    record_release_run,
    serialize_release_graph,
    validate_release_graph,
    validate_release_run,
)
from skeleton.build.remote_build import (
    RemoteArtifactRef,
    RemoteExecutionSpec,
    RemoteJobReceipt,
    VerifiedRemoteReceipt,
    build_remote_plan,
    verify_remote_receipt,
)


SOURCE_COMMIT = "1" * 40
TOOLCHAIN_DIGEST = "2" * 64


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _graph():
    return build_incremental_graph(
        [
            {"id": "source", "inputs": {"blob": "src"}},
            {"id": "compile", "dependencies": ["source"]},
            {"id": "package", "dependencies": ["compile"]},
        ]
    )


def _spec(node_id: str) -> RemoteExecutionSpec:
    return RemoteExecutionSpec(
        node_id=node_id,
        argv=("python", "-m", "builder", node_id),
        input_artifacts=(
            RemoteArtifactRef(
                artifact_id=f"input:{node_id}",
                sha256=_digest(f"input:{node_id}"),
                size_bytes=10,
            ),
        ),
        output_artifact_ids=(f"output:{node_id}",),
        working_directory=".",
        writable_paths=(f"build/{node_id}",),
    )


def _plan():
    graph = _graph()
    return build_remote_plan(
        graph,
        source_commit=SOURCE_COMMIT,
        toolchain_digest=TOOLCHAIN_DIGEST,
        executions=[_spec(node_id) for node_id in graph.topological_order],
    )


def _release_graph():
    return build_release_graph(
        _plan(),
        target="linux-x64",
        models={"npc-model": _digest("model")},
        assets={"main-pack": _digest("asset")},
        configs={"release": _digest("config")},
    )


def _receipt(
    plan,
    node_id: str,
    *,
    output_digest: str | None = None,
    runner: str = "runner-a",
    log_digest: str | None = None,
):
    job = plan.node_job_map()[node_id]
    artifact = RemoteArtifactRef(
        artifact_id=job.output_artifact_ids[0],
        sha256=output_digest or _digest(f"output-bytes:{node_id}"),
        size_bytes=100 + len(node_id),
    )
    return verify_remote_receipt(
        plan,
        RemoteJobReceipt(
            job_id=job.job_id,
            plan_fingerprint=plan.plan_fingerprint,
            source_commit=plan.source_commit,
            toolchain_digest=plan.toolchain_digest,
            runner_id=runner,
            status="success",
            output_artifacts=(artifact,),
            log_digest=log_digest or _digest(f"log:{runner}:{node_id}"),
        ),
    )


def _receipts(plan, *, runner: str = "runner-a", suffix: str = ""):
    return tuple(
        _receipt(
            plan,
            node_id,
            runner=runner,
            output_digest=_digest(f"stable-output:{node_id}{suffix}"),
        )
        for node_id in plan.selected_nodes
    )


def test_release_graph_binds_all_reproducibility_inputs() -> None:
    plan = _plan()
    graph = build_release_graph(
        plan,
        target="linux-x64",
        models={"npc-model": _digest("model")},
        assets={"main-pack": _digest("asset")},
        configs={"release": _digest("config")},
    )

    assert graph.source_commit == plan.source_commit
    assert graph.graph_fingerprint == plan.graph_fingerprint
    assert graph.remote_plan_fingerprint == plan.plan_fingerprint
    assert graph.toolchain_digest == plan.toolchain_digest
    assert graph.target == "linux-x64"
    assert graph.models == (NamedDigest("npc-model", _digest("model")),)
    assert graph.assets == (NamedDigest("main-pack", _digest("asset")),)
    assert graph.configs == (NamedDigest("release", _digest("config")),)
    assert tuple(step.job_id for step in graph.steps) == tuple(
        job.job_id for job in plan.jobs
    )
    assert len(graph.digest) == 64


def test_named_digest_input_order_does_not_change_graph_identity() -> None:
    plan = _plan()
    left = build_release_graph(
        plan,
        target="linux-x64",
        models=[
            {"name": "z-model", "sha256": _digest("z")},
            {"name": "a-model", "sha256": _digest("a")},
        ],
        assets=[
            {"name": "z-pack", "sha256": _digest("zp")},
            {"name": "a-pack", "sha256": _digest("ap")},
        ],
    )
    right = build_release_graph(
        plan,
        target="linux-x64",
        models=[
            {"name": "a-model", "sha256": _digest("a")},
            {"name": "z-model", "sha256": _digest("z")},
        ],
        assets=[
            {"name": "a-pack", "sha256": _digest("ap")},
            {"name": "z-pack", "sha256": _digest("zp")},
        ],
    )

    assert left == right


def test_target_or_material_change_changes_identity() -> None:
    plan = _plan()
    baseline = build_release_graph(
        plan,
        target="linux-x64",
        models={"model": _digest("model")},
    )
    target_change = build_release_graph(
        plan,
        target="windows-x64",
        models={"model": _digest("model")},
    )
    model_change = build_release_graph(
        plan,
        target="linux-x64",
        models={"model": _digest("model-v2")},
    )

    assert baseline.digest != target_change.digest
    assert baseline.digest != model_change.digest


@pytest.mark.parametrize(
    "field",
    ["source_commit", "graph_fingerprint", "remote_plan_fingerprint", "toolchain_digest"],
)
def test_forged_release_graph_authority_fields_fail_closed(field: str) -> None:
    plan = _plan()
    graph = build_release_graph(plan, target="linux-x64")
    replacement = "0" * (40 if field == "source_commit" else 64)

    with pytest.raises(ReleaseGraphError):
        validate_release_graph(replace(graph, **{field: replacement}), plan)


def test_forged_step_or_graph_digest_fails_closed() -> None:
    plan = _plan()
    graph = build_release_graph(plan, target="linux-x64")
    forged_step = replace(graph.steps[0], recipe_digest="0" * 64)

    with pytest.raises(ReleaseGraphError, match="derived identity"):
        validate_release_graph(
            replace(graph, steps=(forged_step, *graph.steps[1:])),
            plan,
        )

    with pytest.raises(ReleaseGraphError, match="derived identity"):
        validate_release_graph(replace(graph, digest="0" * 64), plan)


def test_release_graph_serialization_is_canonical() -> None:
    plan = _plan()
    graph = _release_graph()

    raw = serialize_release_graph(graph, plan)

    assert raw == json.dumps(
        json.loads(raw),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def test_invalid_named_digests_and_duplicate_names_fail_closed() -> None:
    plan = _plan()

    with pytest.raises(ReleaseGraphError):
        build_release_graph(
            plan,
            target="linux-x64",
            models={"model": "bad"},
        )

    with pytest.raises(ReleaseGraphError, match="duplicate"):
        build_release_graph(
            plan,
            target="linux-x64",
            models=[
                {"name": "model", "sha256": _digest("a")},
                {"name": "model", "sha256": _digest("b")},
            ],
        )

    with pytest.raises(ReleaseGraphError):
        build_release_graph(plan, target="bad target")


def test_record_run_requires_exact_successful_job_coverage() -> None:
    plan = _plan()
    graph = build_release_graph(plan, target="linux-x64")
    receipts = _receipts(plan)

    run = record_release_run(graph, plan, reversed(receipts))
    assert run.graph_digest == graph.digest
    assert len(run.receipt_digests) == len(plan.jobs)
    assert tuple(item.artifact_id for item in run.output_artifacts) == tuple(
        sorted(f"output:{node_id}" for node_id in plan.selected_nodes)
    )

    with pytest.raises(ReleaseGraphError, match="exactly cover"):
        record_release_run(graph, plan, receipts[:-1])


def test_forged_verified_receipt_digest_is_rejected() -> None:
    plan = _plan()
    graph = build_release_graph(plan, target="linux-x64")
    receipts = list(_receipts(plan))
    receipts[0] = replace(receipts[0], receipt_digest="0" * 64)

    with pytest.raises(ReleaseGraphError, match="receipt digest"):
        record_release_run(graph, plan, receipts)


def test_failed_or_output_mismatched_receipt_is_rejected() -> None:
    plan = _plan()
    graph = build_release_graph(plan, target="linux-x64")
    receipt = _receipt(plan, "source")

    with pytest.raises(ReleaseGraphError, match="successful"):
        record_release_run(
            graph,
            plan,
            [
                replace(receipt, status="failure"),
                *_receipts(plan)[1:],
            ],
        )

    bad_output = replace(
        receipt.output_artifacts[0],
        artifact_id="output:wrong",
    )
    forged = replace(receipt, output_artifacts=(bad_output,))
    with pytest.raises(ReleaseGraphError, match="output set"):
        record_release_run(
            graph,
            plan,
            [forged, *_receipts(plan)[1:]],
        )


def test_hand_constructed_verified_receipt_cannot_bypass_b008_digest() -> None:
    plan = _plan()
    graph = build_release_graph(plan, target="linux-x64")
    real = _receipt(plan, "source")
    forged = VerifiedRemoteReceipt(
        job_id=real.job_id,
        runner_id=real.runner_id,
        status=real.status,
        output_artifacts=real.output_artifacts,
        log_digest=real.log_digest,
        receipt_digest=_digest("invented"),
    )

    with pytest.raises(ReleaseGraphError, match="receipt digest"):
        record_release_run(
            graph,
            plan,
            [forged, *_receipts(plan)[1:]],
        )


def test_release_run_digest_and_output_set_are_revalidated() -> None:
    plan = _plan()
    graph = build_release_graph(plan, target="linux-x64")
    run = record_release_run(graph, plan, _receipts(plan))

    validate_release_run(run, graph)

    with pytest.raises(ReleaseGraphError, match="run digest"):
        validate_release_run(replace(run, run_digest="0" * 64), graph)

    with pytest.raises(ReleaseGraphError, match="output set"):
        validate_release_run(
            replace(
                run,
                output_artifacts=run.output_artifacts[:-1],
                run_digest=_digest("not-important"),
            ),
            graph,
        )

    with pytest.raises(ReleaseGraphError, match="receipt digest count"):
        validate_release_run(
            replace(
                run,
                receipt_digests=run.receipt_digests[:-1],
            ),
            graph,
        )


def test_repeated_outputs_are_reproducible_despite_runner_log_changes() -> None:
    plan = _plan()
    graph = build_release_graph(plan, target="linux-x64")
    left = record_release_run(
        graph,
        plan,
        _receipts(plan, runner="runner-a"),
    )
    right = record_release_run(
        graph,
        plan,
        _receipts(plan, runner="runner-b"),
    )

    assert left.receipt_digests != right.receipt_digests
    assert left.run_digest != right.run_digest
    assert left.output_artifacts == right.output_artifacts

    decision = compare_release_runs(graph, left, right)
    assert decision.reproducible is True
    assert decision.mismatched_artifact_ids == ()
    assert len(decision.decision_digest) == 64


def test_output_byte_drift_is_reported_by_artifact_id() -> None:
    plan = _plan()
    graph = build_release_graph(plan, target="linux-x64")
    left = record_release_run(
        graph,
        plan,
        _receipts(plan, runner="runner-a"),
    )

    changed_receipts = []
    for node_id in plan.selected_nodes:
        suffix = "-changed" if node_id == "package" else ""
        changed_receipts.append(
            _receipt(
                plan,
                node_id,
                runner="runner-b",
                output_digest=_digest(f"stable-output:{node_id}{suffix}"),
            )
        )
    right = record_release_run(graph, plan, changed_receipts)

    decision = compare_release_runs(graph, left, right)

    assert decision.reproducible is False
    assert decision.mismatched_artifact_ids == ("output:package",)


def test_compare_rejects_runs_from_different_graph_identity() -> None:
    plan = _plan()
    graph = build_release_graph(plan, target="linux-x64")
    other = build_release_graph(plan, target="windows-x64")
    left = record_release_run(graph, plan, _receipts(plan))
    right = record_release_run(other, plan, _receipts(plan))

    with pytest.raises(ReleaseGraphError, match="graph digest"):
        compare_release_runs(graph, left, right)


def test_release_run_output_order_is_canonical() -> None:
    plan = _plan()
    graph = build_release_graph(plan, target="linux-x64")
    run = record_release_run(graph, plan, _receipts(plan))

    reversed_outputs = tuple(reversed(run.output_artifacts))
    with pytest.raises(ReleaseGraphError, match="ordering"):
        validate_release_run(
            replace(run, output_artifacts=reversed_outputs),
            graph,
        )
