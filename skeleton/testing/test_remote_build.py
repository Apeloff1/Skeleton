"""Regression tests for the hermetic remote-build contract (#807 B008)."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from skeleton.build.incremental_graph import build_incremental_graph
from skeleton.build.remote_build import (
    RemoteArtifactRef,
    RemoteBuildError,
    RemoteExecutionSpec,
    RemoteJobReceipt,
    build_remote_plan,
    build_transfer_manifest,
    resume_missing_chunks,
    toolchain_manifest_digest,
    verify_remote_receipt,
    verify_transfer_chunks,
)


SOURCE_COMMIT = "1" * 40
TOOLCHAIN_DIGEST = "2" * 64


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _graph():
    return build_incremental_graph(
        [
            {"id": "src-a", "inputs": {"blob": "a"}},
            {"id": "src-b", "inputs": {"blob": "b"}},
            {"id": "compile-a", "dependencies": ["src-a"]},
            {"id": "compile-b", "dependencies": ["src-b"]},
            {"id": "link", "dependencies": ["compile-a", "compile-b"]},
            {"id": "docs", "inputs": {"blob": "docs"}},
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


def _plan(targets=None):
    graph = _graph()
    selected = (
        graph.topological_order
        if targets is None
        else ("src-a", "src-b", "compile-a", "compile-b", "link")
    )
    return build_remote_plan(
        graph,
        source_commit=SOURCE_COMMIT,
        toolchain_digest=TOOLCHAIN_DIGEST,
        executions=[_spec(node_id) for node_id in selected],
        targets=targets,
    )


def test_initial_ready_jobs_are_independent_and_parallelizable() -> None:
    plan = _plan()

    ready = {job.node_id for job in plan.ready_jobs()}

    assert ready == {"src-a", "src-b", "docs"}
    assert all(job.network_access is False for job in plan.jobs)


def test_dependencies_unlock_only_after_required_jobs_complete() -> None:
    plan = _plan()
    by_node = plan.node_job_map()

    completed = {
        by_node["src-a"].job_id,
        by_node["src-b"].job_id,
        by_node["docs"].job_id,
    }
    ready = {job.node_id for job in plan.ready_jobs(completed)}

    assert ready == {"compile-a", "compile-b"}

    completed.update(
        {
            by_node["compile-a"].job_id,
            by_node["compile-b"].job_id,
        }
    )
    ready = {job.node_id for job in plan.ready_jobs(completed)}
    assert ready == {"link"}


def test_target_plan_is_dependency_closed_and_excludes_unrelated_docs() -> None:
    plan = _plan(targets=["link"])

    assert set(plan.selected_nodes) == {
        "src-a",
        "src-b",
        "compile-a",
        "compile-b",
        "link",
    }
    assert "docs" not in plan.selected_nodes


def test_execution_spec_order_does_not_change_plan_identity() -> None:
    graph = _graph()
    specs = [_spec(node_id) for node_id in graph.topological_order]

    left = build_remote_plan(
        graph,
        source_commit=SOURCE_COMMIT,
        toolchain_digest=TOOLCHAIN_DIGEST,
        executions=specs,
    )
    right = build_remote_plan(
        graph,
        source_commit=SOURCE_COMMIT,
        toolchain_digest=TOOLCHAIN_DIGEST,
        executions=list(reversed(specs)),
    )

    assert left == right
    assert left.plan_fingerprint == right.plan_fingerprint
    assert left.serialize() == right.serialize()
    assert left.serialize() == json.dumps(
        json.loads(left.serialize()),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def test_forged_plan_derived_fields_fail_closed() -> None:
    plan = _plan()
    first = plan.jobs[0]

    assert {job.node_id for job in plan.ready_jobs()} == {"src-a", "src-b", "docs"}

    forged_plan = replace(plan, plan_fingerprint="0" * 64)
    with pytest.raises(RemoteBuildError, match="plan fingerprint"):
        forged_plan.ready_jobs()

    forged_job = replace(first, network_access=True)
    forged_jobs = (forged_job, *plan.jobs[1:])
    with pytest.raises(RemoteBuildError, match="authority/provenance"):
        replace(plan, jobs=forged_jobs).ready_jobs()


def test_completed_job_set_must_be_dependency_closed() -> None:
    plan = _plan()
    by_node = plan.node_job_map()

    with pytest.raises(RemoteBuildError, match="dependency-closed"):
        plan.ready_jobs([by_node["compile-a"].job_id])


def test_source_toolchain_or_command_change_changes_job_identity() -> None:
    graph = _graph()
    specs = [_spec(node_id) for node_id in graph.topological_order]
    baseline = build_remote_plan(
        graph,
        source_commit=SOURCE_COMMIT,
        toolchain_digest=TOOLCHAIN_DIGEST,
        executions=specs,
    )

    changed_source = build_remote_plan(
        graph,
        source_commit="3" * 40,
        toolchain_digest=TOOLCHAIN_DIGEST,
        executions=specs,
    )
    changed_toolchain = build_remote_plan(
        graph,
        source_commit=SOURCE_COMMIT,
        toolchain_digest="4" * 64,
        executions=specs,
    )
    changed_specs = list(specs)
    changed_specs[0] = replace(
        changed_specs[0],
        argv=("python", "-m", "builder", "different"),
    )
    changed_command = build_remote_plan(
        graph,
        source_commit=SOURCE_COMMIT,
        toolchain_digest=TOOLCHAIN_DIGEST,
        executions=changed_specs,
    )

    assert baseline.plan_fingerprint != changed_source.plan_fingerprint
    assert baseline.plan_fingerprint != changed_toolchain.plan_fingerprint
    assert baseline.plan_fingerprint != changed_command.plan_fingerprint


@pytest.mark.parametrize(
    "argv",
    [
        ("bash", "-c", "echo unsafe"),
        ("sh", "script.sh"),
        ("pwsh", "-Command", "Write-Host unsafe"),
        ("cmd.exe", "/c", "echo unsafe"),
    ],
)
def test_shell_wrappers_are_rejected(argv: tuple[str, ...]) -> None:
    graph = build_incremental_graph([{"id": "node", "inputs": {"x": "y"}}])

    with pytest.raises(RemoteBuildError, match="shell wrappers"):
        build_remote_plan(
            graph,
            source_commit=SOURCE_COMMIT,
            toolchain_digest=TOOLCHAIN_DIGEST,
            executions=[RemoteExecutionSpec(node_id="node", argv=argv)],
        )


def test_execution_specs_must_exactly_cover_selected_nodes() -> None:
    graph = _graph()

    with pytest.raises(RemoteBuildError, match="exactly cover"):
        build_remote_plan(
            graph,
            source_commit=SOURCE_COMMIT,
            toolchain_digest=TOOLCHAIN_DIGEST,
            executions=[_spec("src-a")],
        )

    specs = [_spec(node_id) for node_id in graph.topological_order]
    specs.append(_spec("extra"))
    with pytest.raises(RemoteBuildError):
        build_remote_plan(
            graph,
            source_commit=SOURCE_COMMIT,
            toolchain_digest=TOOLCHAIN_DIGEST,
            executions=specs,
        )


def test_root_write_and_traversal_paths_are_rejected() -> None:
    graph = build_incremental_graph([{"id": "node", "inputs": {"x": "y"}}])

    with pytest.raises(RemoteBuildError):
        build_remote_plan(
            graph,
            source_commit=SOURCE_COMMIT,
            toolchain_digest=TOOLCHAIN_DIGEST,
            executions=[
                RemoteExecutionSpec(
                    node_id="node",
                    argv=("python", "build.py"),
                    writable_paths=(".",),
                )
            ],
        )

    with pytest.raises(RemoteBuildError):
        build_remote_plan(
            graph,
            source_commit=SOURCE_COMMIT,
            toolchain_digest=TOOLCHAIN_DIGEST,
            executions=[
                RemoteExecutionSpec(
                    node_id="node",
                    argv=("python", "build.py"),
                    working_directory="../escape",
                )
            ],
        )


def test_transfer_manifest_resumes_only_missing_verified_chunks() -> None:
    chunks = [b"alpha", b"beta", b"gamma"]
    manifest = build_transfer_manifest("artifact:one", chunks)

    missing = resume_missing_chunks(
        manifest,
        {
            0: hashlib.sha256(chunks[0]).hexdigest(),
            2: hashlib.sha256(chunks[2]).hexdigest(),
        },
    )

    assert [chunk.index for chunk in missing] == [1]
    assert manifest.size_bytes == sum(map(len, chunks))
    assert manifest.sha256 == hashlib.sha256(b"".join(chunks)).hexdigest()


def test_resume_rejects_wrong_or_unknown_chunk_claim() -> None:
    manifest = build_transfer_manifest("artifact:one", [b"alpha", b"beta"])

    with pytest.raises(RemoteBuildError, match="digest mismatch"):
        resume_missing_chunks(manifest, {0: "0" * 64})

    with pytest.raises(RemoteBuildError, match="outside manifest"):
        resume_missing_chunks(manifest, {9: "0" * 64})


def test_complete_transfer_verifies_chunk_and_aggregate_integrity() -> None:
    chunks = {0: b"alpha", 1: b"beta", 2: b"gamma"}
    manifest = build_transfer_manifest("artifact:one", chunks.values())

    ref = verify_transfer_chunks(manifest, chunks)

    assert ref.artifact_id == "artifact:one"
    assert ref.sha256 == manifest.sha256
    assert ref.size_bytes == manifest.size_bytes

    tampered = dict(chunks)
    tampered[1] = b"BETa"
    with pytest.raises(RemoteBuildError, match="chunk"):
        verify_transfer_chunks(manifest, tampered)


def test_transfer_manifest_tampering_is_detected() -> None:
    manifest = build_transfer_manifest("artifact:one", [b"alpha", b"beta"])

    with pytest.raises(RemoteBuildError, match="fingerprint mismatch"):
        resume_missing_chunks(
            replace(manifest, manifest_fingerprint="0" * 64),
            {},
        )


def test_success_receipt_binds_exact_declared_outputs_and_provenance() -> None:
    plan = _plan(targets=["link"])
    job = plan.node_job_map()["link"]
    output = RemoteArtifactRef(
        artifact_id="output:link",
        sha256=_digest("linked-output"),
        size_bytes=123,
    )
    receipt = RemoteJobReceipt(
        job_id=job.job_id,
        plan_fingerprint=plan.plan_fingerprint,
        source_commit=plan.source_commit,
        toolchain_digest=plan.toolchain_digest,
        runner_id="runner:linux-x86_64:01",
        status="success",
        output_artifacts=(output,),
        log_digest=_digest("build-log"),
    )

    verified = verify_remote_receipt(plan, receipt)

    assert verified.status == "success"
    assert verified.output_artifacts == (output,)
    assert len(verified.receipt_digest) == 64


def test_receipt_provenance_mismatch_fails_closed() -> None:
    plan = _plan(targets=["link"])
    job = plan.node_job_map()["link"]
    output = RemoteArtifactRef("output:link", _digest("out"), 3)
    receipt = RemoteJobReceipt(
        job_id=job.job_id,
        plan_fingerprint=plan.plan_fingerprint,
        source_commit=plan.source_commit,
        toolchain_digest=plan.toolchain_digest,
        runner_id="runner:1",
        status="success",
        output_artifacts=(output,),
        log_digest=_digest("log"),
    )

    with pytest.raises(RemoteBuildError, match="plan fingerprint"):
        verify_remote_receipt(
            plan,
            replace(receipt, plan_fingerprint="0" * 64),
        )
    with pytest.raises(RemoteBuildError, match="toolchain"):
        verify_remote_receipt(
            plan,
            replace(receipt, toolchain_digest="0" * 64),
        )
    with pytest.raises(RemoteBuildError, match="output set"):
        verify_remote_receipt(
            plan,
            replace(receipt, output_artifacts=()),
        )


def test_failed_receipt_cannot_publish_outputs() -> None:
    plan = _plan(targets=["link"])
    job = plan.node_job_map()["link"]

    with pytest.raises(RemoteBuildError, match="must not publish"):
        verify_remote_receipt(
            plan,
            RemoteJobReceipt(
                job_id=job.job_id,
                plan_fingerprint=plan.plan_fingerprint,
                source_commit=plan.source_commit,
                toolchain_digest=plan.toolchain_digest,
                runner_id="runner:1",
                status="failure",
                output_artifacts=(
                    RemoteArtifactRef("output:link", _digest("out"), 3),
                ),
                log_digest=_digest("log"),
            ),
        )


def test_toolchain_manifest_digest_is_order_independent() -> None:
    left = toolchain_manifest_digest(
        {"tools": {"python": "3.11.16", "node": "24.20.0"}, "schema": 1}
    )
    right = toolchain_manifest_digest(
        {"schema": 1, "tools": {"node": "24.20.0", "python": "3.11.16"}}
    )
    assert left == right
