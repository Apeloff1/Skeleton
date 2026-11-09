"""Hermetic remote-build job, transfer, and provenance contracts (#807 B008).

This module is deliberately non-executing. It compiles B002 graph nodes into
content-addressed remote job specifications bound to an immutable source commit
and B004 toolchain digest. Runtime adapters may execute the emitted argv with
shell=False, but this module grants no network capability and accepts no shell
wrapper commands.

Artifact transfer is chunk-addressed and resumable. Success receipts must bind
the exact plan/job/source/toolchain and the exact declared output set.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any, Iterable, Mapping, Sequence

from skeleton.build.incremental_graph import IncrementalBuildGraph
from skeleton.kernel.errors import SkeletonError


REMOTE_BUILD_SCHEMA = 1
REMOTE_BUILD_ALGORITHM = "sha256"
MAX_JOBS = 4096
MAX_ARGV = 128
MAX_TOKEN_LENGTH = 2048
MAX_PATHS = 128
MAX_ARTIFACTS = 256
MAX_ARTIFACT_BYTES = 1 << 50
MAX_CHUNKS = 65536
MAX_CHUNK_BYTES = 16 * 1024 * 1024
MAX_CLOSURE_VISITS = 65536
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
FORBIDDEN_SHELLS = frozenset(
    {
        "sh",
        "bash",
        "zsh",
        "fish",
        "cmd",
        "cmd.exe",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
    }
)
RECEIPT_STATUSES = frozenset({"success", "failure", "cancelled"})


class RemoteBuildError(SkeletonError):
    """Remote-build contract input or evidence is invalid."""

    code = "BUILD.REMOTE_CONTRACT"
    http_status = 400


@dataclass(frozen=True, slots=True)
class RemoteArtifactRef:
    artifact_id: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class RemoteExecutionSpec:
    node_id: str
    argv: Sequence[str]
    input_artifacts: Sequence[RemoteArtifactRef | Mapping[str, Any]] = ()
    output_artifact_ids: Sequence[str] = ()
    working_directory: str = "."
    writable_paths: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class RemoteBuildJob:
    job_id: str
    node_id: str
    node_fingerprint: str
    graph_fingerprint: str
    source_commit: str
    toolchain_digest: str
    dependency_job_ids: tuple[str, ...]
    argv: tuple[str, ...]
    input_artifacts: tuple[RemoteArtifactRef, ...]
    output_artifact_ids: tuple[str, ...]
    working_directory: str
    writable_paths: tuple[str, ...]
    network_access: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "node_id": self.node_id,
            "node_fingerprint": self.node_fingerprint,
            "graph_fingerprint": self.graph_fingerprint,
            "source_commit": self.source_commit,
            "toolchain_digest": self.toolchain_digest,
            "dependency_job_ids": list(self.dependency_job_ids),
            "argv": list(self.argv),
            "input_artifacts": [item.to_dict() for item in self.input_artifacts],
            "output_artifact_ids": list(self.output_artifact_ids),
            "working_directory": self.working_directory,
            "writable_paths": list(self.writable_paths),
            "network_access": self.network_access,
        }


@dataclass(frozen=True, slots=True)
class RemoteBuildPlan:
    schema: int
    algorithm: str
    source_commit: str
    graph_fingerprint: str
    toolchain_digest: str
    selected_nodes: tuple[str, ...]
    jobs: tuple[RemoteBuildJob, ...]
    plan_fingerprint: str

    def job_map(self) -> dict[str, RemoteBuildJob]:
        return {job.job_id: job for job in self.jobs}

    def node_job_map(self) -> dict[str, RemoteBuildJob]:
        return {job.node_id: job for job in self.jobs}

    def ready_jobs(self, completed_job_ids: Iterable[str] = ()) -> tuple[RemoteBuildJob, ...]:
        validate_remote_plan(self)
        completed = _normalize_completed(completed_job_ids, self.job_map())
        return tuple(
            job
            for job in self.jobs
            if job.job_id not in completed
            and all(dep in completed for dep in job.dependency_job_ids)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "source_commit": self.source_commit,
            "graph_fingerprint": self.graph_fingerprint,
            "toolchain_digest": self.toolchain_digest,
            "selected_nodes": list(self.selected_nodes),
            "jobs": [job.to_dict() for job in self.jobs],
            "plan_fingerprint": self.plan_fingerprint,
        }

    def serialize(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class TransferChunk:
    index: int
    offset: int
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "offset": self.offset,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class ArtifactTransferManifest:
    schema: int
    algorithm: str
    artifact_id: str
    size_bytes: int
    sha256: str
    chunks: tuple[TransferChunk, ...]
    manifest_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "artifact_id": self.artifact_id,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "manifest_fingerprint": self.manifest_fingerprint,
        }

    def serialize(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class RemoteJobReceipt:
    job_id: str
    plan_fingerprint: str
    source_commit: str
    toolchain_digest: str
    runner_id: str
    status: str
    output_artifacts: Sequence[RemoteArtifactRef | Mapping[str, Any]]
    log_digest: str


@dataclass(frozen=True, slots=True)
class VerifiedRemoteReceipt:
    job_id: str
    runner_id: str
    status: str
    output_artifacts: tuple[RemoteArtifactRef, ...]
    log_digest: str
    receipt_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "runner_id": self.runner_id,
            "status": self.status,
            "output_artifacts": [item.to_dict() for item in self.output_artifacts],
            "log_digest": self.log_digest,
            "receipt_digest": self.receipt_digest,
        }


def build_remote_plan(
    graph: IncrementalBuildGraph,
    *,
    source_commit: str,
    toolchain_digest: str,
    executions: Iterable[RemoteExecutionSpec | Mapping[str, Any]],
    targets: Sequence[str] | None = None,
) -> RemoteBuildPlan:
    """Compile exact graph nodes into hermetic content-addressed remote jobs."""

    if not isinstance(graph, IncrementalBuildGraph):
        raise RemoteBuildError("graph must be an IncrementalBuildGraph")
    source_commit = _require_sha1(source_commit, field="source_commit")
    toolchain_digest = _require_sha256(toolchain_digest, field="toolchain_digest")
    node_map = graph.node_map()
    selected = _selected_nodes(graph, targets)
    selected_set = set(selected)

    execution_map: dict[str, RemoteExecutionSpec] = {}
    for raw in _bounded_iterable(executions, field="executions", maximum=MAX_JOBS):
        spec = _coerce_execution(raw)
        if spec.node_id in execution_map:
            raise RemoteBuildError(
                "duplicate remote execution spec",
                context={"node_id": spec.node_id},
            )
        execution_map[spec.node_id] = spec

    missing = sorted(selected_set - set(execution_map))
    extra = sorted(set(execution_map) - selected_set)
    if missing or extra:
        raise RemoteBuildError(
            "remote execution specs must exactly cover selected graph nodes",
            context={"missing": missing[:16], "extra": extra[:16]},
        )

    jobs_by_node: dict[str, RemoteBuildJob] = {}
    jobs: list[RemoteBuildJob] = []
    for node_id in selected:
        node = node_map[node_id]
        spec = execution_map[node_id]
        dependency_jobs = tuple(
            jobs_by_node[dep].job_id
            for dep in node.dependencies
            if dep in selected_set
        )
        input_artifacts = _normalize_artifacts(spec.input_artifacts)
        output_ids = _normalize_ids(
            spec.output_artifact_ids,
            field="output_artifact_ids",
            maximum=MAX_ARTIFACTS,
        )
        argv = _normalize_argv(spec.argv)
        working_directory = _normalize_path(
            spec.working_directory,
            field="working_directory",
            allow_dot=True,
        )
        writable_paths = _normalize_paths(
            spec.writable_paths,
            field="writable_paths",
            maximum=MAX_PATHS,
            allow_dot=False,
        )
        payload = {
            "schema": REMOTE_BUILD_SCHEMA,
            "algorithm": REMOTE_BUILD_ALGORITHM,
            "node_id": node_id,
            "node_fingerprint": node.fingerprint,
            "graph_fingerprint": graph.fingerprint,
            "source_commit": source_commit,
            "toolchain_digest": toolchain_digest,
            "dependency_job_ids": list(dependency_jobs),
            "argv": list(argv),
            "input_artifacts": [item.to_dict() for item in input_artifacts],
            "output_artifact_ids": list(output_ids),
            "working_directory": working_directory,
            "writable_paths": list(writable_paths),
            "network_access": False,
        }
        job_id = _sha256(payload)
        job = RemoteBuildJob(
            job_id=job_id,
            node_id=node_id,
            node_fingerprint=node.fingerprint,
            graph_fingerprint=graph.fingerprint,
            source_commit=source_commit,
            toolchain_digest=toolchain_digest,
            dependency_job_ids=dependency_jobs,
            argv=argv,
            input_artifacts=input_artifacts,
            output_artifact_ids=output_ids,
            working_directory=working_directory,
            writable_paths=writable_paths,
        )
        jobs_by_node[node_id] = job
        jobs.append(job)

    plan_payload = {
        "schema": REMOTE_BUILD_SCHEMA,
        "algorithm": REMOTE_BUILD_ALGORITHM,
        "source_commit": source_commit,
        "graph_fingerprint": graph.fingerprint,
        "toolchain_digest": toolchain_digest,
        "selected_nodes": list(selected),
        "jobs": [job.to_dict() for job in jobs],
    }
    return RemoteBuildPlan(
        schema=REMOTE_BUILD_SCHEMA,
        algorithm=REMOTE_BUILD_ALGORITHM,
        source_commit=source_commit,
        graph_fingerprint=graph.fingerprint,
        toolchain_digest=toolchain_digest,
        selected_nodes=selected,
        jobs=tuple(jobs),
        plan_fingerprint=_sha256(plan_payload),
    )


def build_transfer_manifest(
    artifact_id: str,
    chunks: Iterable[bytes | bytearray | memoryview],
) -> ArtifactTransferManifest:
    """Hash a bounded chunk stream into a resumable transfer manifest."""

    artifact_id = _require_id(artifact_id, field="artifact_id")
    full_digest = hashlib.sha256()
    rows: list[TransferChunk] = []
    offset = 0
    for raw in chunks:
        if len(rows) >= MAX_CHUNKS:
            raise RemoteBuildError("artifact chunk count exceeds safety bound")
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise RemoteBuildError("artifact chunks must be bytes-like values")
        chunk = bytes(raw)
        if not chunk:
            raise RemoteBuildError("artifact chunks must not be empty")
        if len(chunk) > MAX_CHUNK_BYTES:
            raise RemoteBuildError("artifact chunk exceeds maximum byte size")
        if offset + len(chunk) > MAX_ARTIFACT_BYTES:
            raise RemoteBuildError("artifact exceeds maximum byte size")
        digest = hashlib.sha256(chunk).hexdigest()
        rows.append(
            TransferChunk(
                index=len(rows),
                offset=offset,
                size_bytes=len(chunk),
                sha256=digest,
            )
        )
        full_digest.update(chunk)
        offset += len(chunk)

    if not rows:
        raise RemoteBuildError("artifact transfer requires at least one chunk")
    payload = {
        "schema": REMOTE_BUILD_SCHEMA,
        "algorithm": REMOTE_BUILD_ALGORITHM,
        "artifact_id": artifact_id,
        "size_bytes": offset,
        "sha256": full_digest.hexdigest(),
        "chunks": [row.to_dict() for row in rows],
    }
    return ArtifactTransferManifest(
        schema=REMOTE_BUILD_SCHEMA,
        algorithm=REMOTE_BUILD_ALGORITHM,
        artifact_id=artifact_id,
        size_bytes=offset,
        sha256=payload["sha256"],
        chunks=tuple(rows),
        manifest_fingerprint=_sha256(payload),
    )


def resume_missing_chunks(
    manifest: ArtifactTransferManifest,
    received: Mapping[int, str],
) -> tuple[TransferChunk, ...]:
    """Return only missing chunks after validating every claimed received chunk."""

    _validate_transfer_manifest(manifest)
    if not isinstance(received, Mapping):
        raise RemoteBuildError("received chunk map must be a mapping")
    expected = {chunk.index: chunk for chunk in manifest.chunks}
    for raw_index, raw_digest in received.items():
        if isinstance(raw_index, bool) or not isinstance(raw_index, int):
            raise RemoteBuildError("received chunk index must be an integer")
        chunk = expected.get(raw_index)
        if chunk is None:
            raise RemoteBuildError(
                "received chunk index is outside manifest",
                context={"index": raw_index},
            )
        digest = _require_sha256(raw_digest, field="received chunk digest")
        if digest != chunk.sha256:
            raise RemoteBuildError(
                "received chunk digest mismatch",
                context={"index": raw_index},
            )
    return tuple(chunk for chunk in manifest.chunks if chunk.index not in received)


def verify_transfer_chunks(
    manifest: ArtifactTransferManifest,
    chunks: Mapping[int, bytes | bytearray | memoryview],
) -> RemoteArtifactRef:
    """Verify a complete chunk set against chunk and aggregate digests."""

    _validate_transfer_manifest(manifest)
    if not isinstance(chunks, Mapping):
        raise RemoteBuildError("chunk payloads must be a mapping")
    expected_indices = {chunk.index for chunk in manifest.chunks}
    supplied_indices = set(chunks)
    if supplied_indices != expected_indices:
        raise RemoteBuildError(
            "chunk payload set does not exactly cover transfer manifest"
        )

    digest = hashlib.sha256()
    total = 0
    for descriptor in manifest.chunks:
        raw = chunks[descriptor.index]
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise RemoteBuildError("chunk payload must be bytes-like")
        chunk = bytes(raw)
        if len(chunk) != descriptor.size_bytes:
            raise RemoteBuildError(
                "chunk size mismatch",
                context={"index": descriptor.index},
            )
        observed = hashlib.sha256(chunk).hexdigest()
        if observed != descriptor.sha256:
            raise RemoteBuildError(
                "chunk digest mismatch",
                context={"index": descriptor.index},
            )
        digest.update(chunk)
        total += len(chunk)
    if total != manifest.size_bytes or digest.hexdigest() != manifest.sha256:
        raise RemoteBuildError("aggregate artifact integrity mismatch")
    return RemoteArtifactRef(
        artifact_id=manifest.artifact_id,
        sha256=manifest.sha256,
        size_bytes=manifest.size_bytes,
    )


def verify_remote_receipt(
    plan: RemoteBuildPlan,
    receipt: RemoteJobReceipt,
) -> VerifiedRemoteReceipt:
    """Validate runner evidence against the exact remote job contract."""

    validate_remote_plan(plan)
    if not isinstance(receipt, RemoteJobReceipt):
        raise RemoteBuildError("receipt must be a RemoteJobReceipt")
    jobs = plan.job_map()
    job = jobs.get(receipt.job_id)
    if job is None:
        raise RemoteBuildError("receipt references unknown remote job")
    if receipt.plan_fingerprint != plan.plan_fingerprint:
        raise RemoteBuildError("receipt plan fingerprint mismatch")
    if receipt.source_commit != plan.source_commit:
        raise RemoteBuildError("receipt source commit mismatch")
    if receipt.toolchain_digest != plan.toolchain_digest:
        raise RemoteBuildError("receipt toolchain digest mismatch")
    runner_id = _require_id(receipt.runner_id, field="runner_id")
    if receipt.status not in RECEIPT_STATUSES:
        raise RemoteBuildError("unsupported remote receipt status")
    log_digest = _require_sha256(receipt.log_digest, field="log_digest")
    outputs = _normalize_artifacts(receipt.output_artifacts)
    output_ids = tuple(item.artifact_id for item in outputs)

    if receipt.status == "success":
        if output_ids != job.output_artifact_ids:
            raise RemoteBuildError(
                "successful receipt output set does not match job declaration",
                context={
                    "expected": list(job.output_artifact_ids),
                    "observed": list(output_ids),
                },
            )
    elif outputs:
        raise RemoteBuildError(
            "failed or cancelled receipt must not publish output artifacts"
        )

    payload = {
        "schema": REMOTE_BUILD_SCHEMA,
        "algorithm": REMOTE_BUILD_ALGORITHM,
        "job_id": job.job_id,
        "plan_fingerprint": plan.plan_fingerprint,
        "source_commit": plan.source_commit,
        "toolchain_digest": plan.toolchain_digest,
        "runner_id": runner_id,
        "status": receipt.status,
        "output_artifacts": [item.to_dict() for item in outputs],
        "log_digest": log_digest,
    }
    return VerifiedRemoteReceipt(
        job_id=job.job_id,
        runner_id=runner_id,
        status=receipt.status,
        output_artifacts=outputs,
        log_digest=log_digest,
        receipt_digest=_sha256(payload),
    )


def validate_remote_plan(plan: RemoteBuildPlan) -> None:
    """Recompute all derived job/plan identities and dependency ordering."""

    if not isinstance(plan, RemoteBuildPlan):
        raise RemoteBuildError("plan must be a RemoteBuildPlan")
    if plan.schema != REMOTE_BUILD_SCHEMA or plan.algorithm != REMOTE_BUILD_ALGORITHM:
        raise RemoteBuildError("remote plan schema/algorithm mismatch")
    source_commit = _require_sha1(plan.source_commit, field="source_commit")
    toolchain_digest = _require_sha256(
        plan.toolchain_digest,
        field="toolchain_digest",
    )
    graph_fingerprint = _require_sha256(
        plan.graph_fingerprint,
        field="graph_fingerprint",
    )
    if len(plan.jobs) > MAX_JOBS or len(plan.jobs) != len(plan.selected_nodes):
        raise RemoteBuildError("remote plan job count is invalid")

    seen_jobs: set[str] = set()
    seen_nodes: set[str] = set()
    observed_nodes: list[str] = []
    for job in plan.jobs:
        if not isinstance(job, RemoteBuildJob):
            raise RemoteBuildError("remote plan jobs must be RemoteBuildJob values")
        if job.node_id in seen_nodes:
            raise RemoteBuildError("remote plan contains duplicate node id")
        if job.job_id in seen_jobs:
            raise RemoteBuildError("remote plan contains duplicate job id")
        if (
            job.graph_fingerprint != graph_fingerprint
            or job.source_commit != source_commit
            or job.toolchain_digest != toolchain_digest
            or job.network_access is not False
        ):
            raise RemoteBuildError("remote job authority/provenance drifted from plan")

        dependency_ids = tuple(job.dependency_job_ids)
        if any(dep not in seen_jobs for dep in dependency_ids):
            raise RemoteBuildError(
                "remote job dependency must reference an earlier plan job"
            )
        payload = {
            "schema": REMOTE_BUILD_SCHEMA,
            "algorithm": REMOTE_BUILD_ALGORITHM,
            "node_id": job.node_id,
            "node_fingerprint": _require_sha256(
                job.node_fingerprint,
                field="node_fingerprint",
            ),
            "graph_fingerprint": graph_fingerprint,
            "source_commit": source_commit,
            "toolchain_digest": toolchain_digest,
            "dependency_job_ids": list(dependency_ids),
            "argv": list(_normalize_argv(job.argv)),
            "input_artifacts": [
                item.to_dict() for item in _normalize_artifacts(job.input_artifacts)
            ],
            "output_artifact_ids": list(
                _normalize_ids(
                    job.output_artifact_ids,
                    field="output_artifact_ids",
                    maximum=MAX_ARTIFACTS,
                )
            ),
            "working_directory": _normalize_path(
                job.working_directory,
                field="working_directory",
                allow_dot=True,
            ),
            "writable_paths": list(
                _normalize_paths(
                    job.writable_paths,
                    field="writable_paths",
                    maximum=MAX_PATHS,
                    allow_dot=False,
                )
            ),
            "network_access": False,
        }
        if _sha256(payload) != job.job_id:
            raise RemoteBuildError("remote job fingerprint mismatch")
        seen_jobs.add(job.job_id)
        seen_nodes.add(job.node_id)
        observed_nodes.append(job.node_id)

    if tuple(observed_nodes) != tuple(plan.selected_nodes):
        raise RemoteBuildError("remote plan selected_nodes drifted from jobs")
    plan_payload = {
        "schema": REMOTE_BUILD_SCHEMA,
        "algorithm": REMOTE_BUILD_ALGORITHM,
        "source_commit": source_commit,
        "graph_fingerprint": graph_fingerprint,
        "toolchain_digest": toolchain_digest,
        "selected_nodes": list(plan.selected_nodes),
        "jobs": [job.to_dict() for job in plan.jobs],
    }
    if _sha256(plan_payload) != plan.plan_fingerprint:
        raise RemoteBuildError("remote plan fingerprint mismatch")


def toolchain_manifest_digest(value: Mapping[str, Any]) -> str:
    """Return a canonical digest suitable for binding B004 into remote jobs."""

    if not isinstance(value, Mapping):
        raise RemoteBuildError("toolchain manifest must be a mapping")
    return _sha256(dict(value))


def _selected_nodes(
    graph: IncrementalBuildGraph,
    targets: Sequence[str] | None,
) -> tuple[str, ...]:
    node_map = graph.node_map()
    if targets is None:
        return tuple(graph.topological_order)
    normalized_targets = _normalize_ids(
        targets,
        field="targets",
        maximum=MAX_JOBS,
    )
    if not normalized_targets:
        raise RemoteBuildError("targets must not be empty")
    for node_id in normalized_targets:
        if node_id not in node_map:
            raise RemoteBuildError(
                "unknown remote build target",
                context={"node_id": node_id},
            )

    selected: set[str] = set()
    stack = list(reversed(normalized_targets))
    visits = 0
    while stack:
        visits += 1
        if visits > MAX_CLOSURE_VISITS:
            raise RemoteBuildError("target dependency closure exceeds visit bound")
        node_id = stack.pop()
        if node_id in selected:
            continue
        selected.add(node_id)
        stack.extend(reversed(node_map[node_id].dependencies))
    return tuple(
        node_id for node_id in graph.topological_order if node_id in selected
    )


def _coerce_execution(
    raw: RemoteExecutionSpec | Mapping[str, Any],
) -> RemoteExecutionSpec:
    if isinstance(raw, RemoteExecutionSpec):
        return RemoteExecutionSpec(
            node_id=_require_id(raw.node_id, field="node_id"),
            argv=raw.argv,
            input_artifacts=raw.input_artifacts,
            output_artifact_ids=raw.output_artifact_ids,
            working_directory=raw.working_directory,
            writable_paths=raw.writable_paths,
        )
    if not isinstance(raw, Mapping):
        raise RemoteBuildError("execution spec must be RemoteExecutionSpec or mapping")
    expected = {
        "node_id",
        "argv",
        "input_artifacts",
        "output_artifact_ids",
        "working_directory",
        "writable_paths",
    }
    extra = sorted(str(key) for key in raw if key not in expected)
    missing = sorted(key for key in ("node_id", "argv") if key not in raw)
    if extra or missing:
        raise RemoteBuildError(
            "execution spec keys mismatch",
            context={"missing": missing, "extra": extra},
        )
    return RemoteExecutionSpec(
        node_id=_require_id(raw["node_id"], field="node_id"),
        argv=raw["argv"],
        input_artifacts=raw.get("input_artifacts", ()),
        output_artifact_ids=raw.get("output_artifact_ids", ()),
        working_directory=raw.get("working_directory", "."),
        writable_paths=raw.get("writable_paths", ()),
    )


def _normalize_argv(value: Any) -> tuple[str, ...]:
    items = _bounded_iterable(value, field="argv", maximum=MAX_ARGV)
    if not items:
        raise RemoteBuildError("argv must not be empty")
    argv = tuple(
        _bounded_text(item, field="argv token", maximum=MAX_TOKEN_LENGTH)
        for item in items
    )
    executable = PurePosixPath(argv[0].replace("\\", "/")).name.lower()
    if executable in FORBIDDEN_SHELLS:
        raise RemoteBuildError(
            "remote jobs must invoke direct executables, not shell wrappers",
            context={"executable": executable},
        )
    return argv


def _normalize_artifacts(
    value: Any,
) -> tuple[RemoteArtifactRef, ...]:
    items = _bounded_iterable(
        value,
        field="artifacts",
        maximum=MAX_ARTIFACTS,
    )
    normalized: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for raw in items:
        if isinstance(raw, RemoteArtifactRef):
            artifact_id = _require_id(raw.artifact_id, field="artifact_id")
            sha256 = _require_sha256(raw.sha256, field="artifact sha256")
            size_bytes = _bounded_size(raw.size_bytes)
        elif isinstance(raw, Mapping):
            expected = {"artifact_id", "sha256", "size_bytes"}
            extra = sorted(str(key) for key in raw if key not in expected)
            missing = sorted(key for key in expected if key not in raw)
            if extra or missing:
                raise RemoteBuildError(
                    "artifact reference keys mismatch",
                    context={"missing": missing, "extra": extra},
                )
            artifact_id = _require_id(raw["artifact_id"], field="artifact_id")
            sha256 = _require_sha256(raw["sha256"], field="artifact sha256")
            size_bytes = _bounded_size(raw["size_bytes"])
        else:
            raise RemoteBuildError(
                "artifact reference must be RemoteArtifactRef or mapping"
            )
        if artifact_id in seen:
            raise RemoteBuildError(
                "duplicate artifact id",
                context={"artifact_id": artifact_id},
            )
        seen.add(artifact_id)
        normalized.append(
            RemoteArtifactRef(
                artifact_id=artifact_id,
                sha256=sha256,
                size_bytes=size_bytes,
            )
        )
    return tuple(sorted(normalized, key=lambda item: item.artifact_id))


def _validate_transfer_manifest(manifest: ArtifactTransferManifest) -> None:
    if not isinstance(manifest, ArtifactTransferManifest):
        raise RemoteBuildError("manifest must be an ArtifactTransferManifest")
    if manifest.schema != REMOTE_BUILD_SCHEMA:
        raise RemoteBuildError("unsupported transfer manifest schema")
    if manifest.algorithm != REMOTE_BUILD_ALGORITHM:
        raise RemoteBuildError("unsupported transfer manifest algorithm")
    artifact_id = _require_id(manifest.artifact_id, field="artifact_id")
    size_bytes = _bounded_size(manifest.size_bytes)
    sha256 = _require_sha256(manifest.sha256, field="artifact sha256")
    if not manifest.chunks or len(manifest.chunks) > MAX_CHUNKS:
        raise RemoteBuildError("transfer manifest chunk count is invalid")

    offset = 0
    for expected_index, chunk in enumerate(manifest.chunks):
        if not isinstance(chunk, TransferChunk):
            raise RemoteBuildError("transfer chunks must be TransferChunk values")
        if chunk.index != expected_index:
            raise RemoteBuildError("transfer chunk indices must be contiguous")
        if chunk.offset != offset:
            raise RemoteBuildError("transfer chunk offsets must be contiguous")
        if (
            isinstance(chunk.size_bytes, bool)
            or not isinstance(chunk.size_bytes, int)
            or chunk.size_bytes <= 0
            or chunk.size_bytes > MAX_CHUNK_BYTES
        ):
            raise RemoteBuildError("transfer chunk size is invalid")
        _require_sha256(chunk.sha256, field="chunk sha256")
        offset += chunk.size_bytes
    if offset != size_bytes:
        raise RemoteBuildError("transfer chunk sizes do not equal artifact size")

    payload = {
        "schema": REMOTE_BUILD_SCHEMA,
        "algorithm": REMOTE_BUILD_ALGORITHM,
        "artifact_id": artifact_id,
        "size_bytes": size_bytes,
        "sha256": sha256,
        "chunks": [chunk.to_dict() for chunk in manifest.chunks],
    }
    if _sha256(payload) != manifest.manifest_fingerprint:
        raise RemoteBuildError("transfer manifest fingerprint mismatch")


def _normalize_completed(
    value: Iterable[str],
    jobs: Mapping[str, RemoteBuildJob],
) -> frozenset[str]:
    items = _bounded_iterable(
        value,
        field="completed_job_ids",
        maximum=MAX_JOBS,
    )
    normalized: set[str] = set()
    for raw in items:
        job_id = _require_sha256(raw, field="completed job id")
        if job_id not in jobs:
            raise RemoteBuildError("completed job id is outside remote plan")
        normalized.add(job_id)
    for job_id in normalized:
        missing_dependencies = [
            dependency
            for dependency in jobs[job_id].dependency_job_ids
            if dependency not in normalized
        ]
        if missing_dependencies:
            raise RemoteBuildError(
                "completed job set is not dependency-closed",
                context={"job_id": job_id},
            )
    return frozenset(normalized)


def _normalize_paths(
    value: Any,
    *,
    field: str,
    maximum: int,
    allow_dot: bool,
) -> tuple[str, ...]:
    items = _bounded_iterable(value, field=field, maximum=maximum)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in items:
        path = _normalize_path(raw, field=field, allow_dot=allow_dot)
        if path in seen:
            raise RemoteBuildError(
                f"{field} contains duplicate path",
                context={"path": path},
            )
        seen.add(path)
        normalized.append(path)
    return tuple(sorted(normalized))


def _normalize_path(value: Any, *, field: str, allow_dot: bool) -> str:
    raw = _bounded_text(value, field=field, maximum=1024)
    if "\\" in raw:
        raise RemoteBuildError(f"{field} must use POSIX separators")
    if raw == ".":
        if allow_dot:
            return raw
        raise RemoteBuildError(f"{field} cannot grant repository-root write access")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RemoteBuildError(f"{field} contains an unsafe path")
    return path.as_posix()


def _normalize_ids(
    value: Any,
    *,
    field: str,
    maximum: int,
) -> tuple[str, ...]:
    items = _bounded_iterable(value, field=field, maximum=maximum)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in items:
        item = _require_id(raw, field=field)
        if item in seen:
            raise RemoteBuildError(
                f"{field} contains duplicate id",
                context={"id": item},
            )
        seen.add(item)
        normalized.append(item)
    return tuple(sorted(normalized))


def _bounded_iterable(
    value: Any,
    *,
    field: str,
    maximum: int,
) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        raise RemoteBuildError(f"{field} must be an iterable sequence")
    try:
        iterator = iter(value)
    except TypeError as exc:
        raise RemoteBuildError(f"{field} must be iterable") from exc
    items: list[Any] = []
    for item in iterator:
        if len(items) >= maximum:
            raise RemoteBuildError(f"{field} exceeds configured limit")
        items.append(item)
    return tuple(items)


def _require_id(value: Any, *, field: str) -> str:
    text = _bounded_text(value, field=field, maximum=256)
    if ID_RE.fullmatch(text) is None:
        raise RemoteBuildError(f"{field} contains unsupported characters")
    return text


def _require_sha1(value: Any, *, field: str) -> str:
    text = _bounded_text(value, field=field, maximum=40)
    if SHA1_RE.fullmatch(text) is None:
        raise RemoteBuildError(f"{field} must be a lowercase SHA-1")
    return text


def _require_sha256(value: Any, *, field: str) -> str:
    text = _bounded_text(value, field=field, maximum=64)
    if SHA256_RE.fullmatch(text) is None:
        raise RemoteBuildError(f"{field} must be a lowercase SHA-256")
    return text


def _bounded_size(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > MAX_ARTIFACT_BYTES
    ):
        raise RemoteBuildError("artifact size_bytes is out of range")
    return value


def _bounded_text(value: Any, *, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise RemoteBuildError(f"{field} must be a non-empty trimmed string")
    if len(value) > maximum or any(ch in value for ch in ("\x00", "\n", "\r")):
        raise RemoteBuildError(f"{field} contains invalid characters or length")
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RemoteBuildError("value is not canonically serializable") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


__all__ = [
    "REMOTE_BUILD_ALGORITHM",
    "REMOTE_BUILD_SCHEMA",
    "ArtifactTransferManifest",
    "RemoteArtifactRef",
    "RemoteBuildError",
    "RemoteBuildJob",
    "RemoteBuildPlan",
    "RemoteExecutionSpec",
    "RemoteJobReceipt",
    "TransferChunk",
    "VerifiedRemoteReceipt",
    "build_remote_plan",
    "build_transfer_manifest",
    "resume_missing_chunks",
    "toolchain_manifest_digest",
    "verify_remote_receipt",
    "verify_transfer_chunks",
    "validate_remote_plan",
]
