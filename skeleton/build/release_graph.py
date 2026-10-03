"""Deterministic reproducible release graph for B010.

B010 binds release recipes to the exact B008 remote-build plan plus explicit
model, asset, configuration, target, source, graph, and toolchain identities.
It does not execute builds or promote releases. It records and compares
content-addressed successful B008 evidence so the existing release evidence
and qualification plane can make downstream policy decisions.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
import re

from skeleton.build.remote_build import (
    REMOTE_BUILD_ALGORITHM,
    REMOTE_BUILD_SCHEMA,
    RemoteArtifactRef,
    RemoteBuildPlan,
    VerifiedRemoteReceipt,
    validate_remote_plan,
)
from skeleton.kernel.errors import SkeletonError


RELEASE_GRAPH_SCHEMA = 1
RELEASE_GRAPH_ALGORITHM = "sha256"
MAX_NAMED_DIGESTS = 4096
MAX_STEPS = 4096
MAX_OUTPUTS = 16384
MAX_ID_CHARS = 256
MAX_SERIALIZED_BYTES = 8 * 1024 * 1024

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,255}$")


class ReleaseGraphError(SkeletonError):
    """Release recipe or reproducibility evidence is invalid."""

    code = "BUILD.RELEASE_GRAPH"
    http_status = 400


@dataclass(frozen=True, slots=True)
class NamedDigest:
    name: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class ReleaseStep:
    step_id: str
    job_id: str
    dependency_step_ids: tuple[str, ...]
    output_artifact_ids: tuple[str, ...]
    recipe_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "job_id": self.job_id,
            "dependency_step_ids": list(self.dependency_step_ids),
            "output_artifact_ids": list(self.output_artifact_ids),
            "recipe_digest": self.recipe_digest,
        }


@dataclass(frozen=True, slots=True)
class ReleaseGraph:
    schema: int
    algorithm: str
    source_commit: str
    graph_fingerprint: str
    remote_plan_fingerprint: str
    toolchain_digest: str
    target: str
    models: tuple[NamedDigest, ...]
    assets: tuple[NamedDigest, ...]
    configs: tuple[NamedDigest, ...]
    steps: tuple[ReleaseStep, ...]
    digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "source_commit": self.source_commit,
            "graph_fingerprint": self.graph_fingerprint,
            "remote_plan_fingerprint": self.remote_plan_fingerprint,
            "toolchain_digest": self.toolchain_digest,
            "target": self.target,
            "models": [item.to_dict() for item in self.models],
            "assets": [item.to_dict() for item in self.assets],
            "configs": [item.to_dict() for item in self.configs],
            "steps": [step.to_dict() for step in self.steps],
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class ReleaseRun:
    graph_digest: str
    receipt_digests: tuple[str, ...]
    output_artifacts: tuple[RemoteArtifactRef, ...]
    run_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "graph_digest": self.graph_digest,
            "receipt_digests": list(self.receipt_digests),
            "output_artifacts": [item.to_dict() for item in self.output_artifacts],
            "run_digest": self.run_digest,
        }


@dataclass(frozen=True, slots=True)
class ReproducibilityDecision:
    graph_digest: str
    left_run_digest: str
    right_run_digest: str
    reproducible: bool
    mismatched_artifact_ids: tuple[str, ...]
    decision_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "graph_digest": self.graph_digest,
            "left_run_digest": self.left_run_digest,
            "right_run_digest": self.right_run_digest,
            "reproducible": self.reproducible,
            "mismatched_artifact_ids": list(self.mismatched_artifact_ids),
            "decision_digest": self.decision_digest,
        }


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_sha1(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA1_RE.fullmatch(value) is None:
        raise ReleaseGraphError(f"{field} must be a lowercase sha1 digest")
    return value


def _require_sha256(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ReleaseGraphError(f"{field} must be a lowercase sha256 digest")
    return value


def _require_id(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_ID_CHARS
        or _ID_RE.fullmatch(value) is None
    ):
        raise ReleaseGraphError(f"{field} is not a canonical identifier")
    return value


def _named_digests(
    values: Mapping[str, str] | Iterable[NamedDigest | Mapping[str, str]],
    *,
    field: str,
) -> tuple[NamedDigest, ...]:
    if isinstance(values, Mapping):
        raw: Iterable[NamedDigest | Mapping[str, str]] = (
            NamedDigest(name=name, sha256=digest) for name, digest in values.items()
        )
    else:
        raw = values
    result: list[NamedDigest] = []
    seen: set[str] = set()
    for index, value in enumerate(raw, start=1):
        if index > MAX_NAMED_DIGESTS:
            raise ReleaseGraphError(f"{field} exceeds its item bound")
        if isinstance(value, NamedDigest):
            item = value
        elif isinstance(value, Mapping) and set(value) == {"name", "sha256"}:
            item = NamedDigest(name=value["name"], sha256=value["sha256"])
        else:
            raise ReleaseGraphError(f"{field} contains malformed entries")
        name = _require_id(item.name, field=f"{field}.name")
        digest = _require_sha256(item.sha256, field=f"{field}.sha256")
        if name in seen:
            raise ReleaseGraphError(f"{field} contains duplicate names")
        seen.add(name)
        result.append(NamedDigest(name=name, sha256=digest))
    return tuple(sorted(result, key=lambda item: item.name))


def _graph_payload(
    *,
    plan: RemoteBuildPlan,
    target: str,
    models: tuple[NamedDigest, ...],
    assets: tuple[NamedDigest, ...],
    configs: tuple[NamedDigest, ...],
    steps: tuple[ReleaseStep, ...],
) -> dict[str, object]:
    return {
        "schema": RELEASE_GRAPH_SCHEMA,
        "algorithm": RELEASE_GRAPH_ALGORITHM,
        "source_commit": plan.source_commit,
        "graph_fingerprint": plan.graph_fingerprint,
        "remote_plan_fingerprint": plan.plan_fingerprint,
        "toolchain_digest": plan.toolchain_digest,
        "target": target,
        "models": [item.to_dict() for item in models],
        "assets": [item.to_dict() for item in assets],
        "configs": [item.to_dict() for item in configs],
        "steps": [step.to_dict() for step in steps],
    }


def build_release_graph(
    plan: RemoteBuildPlan,
    *,
    target: str,
    models: Mapping[str, str] | Iterable[NamedDigest | Mapping[str, str]] = (),
    assets: Mapping[str, str] | Iterable[NamedDigest | Mapping[str, str]] = (),
    configs: Mapping[str, str] | Iterable[NamedDigest | Mapping[str, str]] = (),
) -> ReleaseGraph:
    """Compile one exact B008 plan into a deterministic release recipe."""

    validate_remote_plan(plan)
    target_id = _require_id(target, field="target")
    normalized_models = _named_digests(models, field="models")
    normalized_assets = _named_digests(assets, field="assets")
    normalized_configs = _named_digests(configs, field="configs")

    if len(plan.jobs) > MAX_STEPS:
        raise ReleaseGraphError("remote plan exceeds release step bound")

    step_by_job: dict[str, ReleaseStep] = {}
    steps: list[ReleaseStep] = []
    material_identity = {
        "models": [item.to_dict() for item in normalized_models],
        "assets": [item.to_dict() for item in normalized_assets],
        "configs": [item.to_dict() for item in normalized_configs],
        "target": target_id,
    }
    for job in plan.jobs:
        dependencies = tuple(step_by_job[dep].step_id for dep in job.dependency_job_ids)
        recipe_payload = {
            "remote_job": job.to_dict(),
            "material_identity": material_identity,
        }
        recipe_digest = _sha256(recipe_payload)
        step_payload = {
            "job_id": job.job_id,
            "dependency_step_ids": list(dependencies),
            "output_artifact_ids": list(job.output_artifact_ids),
            "recipe_digest": recipe_digest,
        }
        step_id = _sha256(step_payload)
        step = ReleaseStep(
            step_id=step_id,
            job_id=job.job_id,
            dependency_step_ids=dependencies,
            output_artifact_ids=tuple(job.output_artifact_ids),
            recipe_digest=recipe_digest,
        )
        step_by_job[job.job_id] = step
        steps.append(step)

    step_tuple = tuple(steps)
    payload = _graph_payload(
        plan=plan,
        target=target_id,
        models=normalized_models,
        assets=normalized_assets,
        configs=normalized_configs,
        steps=step_tuple,
    )
    return ReleaseGraph(
        schema=RELEASE_GRAPH_SCHEMA,
        algorithm=RELEASE_GRAPH_ALGORITHM,
        source_commit=plan.source_commit,
        graph_fingerprint=plan.graph_fingerprint,
        remote_plan_fingerprint=plan.plan_fingerprint,
        toolchain_digest=plan.toolchain_digest,
        target=target_id,
        models=normalized_models,
        assets=normalized_assets,
        configs=normalized_configs,
        steps=step_tuple,
        digest=_sha256(payload),
    )


def validate_release_graph(graph: ReleaseGraph, plan: RemoteBuildPlan) -> None:
    """Recompute all graph and step identities against the exact B008 plan."""

    if not isinstance(graph, ReleaseGraph):
        raise ReleaseGraphError("graph must be a ReleaseGraph")
    validate_remote_plan(plan)
    if graph.schema != RELEASE_GRAPH_SCHEMA or graph.algorithm != RELEASE_GRAPH_ALGORITHM:
        raise ReleaseGraphError("release graph schema/algorithm mismatch")
    _require_sha1(graph.source_commit, field="source_commit")
    _require_sha256(graph.graph_fingerprint, field="graph_fingerprint")
    _require_sha256(graph.remote_plan_fingerprint, field="remote_plan_fingerprint")
    _require_sha256(graph.toolchain_digest, field="toolchain_digest")
    if graph.source_commit != plan.source_commit:
        raise ReleaseGraphError("release graph source commit drifted")
    if graph.graph_fingerprint != plan.graph_fingerprint:
        raise ReleaseGraphError("release graph build graph fingerprint drifted")
    if graph.remote_plan_fingerprint != plan.plan_fingerprint:
        raise ReleaseGraphError("release graph remote plan fingerprint drifted")
    if graph.toolchain_digest != plan.toolchain_digest:
        raise ReleaseGraphError("release graph toolchain digest drifted")

    rebuilt = build_release_graph(
        plan,
        target=graph.target,
        models=graph.models,
        assets=graph.assets,
        configs=graph.configs,
    )
    if graph != rebuilt:
        raise ReleaseGraphError("release graph derived identity mismatch")


def serialize_release_graph(graph: ReleaseGraph, plan: RemoteBuildPlan) -> str:
    validate_release_graph(graph, plan)
    raw = _canonical_json(graph.to_dict())
    if len(raw.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        raise ReleaseGraphError("serialized release graph exceeds byte bound")
    return raw


def _receipt_digest(plan: RemoteBuildPlan, receipt: VerifiedRemoteReceipt) -> str:
    jobs = plan.job_map()
    job = jobs.get(receipt.job_id)
    if job is None:
        raise ReleaseGraphError("receipt references unknown remote job")
    runner_id = _require_id(receipt.runner_id, field="runner_id")
    if receipt.status != "success":
        raise ReleaseGraphError("release run requires successful remote receipts")
    log_digest = _require_sha256(receipt.log_digest, field="log_digest")
    outputs: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for raw in receipt.output_artifacts:
        if not isinstance(raw, RemoteArtifactRef):
            raise ReleaseGraphError("verified receipt output must be RemoteArtifactRef")
        artifact_id = _require_id(raw.artifact_id, field="artifact_id")
        sha256 = _require_sha256(raw.sha256, field="artifact.sha256")
        if (
            isinstance(raw.size_bytes, bool)
            or not isinstance(raw.size_bytes, int)
            or raw.size_bytes < 0
        ):
            raise ReleaseGraphError("artifact size must be a non-negative integer")
        if artifact_id in seen:
            raise ReleaseGraphError("receipt contains duplicate output artifact id")
        seen.add(artifact_id)
        outputs.append(
            RemoteArtifactRef(
                artifact_id=artifact_id,
                sha256=sha256,
                size_bytes=raw.size_bytes,
            )
        )
    output_ids = tuple(item.artifact_id for item in outputs)
    if output_ids != job.output_artifact_ids:
        raise ReleaseGraphError("receipt output set does not match remote job declaration")
    payload = {
        "schema": REMOTE_BUILD_SCHEMA,
        "algorithm": REMOTE_BUILD_ALGORITHM,
        "job_id": job.job_id,
        "plan_fingerprint": plan.plan_fingerprint,
        "source_commit": plan.source_commit,
        "toolchain_digest": plan.toolchain_digest,
        "runner_id": runner_id,
        "status": "success",
        "output_artifacts": [item.to_dict() for item in outputs],
        "log_digest": log_digest,
    }
    expected = _sha256(payload)
    if receipt.receipt_digest != expected:
        raise ReleaseGraphError("verified remote receipt digest mismatch")
    return expected


def _run_payload(
    *,
    graph_digest: str,
    receipt_digests: tuple[str, ...],
    outputs: tuple[RemoteArtifactRef, ...],
) -> dict[str, object]:
    return {
        "graph_digest": graph_digest,
        "receipt_digests": list(receipt_digests),
        "output_artifacts": [item.to_dict() for item in outputs],
    }


def record_release_run(
    graph: ReleaseGraph,
    plan: RemoteBuildPlan,
    receipts: Iterable[VerifiedRemoteReceipt],
) -> ReleaseRun:
    """Bind exact successful B008 receipts into one reproducibility run."""

    validate_release_graph(graph, plan)
    by_job: dict[str, VerifiedRemoteReceipt] = {}
    for index, receipt in enumerate(receipts, start=1):
        if index > MAX_STEPS:
            raise ReleaseGraphError("receipt set exceeds step bound")
        if not isinstance(receipt, VerifiedRemoteReceipt):
            raise ReleaseGraphError("receipts must be VerifiedRemoteReceipt values")
        if receipt.job_id in by_job:
            raise ReleaseGraphError("duplicate remote job receipt")
        by_job[receipt.job_id] = receipt

    expected_job_ids = tuple(step.job_id for step in graph.steps)
    if set(by_job) != set(expected_job_ids):
        missing = sorted(set(expected_job_ids) - set(by_job))
        extra = sorted(set(by_job) - set(expected_job_ids))
        raise ReleaseGraphError(
            "release receipts must exactly cover release steps",
            context={"missing": missing[:16], "extra": extra[:16]},
        )

    receipt_digests: list[str] = []
    outputs: list[RemoteArtifactRef] = []
    seen_outputs: set[str] = set()
    for job_id in expected_job_ids:
        receipt = by_job[job_id]
        receipt_digests.append(_receipt_digest(plan, receipt))
        for artifact in receipt.output_artifacts:
            if artifact.artifact_id in seen_outputs:
                raise ReleaseGraphError("output artifact id is produced by multiple jobs")
            seen_outputs.add(artifact.artifact_id)
            outputs.append(artifact)
            if len(outputs) > MAX_OUTPUTS:
                raise ReleaseGraphError("release output set exceeds bound")

    output_tuple = tuple(sorted(outputs, key=lambda item: item.artifact_id))
    receipt_tuple = tuple(receipt_digests)
    payload = _run_payload(
        graph_digest=graph.digest,
        receipt_digests=receipt_tuple,
        outputs=output_tuple,
    )
    return ReleaseRun(
        graph_digest=graph.digest,
        receipt_digests=receipt_tuple,
        output_artifacts=output_tuple,
        run_digest=_sha256(payload),
    )


def validate_release_run(run: ReleaseRun, graph: ReleaseGraph) -> None:
    if not isinstance(run, ReleaseRun):
        raise ReleaseGraphError("run must be a ReleaseRun")
    if run.graph_digest != graph.digest:
        raise ReleaseGraphError("release run graph digest mismatch")
    if len(run.receipt_digests) != len(graph.steps):
        raise ReleaseGraphError("release receipt digest count does not match graph steps")
    for digest in run.receipt_digests:
        _require_sha256(digest, field="receipt_digest")

    seen: set[str] = set()
    normalized: list[RemoteArtifactRef] = []
    for artifact in run.output_artifacts:
        if not isinstance(artifact, RemoteArtifactRef):
            raise ReleaseGraphError("release output must be RemoteArtifactRef")
        artifact_id = _require_id(artifact.artifact_id, field="artifact_id")
        digest = _require_sha256(artifact.sha256, field="artifact.sha256")
        if (
            isinstance(artifact.size_bytes, bool)
            or not isinstance(artifact.size_bytes, int)
            or artifact.size_bytes < 0
        ):
            raise ReleaseGraphError("artifact size must be a non-negative integer")
        if artifact_id in seen:
            raise ReleaseGraphError("release run contains duplicate output artifact id")
        seen.add(artifact_id)
        normalized.append(
            RemoteArtifactRef(
                artifact_id=artifact_id,
                sha256=digest,
                size_bytes=artifact.size_bytes,
            )
        )
    if tuple(sorted(normalized, key=lambda item: item.artifact_id)) != run.output_artifacts:
        raise ReleaseGraphError("release output ordering is not canonical")
    expected_output_ids = {
        artifact_id
        for step in graph.steps
        for artifact_id in step.output_artifact_ids
    }
    if seen != expected_output_ids:
        raise ReleaseGraphError("release output set does not match graph declarations")
    expected = _sha256(
        _run_payload(
            graph_digest=graph.digest,
            receipt_digests=run.receipt_digests,
            outputs=run.output_artifacts,
        )
    )
    if run.run_digest != expected:
        raise ReleaseGraphError("release run digest mismatch")


def compare_release_runs(
    graph: ReleaseGraph,
    left: ReleaseRun,
    right: ReleaseRun,
) -> ReproducibilityDecision:
    """Compare output bytes, not runner or log identities, for reproducibility."""

    validate_release_run(left, graph)
    validate_release_run(right, graph)
    left_map = {item.artifact_id: item for item in left.output_artifacts}
    right_map = {item.artifact_id: item for item in right.output_artifacts}
    all_ids = sorted(set(left_map) | set(right_map))
    mismatched = tuple(
        artifact_id
        for artifact_id in all_ids
        if left_map.get(artifact_id) != right_map.get(artifact_id)
    )
    payload = {
        "graph_digest": graph.digest,
        "left_run_digest": left.run_digest,
        "right_run_digest": right.run_digest,
        "reproducible": not mismatched,
        "mismatched_artifact_ids": list(mismatched),
    }
    return ReproducibilityDecision(
        graph_digest=graph.digest,
        left_run_digest=left.run_digest,
        right_run_digest=right.run_digest,
        reproducible=not mismatched,
        mismatched_artifact_ids=mismatched,
        decision_digest=_sha256(payload),
    )


__all__ = [
    "MAX_NAMED_DIGESTS",
    "MAX_OUTPUTS",
    "MAX_SERIALIZED_BYTES",
    "MAX_STEPS",
    "NamedDigest",
    "RELEASE_GRAPH_ALGORITHM",
    "RELEASE_GRAPH_SCHEMA",
    "ReleaseGraph",
    "ReleaseGraphError",
    "ReleaseRun",
    "ReleaseStep",
    "ReproducibilityDecision",
    "build_release_graph",
    "compare_release_runs",
    "record_release_run",
    "serialize_release_graph",
    "validate_release_graph",
    "validate_release_run",
]
