"""Console build projection in the existing governed game-workspace owner."""

from __future__ import annotations

import asyncio
import hashlib
import io
import time
import zipfile
from contextvars import ContextVar
from functools import partial
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

from core.game_learning import (
    GameLearningError,
    _digest as json_digest,
    _json,
    _key,
    _now,
    _public,
    _drain_executor,
    workspace,
)
from skeleton.jeeves.game_console_build import (
    MAX_ARTIFACT,
    MAX_ARTIFACTS,
    MAX_OUTPUT,
    BuildArtifact,
    BuildSourceTree,
    ConsoleBuildError,
    ConsoleBuildRequest,
    build_runner,
    console_build_catalog,
)

CHUNK_BYTES = 512 * 1024
ARTIFACT_COLLECTION = "game_learning_build_artifacts"
_ARTIFACT_DEPTH = ContextVar("compiled_artifact_authority_depth", default=0)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def build_catalog() -> dict[str, Any]:
    return {
        "schema_version": "skeleton.console_build.catalog.v1",
        "targets": await asyncio.to_thread(console_build_catalog),
        "isolated_runner_required": True,
        "hardware_execution_verified": False,
    }


async def inspect_build_plan(scope, project_id: str, body):
    """Prepare the actual fixed compiler plan, exposing only its public identity."""
    project = await workspace._project(project_id, scope, body["expected_version"])
    binding = await workspace._input(scope, project, require_execution=False)
    await workspace._authority(scope, binding)
    try:
        request = _request({"request": body, "input": binding})
        plan = await asyncio.to_thread(build_runner.plan, request)
    except ConsoleBuildError as exc:
        raise GameLearningError("build_plan_invalid", str(exc), 422) from exc
    await workspace._authority(scope, binding)
    current = await workspace._project(project_id, scope, project["version"])
    if json_digest(current["files"]) != json_digest(project["files"]):
        raise GameLearningError("build_source_changed", "Project changed during compiler preflight.", 409)
    adapter = plan["adapter"]
    missing = [
        "operator_sdk_missing" if str(item).startswith("/") else str(item)
        for item in plan["missing_dependencies"]
    ]
    state = (
        "source_only"
        if adapter["reason"]
        else "toolchain_missing" if missing else "build_available_unexecuted"
    )
    return {
        "schema_version": "skeleton.console_build.preflight.v1",
        "project_id": project_id,
        "project_version": project["version"],
        "head_digest": json_digest(project["files"]),
        "target_id": request.target_id,
        "style_id": request.style_id,
        "state": state,
        "reason": adapter["reason"],
        "missing_dependencies": sorted(set(missing)),
        "source_digest": plan["source_digest"],
        "source_manifest_digest": binding["tree_digest"],
        "plan_digest": plan["plan_digest"],
        "runtime_digest": plan["runtime_digest"],
        "recipe_digest": plan["recipe_digest"],
        "compiler_class": adapter["class"],
        "tools": {name: {"sha256": item["digest"]} for name, item in plan["tools"].items()},
        "expected_outputs": plan["expected_outputs"],
        "source_files": len(plan["source_inventory"]),
        "compilation_executed": False,
        "hardware_execution_verified": False,
    }


async def prepare_project_export(scope, project_id: str, expected_version: int):
    """Materialize genuine canonical source export without returning its private body to a planner."""
    project = await workspace._project(project_id, scope, expected_version)
    exported = await workspace.export_project(scope, project_id, expected_version=expected_version)
    await workspace._project(project_id, scope, expected_version)
    return {
        "schema_version": "skeleton.console_build.source_export.v1",
        "project_id": project_id,
        "project_version": expected_version,
        "head_digest": json_digest(project["files"]),
        "filename": exported["filename"],
        "content_digest": exported["content_digest"],
        "bytes": len(exported["content"].encode("utf-8")),
        "media_type": exported["media_type"],
        "download_path": f"/game-learning/projects/{project_id}/export?expected_version={expected_version}",
        "state": "export_prepared",
        "client_download_verified": False,
    }


async def prepare_artifact_export(scope, project_id: str, artifact_id: str):
    record, job = await _completed_artifact(scope, project_id, artifact_id)
    name, data, digest = await download_build_artifact(scope, project_id, artifact_id)
    project = await workspace._project(project_id, scope)
    await _artifact_authority(scope, job)
    return {
        "schema_version": "skeleton.console_build.binary_export.v1",
        "project_id": project_id,
        "project_version": project["version"],
        "head_digest": json_digest(project["files"]),
        "artifact_id": artifact_id,
        "artifact_digest": digest,
        "bytes": len(data),
        "filename": PurePosixPath(name).name,
        "format": record["format"],
        "producer_job_id": job["job_id"],
        "producer_input_digest": json_digest(job["input"]),
        "download_path": f"/game-learning/projects/{project_id}/build-artifacts/{artifact_id}",
        "state": "export_prepared",
        "client_download_verified": False,
    }


def _request(job: dict[str, Any]) -> ConsoleBuildRequest:
    body, binding = job["request"], job["input"]
    files = binding["files"]
    if not isinstance(files, list) or len(files) > 256:
        raise GameLearningError("build_source_limit", "The admitted project has too many build files.", 413)
    contents = {}
    for item in files:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("content"), str)
            or item["path"] in contents
            or _digest(item["content"].encode()) != item["digest"]
        ):
            raise GameLearningError(
                "build_source_corrupt", "The frozen source file identity is invalid.", 503
            )
        contents[item["path"]] = item["content"]
    sources = BuildSourceTree.from_mapping(contents)
    return ConsoleBuildRequest(
        target_id=body["target_id"],
        sources=sources,
        style_id=body.get("style_id", "arcade_score_attack"),
        optimization=body.get("optimization", 1),
        debug=body.get("debug", False),
        timeout_seconds=body.get("timeout_seconds", 60),
        expected_source_digest=sources.digest,
    )


async def _persist_artifacts(scope, job, result):
    artifacts = workspace.database[ARTIFACT_COLLECTION]
    await artifacts.create_index(
        [("tenant_id", ASCENDING), ("owner_id", ASCENDING), ("project_id", ASCENDING), ("job_id", ASCENDING)]
    )
    output = []
    total = 0
    artifact_limit = 64 * 1024 * 1024 if job["kind"] == "desktop" else MAX_ARTIFACT
    output_limit = 64 * 1024 * 1024 if job["kind"] == "desktop" else MAX_OUTPUT
    if len(result.artifacts) > MAX_ARTIFACTS:
        raise GameLearningError("build_artifact_limit", "Compiler output count exceeds its budget.", 413)
    for artifact in result.artifacts:
        total += len(artifact.data)
        if len(artifact.data) > artifact_limit or total > output_limit:
            raise GameLearningError("build_artifact_limit", "Compiler output bytes exceed their budget.", 413)
        await workspace._authority(scope, job["input"])
        artifact_id = str(
            uuid5(
                NAMESPACE_URL, "console-build:" + job["job_id"] + ":" + artifact.name + ":" + artifact.digest
            )
        )
        source_id = "build:" + artifact_id
        admission = await workspace._admit(
            scope, "game-console-build-artifact", artifact_id, len(artifact.data) + 4096
        )
        count = (len(artifact.data) + CHUNK_BYTES - 1) // CHUNK_BYTES
        for index in range(count):
            chunk = artifact.data[index * CHUNK_BYTES : (index + 1) * CHUNK_BYTES]
            row = {
                "_id": source_id + ":" + str(index),
                **scope,
                "project_id": job["project_id"],
                "job_id": job["job_id"],
                "source_id": source_id,
                "kind": "console_build_artifact",
                "index": index,
                "payload": chunk,
                "digest": _digest(chunk),
            }
            await workspace.chunks.update_one({"_id": row["_id"]}, {"$setOnInsert": row}, upsert=True)
            stored = await workspace.chunks.find_one({"_id": row["_id"], **scope})
            if (
                stored is None
                or stored["digest"] != row["digest"]
                or not isinstance(stored.get("payload"), (bytes, bytearray))
                or len(stored["payload"]) != len(chunk)
                or _digest(bytes(stored["payload"])) != row["digest"]
                or stored["job_id"] != job["job_id"]
            ):
                raise GameLearningError("build_artifact_corrupt", "An immutable artifact chunk differs.", 503)
        record = {
            "_id": artifact_id,
            **scope,
            "project_id": job["project_id"],
            "job_id": job["job_id"],
            "artifact_id": artifact_id,
            "source_id": source_id,
            "chunk_count": count,
            **artifact.as_dict(),
            "input": job["input"],
            "created_at": datetime.now(timezone.utc),
            "storage_receipt": admission,
            "state": "prepared",
        }
        await artifacts.update_one({"_id": artifact_id}, {"$setOnInsert": record}, upsert=True)
        stored = await artifacts.find_one({"_id": artifact_id, **scope})
        if stored is None or any(
            stored[key] != record[key] for key in ("digest", "bytes", "chunk_count", "job_id", "input")
        ):
            raise GameLearningError("build_artifact_corrupt", "An immutable artifact record differs.", 503)
        output.append(
            {
                "artifact_id": artifact_id,
                **artifact.as_dict(),
                "download_path": "/game-learning/projects/"
                + job["project_id"]
                + "/build-artifacts/"
                + artifact_id,
            }
        )
    return output


async def handle_console_build(scope, job, cancelled, emit_event):
    """Existing job runner supplies claim, heartbeat and publication fences."""
    await workspace._authority(scope, job["input"])
    request = _request(job)
    loop = asyncio.get_running_loop()

    def event(payload):
        if cancelled.is_set():
            raise GameLearningError("job_cancelled", "The console build was cancelled.", 409)
        future = asyncio.run_coroutine_threadsafe(emit_event({"kind": "console_build", **payload}), loop)
        try:
            future.result(timeout=5)
        except BaseException:
            future.cancel()
            raise

    worker = loop.run_in_executor(
        None, partial(build_runner.run, request, cancel=cancelled.is_set, on_event=event)
    )
    try:
        result = await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancelled.set()
        cleanup = asyncio.ensure_future(asyncio.gather(worker, return_exceptions=True))
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled.set()
        raise
    if cancelled.is_set():
        raise GameLearningError("job_cancelled", "The console build was cancelled.", 409)
    await workspace._authority(scope, job["input"])
    output = result.as_dict()
    output["artifacts"] = (
        await _persist_artifacts(scope, job, result) if result.state == "binary_ready" else []
    )
    return output


def register_console_build_handler() -> None:
    workspace.register_job_handler("build", handle_console_build)


async def _completed_artifact(scope, project_id: str, artifact_id: str, *, dragon_guarded=False):
    """Prepared CAS bytes confer no authority without the completed issuer."""
    record = await workspace.database[ARTIFACT_COLLECTION].find_one(
        {"_id": artifact_id, **scope, "project_id": project_id}
    )
    if record is None:
        raise GameLearningError("build_artifact_not_found", "This build artifact is unavailable.", 404)
    job = await workspace.jobs.find_one(
        {
            "_id": record["job_id"],
            **scope,
            "project_id": project_id,
            "kind": {"$in": ["build", "desktop", "forge_source"]},
            "status": "completed",
        }
    )
    expected_state = "source_ready" if job is not None and job["kind"] == "forge_source" else "binary_ready"
    if job is None or job.get("result", {}).get("state") != expected_state:
        raise GameLearningError(
            "build_artifact_uncommitted", "This build has no completed artifact receipt.", 409
        )
    if record.get("artifact_id") != artifact_id or record.get("source_id") != "build:" + artifact_id:
        raise GameLearningError("build_artifact_corrupt", "Artifact storage identity differs.", 503)
    issued = next(
        (item for item in job["result"].get("artifacts", []) if item.get("artifact_id") == artifact_id), None
    )
    if (
        issued is None
        or any(
            issued.get(key) != record[key]
            for key in ("digest", "bytes", "name", "format", "format_validation")
        )
        or record["input"] != job["input"]
    ):
        raise GameLearningError(
            "build_artifact_corrupt", "Artifact identity differs from its producing job.", 503
        )
    project = await _artifact_authority(scope, job, dragon_guarded=dragon_guarded)
    if job["job_id"] not in project["job_ids"]:
        raise GameLearningError(
            "build_artifact_uncommitted", "Producer job is not linked to this project.", 409
        )
    return record, job


async def _artifact_authority(scope, job, *, dragon_guarded=False):
    if job["kind"] != "forge_source":
        return await workspace._authority(scope, job["input"], dragon_guarded=dragon_guarded)
    # Historical original source ZIPs are owned records, not authority to run
    # old inputs. Acquired/source-derived content is never admitted here.
    project = await workspace._project(job["project_id"], scope)
    binding = job["input"]
    if (
        project["console_id"] != "forge:godot"
        or binding.get("console_id") != "forge:godot"
        or binding.get("sources")
        or binding.get("source_id") is not None
        or binding.get("derived_sources")
        or binding.get("derived_demonstrations")
        or job["job_id"] not in project["job_ids"]
    ):
        raise GameLearningError("forge_artifact_authority", "Original source export authority differs.", 409)
    return project


async def download_build_artifact(scope, project_id: str, artifact_id: str):
    record, job = await _completed_artifact(scope, project_id, artifact_id)
    return await _artifact_bytes(scope, record, job)


async def _artifact_bytes(scope, record, job):
    project_id = job["project_id"]
    artifact_limit = 64 * 1024 * 1024 if job["kind"] == "desktop" else MAX_ARTIFACT
    chunk_limit = 128 if job["kind"] == "desktop" else 32
    if (
        type(record["chunk_count"]) is not int
        or not 1 <= record["chunk_count"] <= chunk_limit
        or type(record["bytes"]) is not int
        or not 1 <= record["bytes"] <= artifact_limit
        or record["chunk_count"] != (record["bytes"] + CHUNK_BYTES - 1) // CHUNK_BYTES
    ):
        raise GameLearningError(
            "build_artifact_corrupt", "Artifact geometry exceeds its declared bounds.", 503
        )
    rows = (
        await workspace.chunks.find(
            {
                **scope,
                "source_id": record["source_id"],
                "project_id": project_id,
                "job_id": job["job_id"],
                "kind": "console_build_artifact",
            }
        )
        .sort("index", ASCENDING)
        .limit(chunk_limit + 1)
        .to_list(length=chunk_limit + 1)
    )
    if len(rows) != record["chunk_count"]:
        raise GameLearningError("build_artifact_corrupt", "Artifact chunk coverage is incomplete.", 503)
    data = bytearray()
    for index, row in enumerate(rows):
        if (
            not isinstance(row.get("payload"), (bytes, bytearray))
            or not 1 <= len(row["payload"]) <= CHUNK_BYTES
        ):
            raise GameLearningError(
                "build_artifact_corrupt", "Artifact chunk payload type/size differs.", 503
            )
        chunk = bytes(row["payload"])
        if (
            row["index"] != index
            or len(chunk) > CHUNK_BYTES
            or len(data) + len(chunk) > record["bytes"]
            or _digest(chunk) != row["digest"]
        ):
            raise GameLearningError(
                "build_artifact_corrupt", "Artifact chunk bytes failed verification.", 503
            )
        data.extend(chunk)
    if len(data) != record["bytes"] or _digest(data) != record["digest"]:
        raise GameLearningError(
            "build_artifact_corrupt", "Artifact bytes failed their producing receipt.", 503
        )
    await _artifact_authority(scope, job)
    return record["name"], bytes(data), record["digest"]


def artifact_source_projection(scope, source):
    manifest = source.get("artifact_manifest")
    if not isinstance(manifest, dict) or not isinstance(source.get("bundle"), dict):
        raise GameLearningError(
            "compiled_source_corrupt", "Compiled manifest and identity must be objects.", 503
        )
    for field in (
        "artifact_id",
        "job_id",
        "project_id",
        "target_id",
        "core_id",
        "artifact_format",
        "format_validation",
        "artifact_name",
    ):
        value = manifest.get(field)
        if not isinstance(value, str) or not 1 <= len(value) <= 512 or any(ord(c) < 32 for c in value):
            raise GameLearningError(
                "compiled_source_corrupt", "Compiled manifest contains an invalid identity.", 503
            )
    for field in ("artifact_digest", "producer_input_digest", "source_manifest_digest", "registry_digest"):
        value = manifest.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise GameLearningError(
                "compiled_source_corrupt", "Compiled manifest contains an invalid SHA-256.", 503
            )
    if (
        not isinstance(manifest, dict)
        or set(manifest)
        != {
            "schema_version",
            "tenant_id",
            "owner_id",
            "project_id",
            "artifact_id",
            "job_id",
            "artifact_digest",
            "artifact_bytes",
            "artifact_name",
            "artifact_format",
            "format_validation",
            "producer_input_digest",
            "producer_version",
            "producer_epoch",
            "source_manifest_digest",
            "target_id",
            "core_id",
            "registry_digest",
        }
        or type(manifest.get("artifact_bytes")) is not int
        or not 1 <= manifest["artifact_bytes"] <= MAX_ARTIFACT
        or type(manifest.get("producer_version")) is not int
        or manifest["producer_version"] < 1
        or type(manifest.get("producer_epoch")) is not int
        or manifest["producer_epoch"] < 0
        or manifest.get("schema_version") != "skeleton.console_build.artifact_source.v1"
        or json_digest(manifest) != source.get("bundle", {}).get("bundle_digest")
        or manifest.get("artifact_digest") != source.get("source_digest")
        or manifest.get("artifact_bytes") != source.get("byte_length")
        or manifest.get("artifact_name") != source.get("filename")
        or manifest.get("project_id") != source.get("project_id")
        or manifest.get("tenant_id") != scope["tenant_id"]
        or manifest.get("owner_id") != scope["owner_id"]
        or source.get("source_id")
        != _key(source["project_id"], "compiled-artifact-source", manifest["artifact_id"])
        or source.get("rights_refs")
        != ["owned-build-receipt://" + manifest.get("job_id", "") + "/" + manifest.get("artifact_id", "")]
    ):
        raise GameLearningError(
            "compiled_source_corrupt", "Compiled source provenance or exact manifest changed.", 503
        )

    class Projection:
        bundle_digest = json_digest(manifest)

        def to_dict(self):
            return {
                "bundle_id": source["source_id"],
                "bundle_digest": self.bundle_digest,
                "source_digest": source["source_digest"],
                "source_kind": "build_artifact",
                "features": {},
                "provenance": {
                    **scope,
                    "rights_refs": source["rights_refs"],
                    "rights_acknowledged": True,
                    "origin": "completed_owned_build",
                },
                "metadata": manifest,
            }

    return Projection()


def _native_target(project):
    from skeleton.jeeves.game_console_catalog import resolve_console

    target = resolve_console(project["console_id"])
    return (
        target.native_target_id
        or target.emulator_target_id
        or target.target_id.removeprefix("dragon_native:").removeprefix("emulator:")
    )


def _core_for_artifact(project, record, job):
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry, emulator_content_extensions

    if job["kind"] != "build":
        raise GameLearningError(
            "artifact_not_console_content", "Desktop packages cannot run as console cartridges.", 409
        )
    target_id = job["request"]["target_id"].removeprefix("dragon_native:")
    if target_id != _native_target(project):
        raise GameLearningError(
            "artifact_target_mismatch", "Compiled target differs from this project's selected hardware.", 409
        )
    try:
        registry = GameEmulatorRegistry.from_environment()
        core = registry.resolve(target_id)
    except (ValueError, OSError) as exc:
        raise GameLearningError(
            "artifact_emulator_unavailable",
            "Install and approve a compatible core before compiled playback.",
            409,
        ) from exc
    if PurePosixPath(record["name"]).suffix.casefold() not in emulator_content_extensions(core.core_id):
        raise GameLearningError(
            "artifact_format_unavailable",
            "The approved core does not admit this compiler output format.",
            409,
        )
    return target_id, registry, core


async def artifact_playback(scope, project_id, artifact_id):
    record, job = await _completed_artifact(scope, project_id, artifact_id)
    project = await workspace._project(project_id, scope)
    base = {
        "schema_version": "skeleton.console_build.playback.v1",
        "artifact_id": artifact_id,
        "project_id": project_id,
        "project_version": project["version"],
        "artifact_digest": record["digest"],
        "artifact_bytes": record["bytes"],
        "target_id": job["request"].get("target_id"),
        "source_kind": "build_artifact",
        "execution_kind": "libretro",
        "hardware_execution_verified": False,
        "execution_verified": False,
        "learning_reward_scope": "Measured visual exploration; game score, health, mastery and success are unavailable",
        "source_id": None,
        "native_instrumentation": {
            "available": False,
            "fields": [],
            "measurement_scope": "Opaque ROM visual exploration; game state semantics are unavailable",
            "reason": "No exact authored native observation binding is available",
        },
    }
    try:
        target, registry, core = _core_for_artifact(project, record, job)
    except GameLearningError as exc:
        return {
            **base,
            "available": False,
            "readiness": {"code": exc.code, "message": exc.message},
            "core": None,
        }
    source_id = _key(
        project_id,
        "compiled-artifact-source",
        artifact_id,
    )
    source = await workspace.sources.find_one({"_id": source_id, **scope})
    if source:
        artifact_source_projection(scope, source)
    if source and (
        source.get("state") != "active"
        or source.get("rights_acknowledged") is not True
        or source["artifact_manifest"]["registry_digest"] != registry.registry_digest
        or source["artifact_manifest"]["core_id"] != core.core_id
    ):
        return {
            **base,
            "available": False,
            "readiness": {
                "code": "compiled_source_withdrawn_or_core_changed",
                "message": "This compiled source was withdrawn or its core approval changed; create a fresh current build.",
            },
            "core": core.public_dict(),
        }
    return {
        **base,
        "native_instrumentation": _instrumentation_projection(_native_observation(record, job, core.core_id)),
        "target_id": target,
        "available": True,
        "readiness": {
            "code": "approved_core_ready",
            "message": "Ready to attempt actual emulator playback; compilation and core availability do not prove game compatibility.",
        },
        "core": core.public_dict(),
        "source_id": source_id if source and source_id in project["source_ids"] else None,
    }


def _native_observation(record, job, core_id):
    """Derive RAM authority from issuer-frozen sources, never HTTP metadata."""
    from skeleton.jeeves.game_console_editor import ConsoleEditorError, ConsoleProject

    files = {}
    for item in job["input"]["files"]:
        if _digest(item["content"].encode()) != item["digest"] or item["path"] in files:
            raise GameLearningError("build_source_corrupt", "Producer source identity differs.", 503)
        files[item["path"]] = item["content"]
    if "game/editor/console.json" not in files:
        return None
    try:
        project = ConsoleProject.from_files(files, target_id=job["request"]["target_id"])
        layout = project.native_observation_layout()
    except ConsoleEditorError as exc:
        if exc.code == "editor_native_observation_unbound":
            return None
        raise GameLearningError(
            "native_layout_invalid", "Producer authoring layout is invalid.", 503
        ) from exc
    if core_id not in layout["core_ids"]:
        return None
    payload = {
        "schema_version": "skeleton.console_build.native_observation.v1",
        "layout": layout,
        "artifact_digest": record["digest"],
        "producer_job_id": job["job_id"],
        "producer_input_digest": json_digest(job["input"]),
    }
    return {**payload, "descriptor_digest": json_digest(payload)}


def _instrumentation_projection(descriptor):
    if descriptor is None:
        return {
            "available": False,
            "fields": [],
            "measurement_scope": "Opaque ROM visual exploration; game state semantics are unavailable",
            "reason": "The exact authored kernel/data binding or compatible core is unavailable",
        }
    layout = descriptor["layout"]
    return {
        "available": True,
        "schema_version": descriptor["schema_version"],
        "layout_digest": layout["layout_digest"],
        "descriptor_digest": descriptor["descriptor_digest"],
        "fields": list(layout["fields"]),
        "core_ids": layout["core_ids"],
        "measurement_scope": layout["measurement_scope"],
        "reward_components": ["visual_change", "movement", "health_delta", "goal_reached"],
        "game_success_available": True,
    }


async def artifact_native_observation(scope, source, *, dragon_guarded=False):
    artifact_source_projection(scope, source)
    record, job = await _completed_artifact(
        scope,
        source["project_id"],
        source["artifact_manifest"]["artifact_id"],
        dragon_guarded=dragon_guarded,
    )
    return _native_observation(record, job, source["artifact_manifest"]["core_id"])


async def assert_artifact_source(scope, source, *, dragon_guarded=False):
    artifact_source_projection(scope, source)
    depth = _ARTIFACT_DEPTH.get()
    if depth >= 8:
        raise GameLearningError(
            "compiled_source_dependency_limit", "Compiled producer dependency depth exceeds eight.", 413
        )
    token = _ARTIFACT_DEPTH.set(depth + 1)
    try:
        pin = source["artifact_manifest"]
        record, job = await _completed_artifact(
            scope, source["project_id"], pin["artifact_id"], dragon_guarded=dragon_guarded
        )
        if (
            job["kind"] != "build"
            or job["job_id"] != pin["job_id"]
            or json_digest(job["input"]) != pin["producer_input_digest"]
            or job["input"]["project_version"] != pin["producer_version"]
            or job["input"].get("input_epoch", 0) != pin["producer_epoch"]
            or job["input"]["tree_digest"] != pin["source_manifest_digest"]
            or any(
                record[key] != pin[field]
                for key, field in (
                    ("digest", "artifact_digest"),
                    ("bytes", "artifact_bytes"),
                    ("name", "artifact_name"),
                    ("format", "artifact_format"),
                    ("format_validation", "format_validation"),
                )
            )
        ):
            raise GameLearningError(
                "compiled_producer_changed", "Exact completed producer identity changed.", 403
            )
        project = await workspace._project(source["project_id"], scope)
        if (
            source["source_id"] not in project["source_ids"]
            or source.get("state") != "active"
            or source.get("rights_acknowledged") is not True
        ):
            raise GameLearningError(
                "compiled_source_withdrawn", "Compiled source is unlinked or withdrawn.", 403
            )
        target, registry, core = _core_for_artifact(project, record, job)
        if (
            target != pin["target_id"]
            or registry.registry_digest != pin["registry_digest"]
            or core.core_id != pin["core_id"]
        ):
            raise GameLearningError(
                "compiled_core_changed", "Compiled source's approved core binding changed.", 409
            )
        return record, job
    finally:
        _ARTIFACT_DEPTH.reset(token)


async def admit_artifact_source(scope, project_id, artifact_id, body):
    record, job = await _completed_artifact(scope, project_id, artifact_id)
    project = await workspace._project(project_id, scope, body["expected_version"])
    target, registry, core = _core_for_artifact(project, record, job)
    source_id = _key(
        project_id,
        "compiled-artifact-source",
        artifact_id,
    )
    operation_id = _key(project_id, "compiled-artifact-admission", body["idempotency_key"])
    request_digest = json_digest({"artifact_id": artifact_id, **body})
    prior = await workspace.revisions.find_one({"_id": operation_id, **scope})
    if prior and (prior.get("request_digest") != request_digest or prior.get("source_id") != source_id):
        raise GameLearningError(
            "idempotency_conflict", "Compiled admission key binds different source or core approval.", 409
        )
    # Read every actual chunk and the complete compiled SHA before granting a source.
    name, data, digest = await download_build_artifact(scope, project_id, artifact_id)
    from skeleton.jeeves.game_console_build import _format

    try:
        actual_format, validation = _format(target, data, PurePosixPath(name).suffix.lstrip(".").lower())
    except ValueError as exc:
        raise GameLearningError(
            "compiled_format_invalid", "Compiled cartridge failed its declared format validation.", 503
        ) from exc
    if (actual_format, validation) != (record["format"], record["format_validation"]):
        raise GameLearningError(
            "compiled_format_changed", "Compiled format differs from its completed receipt.", 503
        )
    manifest = {
        "schema_version": "skeleton.console_build.artifact_source.v1",
        **scope,
        "project_id": project_id,
        "artifact_id": artifact_id,
        "job_id": job["job_id"],
        "artifact_digest": digest,
        "artifact_bytes": len(data),
        "artifact_name": name,
        "artifact_format": actual_format,
        "format_validation": validation,
        "producer_input_digest": json_digest(job["input"]),
        "producer_version": job["input"]["project_version"],
        "producer_epoch": job["input"].get("input_epoch", 0),
        "source_manifest_digest": job["input"]["tree_digest"],
        "target_id": target,
        "core_id": core.core_id,
        "registry_digest": registry.registry_digest,
    }
    source = {
        "_id": source_id,
        **scope,
        "project_id": project_id,
        "source_id": source_id,
        "kind": "build_artifact",
        "filename": name,
        "source_digest": digest,
        "byte_length": len(data),
        "authority_epoch": 0,
        "rights_refs": ["owned-build-receipt://" + job["job_id"] + "/" + artifact_id],
        "rights_acknowledged": True,
        "state": "active",
        "created_at": _now(),
        "artifact_manifest": manifest,
        "metadata": {
            "artifact_id": artifact_id,
            "producer_job_id": job["job_id"],
            "target_id": target,
            "execution_kind": "libretro",
            "core_id": core.core_id,
            "registry_digest": registry.registry_digest,
            "rights_basis": "existing_owned_project_and_live_producer_authority",
            "hardware_execution_verified": False,
        },
        "bundle": {"bundle_digest": json_digest(manifest)},
    }
    existing = await workspace.sources.find_one({"_id": source_id, **scope})
    if existing:
        if existing.get("state") != "active" or existing.get("artifact_manifest") != manifest:
            raise GameLearningError(
                "compiled_source_conflict", "Compiled source was withdrawn or its manifest differs.", 409
            )
        if source_id in project["source_ids"]:
            return {
                "project": await workspace.get_project(scope, project_id),
                "source": _public(existing),
                "playback": await artifact_playback(scope, project_id, artifact_id),
            }
    await workspace._admit(
        scope, "game-console-compiled-source", source_id, len(_json(manifest, 65536)) + 4096
    )
    if prior is None:
        reserved = await workspace.projects.update_one(
            {
                "_id": project_id,
                **scope,
                "version": project["version"],
                "_input_epoch": project.get("_input_epoch", 0),
                "_artifact_admissions": {"$ne": operation_id},
                "_artifact_admissions.127": {"$exists": False},
            },
            {"$addToSet": {"_artifact_admissions": operation_id}},
        )
        if not reserved.modified_count:
            current = await workspace._project(project_id, scope, project["version"])
            if operation_id not in current.get("_artifact_admissions", []):
                raise GameLearningError(
                    "compiled_admission_limit",
                    "Compiled admission limit or current project fence was reached.",
                    409,
                )
        await workspace.revisions.update_one(
            {"_id": operation_id},
            {
                "$setOnInsert": {
                    "_id": operation_id,
                    **scope,
                    "kind": "compiled_artifact_admission",
                    "project_id": project_id,
                    "request_digest": request_digest,
                    "source_id": source_id,
                    "created_at": _now(),
                }
            },
            upsert=True,
        )
        issued = await workspace.revisions.find_one({"_id": operation_id, **scope})
        if issued["request_digest"] != request_digest or issued["source_id"] != source_id:
            raise GameLearningError("idempotency_conflict", "Compiled admission receipt differs.", 409)
    await workspace.sources.update_one({"_id": source_id}, {"$setOnInsert": source}, upsert=True)
    actual = await workspace.sources.find_one({"_id": source_id, **scope})
    if actual is None or actual.get("artifact_manifest") != manifest or actual.get("state") != "active":
        raise GameLearningError("compiled_source_conflict", "Prepared compiled source changed.", 409)

    async def publish():
        await workspace._authority(scope, job["input"], dragon_guarded=True)
        return await workspace.projects.update_one(
            {
                "_id": project_id,
                **scope,
                "version": project["version"],
                "_input_epoch": project.get("_input_epoch", 0),
                "source_ids": {"$ne": source_id},
                "source_ids.63": {"$exists": False},
            },
            {"$addToSet": {"source_ids": source_id}, "$set": {"updated_at": _now()}},
        )

    changed = await workspace._guarded_write(scope, job["input"], publish)
    if not changed.modified_count:
        head = await workspace._project(project_id, scope, project["version"])
        if source_id not in head["source_ids"]:
            raise GameLearningError(
                "compiled_source_conflict",
                "Project changed or source capacity was reached before association.",
                409,
            )
    await assert_artifact_source(scope, actual)
    return {
        "project": await workspace.get_project(scope, project_id),
        "source": _public(actual),
        "playback": await artifact_playback(scope, project_id, artifact_id),
    }


async def preview_artifact(scope, project_id, artifact_id, body):
    """Observe an exact compiler output through the existing approved simulation owner."""
    if body.get("actions") is not None:
        if (
            not isinstance(body["actions"], list)
            or not 1 <= len(body["actions"]) <= 256
            or body.get("steps") is not None
        ):
            raise GameLearningError(
                "artifact_preview_limit", "Choose at most256 explicit inputs or a step count.", 422
            )
    elif type(body.get("steps", 60)) is not int or not 1 <= body.get("steps", 60) <= 256:
        raise GameLearningError("artifact_preview_limit", "Preview contains at most256 actual inputs.", 422)
    admitted = await admit_artifact_source(
        scope,
        project_id,
        artifact_id,
        {
            "expected_version": body["expected_version"],
            "idempotency_key": "preview:" + json_digest(body["idempotency_key"]),
        },
    )
    request = {
        "expected_version": body["expected_version"],
        "idempotency_key": "artifact-preview:" + json_digest(body["idempotency_key"]),
        "source_id": admitted["source"]["source_id"],
        "seed": body.get("seed", 0),
        "episode_steps": 256,
        "reset": True,
        **({"actions": body["actions"]} if body.get("actions") else {"steps": body.get("steps") or 60}),
    }
    project, result = await workspace.simulate(scope, project_id, request)
    record, job = await _completed_artifact(scope, project_id, artifact_id)
    receipt_id = _key(project_id, "simulation", request["idempotency_key"])
    proof = await workspace.receipts.find_one({"_id": receipt_id, **scope, "project_id": project_id})
    if proof is None or proof["request_digest"] != json_digest(request) or proof["result"] != result:
        raise GameLearningError(
            "artifact_preview_uncommitted", "The actual preview receipt is unavailable.", 503
        )
    transitions = result.get("transitions", [])
    return {
        "schema_version": "skeleton.console_build.preview.v1",
        "project_id": project_id,
        "project_version": project["version"],
        "head_digest": json_digest(project["files"]),
        "artifact_id": artifact_id,
        "artifact_digest": record["digest"],
        "producer_job_id": job["job_id"],
        "producer_input_digest": json_digest(job["input"]),
        "toolchain_plan_digest": job["result"].get("receipt", {}).get("plan_digest"),
        "source_manifest_digest": job["input"]["tree_digest"],
        "source_id": admitted["source"]["source_id"],
        "simulation_receipt_id": receipt_id,
        "simulation_request_digest": proof["request_digest"],
        "simulation_result_digest": json_digest(result),
        "session_id": result["session_id"],
        "session_version": result["version"],
        "snapshot_digest": result["snapshot_digest"],
        "steps": result["steps"],
        "transition_count": len(transitions),
        "transitions_digest": json_digest(transitions),
        "frame": result.get("last_frame"),
        "native_instrumentation": admitted["playback"]["native_instrumentation"],
        "state": "preview_observed",
        "scope": "Actual bounded inputs and frame from approved emulator; no learned policy or game mastery claim",
    }


async def start_artifact_play(scope, project_id, artifact_id, body):
    admitted = await admit_artifact_source(
        scope,
        project_id,
        artifact_id,
        {
            "expected_version": body["expected_version"],
            "idempotency_key": "play:" + json_digest(body["idempotency_key"]),
        },
    )
    from routes.game_learning import _plays

    request = {**body, "source_id": admitted["source"]["source_id"]}
    play = await _plays().create(scope, project_id, request)
    return {"play": play, "source": admitted["source"], "playback": admitted["playback"]}


async def start_artifact_training(scope, project_id, artifact_id, body):
    admitted = await admit_artifact_source(
        scope,
        project_id,
        artifact_id,
        {
            "expected_version": body["expected_version"],
            "idempotency_key": "train:" + json_digest(body["idempotency_key"]),
        },
    )
    job = await workspace.start_job(
        scope, project_id, "train", {**body, "source_id": admitted["source"]["source_id"]}
    )
    return {"job": job, "source": admitted["source"], "playback": admitted["playback"]}


async def start_artifact_campaign(scope, project_id, artifact_id, body):
    """Bind a campaign to one exact owned compiler output, through its source authority."""
    admitted = await admit_artifact_source(
        scope,
        project_id,
        artifact_id,
        {
            "expected_version": body["expected_version"],
            "idempotency_key": "campaign:" + json_digest(body["idempotency_key"]),
        },
    )
    from core.game_studio_learning import create

    campaign = await create(scope, project_id, {**body, "source_id": admitted["source"]["source_id"]})
    return {"campaign": campaign, "source": admitted["source"], "playback": admitted["playback"]}


# The original Godot compiler is a projection of this existing project/job and
# artifact owner. It does not create a second project or background-job store.
FORGE_SOURCE_SCHEMA = "skeleton.forge.durable_source.v1"
_FORGE_ROOT = Path(__file__).resolve().parents[2]
_FORGE_SOURCE_ROOTS = (
    "skeleton/context", "skeleton/forge", "skeleton/jeeves", "skeleton/cortex",
    "skeleton/pipelines", "skeleton/kernel", "skeleton/ai/game_builder",
)
_FORGE_FILES = 256
_FORGE_BYTES = 8 * 1024 * 1024


def forge_compiler_digest():
    """Pin the bounded server-owned compiler source inventory, never a client path."""
    paths = sorted({
        path for relative in _FORGE_SOURCE_ROOTS
        for path in (_FORGE_ROOT / relative).rglob("*.py")
    } | {Path(__file__).resolve()})
    if not 1 <= len(paths) <= 16384:
        raise GameLearningError("forge_compiler_inventory", "Compiler source inventory exceeds its budget.", 503)
    total, inventory = 0, {}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(_FORGE_ROOT):
            raise GameLearningError("forge_compiler_inventory", "Compiler source inventory is not local.", 503)
        data = path.read_bytes()
        total += len(data)
        if len(data) > 4 * 1024 * 1024 or total > 64 * 1024 * 1024:
            raise GameLearningError("forge_compiler_inventory", "Compiler source inventory exceeds its budget.", 503)
        inventory[str(path.relative_to(_FORGE_ROOT))] = _digest(data)
    return json_digest({"schema": FORGE_SOURCE_SCHEMA, "files": inventory})


async def _forge_input(scope, project, binding, body):
    if project["console_id"] != "forge:godot":
        raise GameLearningError("forge_project_required", "Choose an owned original Forge project.", 409)
    binding["forge_compiler_digest"] = await asyncio.to_thread(forge_compiler_digest)
    return binding


def _forge_archive(payload):
    """Seal only successful exact original source; archive timestamps are fixed."""
    from skeleton.forge.source_manifest import source_manifest
    from skeleton.forge.projector import _validate

    files, manifest = payload.get("files"), payload.get("source_manifest")
    if payload.get("succeeded") is not True or not isinstance(files, dict) or not 1 <= len(files) <= _FORGE_FILES:
        raise GameLearningError("forge_source_unsealed", "The compiler did not seal a successful source build.")
    total = 0
    for name, content in files.items():
        if not isinstance(name, str) or not isinstance(content, str):
            raise GameLearningError("forge_source_invalid", "Generated source must contain bounded text files.")
        total += len(content.encode("utf-8"))
        if total > _FORGE_BYTES:
            raise GameLearningError("forge_source_limit", "Source exceeds 256 files / 8 MiB.", 413)
        # The projector validates canonical relative paths. Portable ZIP names
        # additionally reject Windows devices and hidden/dot segments.
        if not _portable_source_path(name):
            raise GameLearningError("forge_source_path", "Generated source has an unsafe export path.")
    try:
        _validate(files)
        if not isinstance(manifest, dict) or source_manifest(files) != manifest:
            raise ValueError("manifest differs")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise GameLearningError("forge_manifest_mismatch", "Generated source differs from its sealed manifest.") from exc
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content.encode("utf-8"), compresslevel=9)
    build = {key: value for key, value in payload.items() if key != "files"}
    build["file_names"] = sorted(files)
    build["source_export"] = {
        "status": "ready", "bytes": total, "file_count": len(files),
        "manifest_sha256": manifest["sha256"],
    }
    _json(build, 1536 * 1024)
    return BuildArtifact("source.zip", output.getvalue(), "zip", "exact_source_manifest"), build


def _portable_source_path(name):
    import re
    devices = {"con", "nul", "aux", "prn"} | {
        f"{prefix}{index}" for prefix in ("com", "lpt") for index in range(1, 10)
    }
    return isinstance(name, str) and 0 < len(name) <= 240 and all(
        part and not part.startswith(".") and part.rstrip(" .") == part
        and re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", part) is not None
        and part.split(".")[0].casefold() not in devices
        for part in name.split("/")
    )


def _compile_forge_source(request):
    from skeleton.context.pipeline import GameForgeRun
    options = dict(request)
    vision = options.pop("vision", "")
    blend = options.pop("blend", None)
    fraction = options.pop("t", 0.5)
    for ignored in ("project_root", "overwrite", "include_files"):
        options.pop(ignored, None)
    if blend is not None:
        options["blend"] = tuple(blend) + (fraction,)
    # Fresh local state: no shared live cortex, persisted own.json or provider
    # session is replayed by this source-only job.
    return _forge_archive(GameForgeRun().execute(vision, **options))


def _forge_worker_filter(scope, job):
    return {
        "_id": job["job_id"], **scope, "status": "running",
        "worker_token": job["worker_token"], "lease_until": {"$gt": _now()},
        "cancel_requested": False, "input_changed": False,
    }


async def _verify_forge_prepared(scope, job, prepared):
    if (
        not isinstance(prepared, dict)
        or prepared.get("request_digest") != job["request_digest"]
        or prepared.get("compiler_digest") != job["input"].get("forge_compiler_digest")
        or prepared.get("result_digest") != json_digest(prepared.get("result"))
    ):
        raise GameLearningError("forge_prepared_corrupt", "Prepared source receipt identity differs.", 503)
    result = prepared["result"]
    issued = result.get("artifacts", [])
    if result.get("state") != "source_ready" or len(issued) != 1:
        raise GameLearningError("forge_prepared_corrupt", "Prepared source receipt is incomplete.", 503)
    artifact = issued[0]
    record = await workspace.database[ARTIFACT_COLLECTION].find_one({
        "_id": artifact["artifact_id"], **scope, "project_id": job["project_id"], "job_id": job["job_id"],
    })
    if record is None or record.get("input") != job["input"] or any(
        record.get(key) != artifact.get(key)
        for key in ("artifact_id", "digest", "bytes", "name", "format", "format_validation")
    ):
        raise GameLearningError("forge_prepared_corrupt", "Prepared source artifact differs.", 503)
    if record.get("source_id") != "build:" + artifact["artifact_id"]:
        raise GameLearningError("forge_prepared_corrupt", "Prepared source chunk identity differs.", 503)
    _, data, _ = await _artifact_bytes(scope, record, job)
    from skeleton.forge.source_manifest import source_manifest
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if (
                not 1 <= len(names) <= _FORGE_FILES or len(set(names)) != len(names)
                or any(not _portable_source_path(name) for name in names)
                or sum(item.file_size for item in archive.infolist()) > _FORGE_BYTES
            ):
                raise ValueError("archive geometry differs")
            files = {name: archive.read(name).decode("utf-8") for name in names}
        if source_manifest(files) != result.get("source_manifest"):
            raise ValueError("archive manifest differs")
    except (ValueError, UnicodeError, zipfile.BadZipFile, RuntimeError) as exc:
        raise GameLearningError("forge_prepared_corrupt", "Prepared source ZIP failed manifest verification.", 503) from exc
    return result


async def handle_forge_source(scope, job, cancelled, emit_event):
    """Dispatch once, retain exact preparation, then use the existing terminal CAS."""
    await workspace._authority(scope, job["input"])
    if job.get("request_digest") != json_digest(job["request"]):
        raise GameLearningError("forge_request_changed", "The frozen build request differs.", 503)
    if await asyncio.to_thread(forge_compiler_digest) != job["input"].get("forge_compiler_digest"):
        raise GameLearningError("forge_compiler_changed", "Compiler changed; start a new explicit build request.", 409)
    if job.get("_forge_prepared") is not None:
        result = await _verify_forge_prepared(scope, job, job["_forge_prepared"])
        await workspace._authority(scope, job["input"])
        return result
    if job.get("_forge_dispatched") is not None:
        raise GameLearningError(
            "forge_dispatch_unresolved",
            "This build was dispatched without a recoverable receipt. Start a new explicit request; it will not replay automatically.",
            409,
        )
    dispatch = {
        "request_digest": job["request_digest"],
        "compiler_digest": job["input"]["forge_compiler_digest"],
    }
    changed = await workspace.jobs.update_one(
        {**_forge_worker_filter(scope, job), "_forge_dispatched": {"$exists": False}},
        {"$set": {"_forge_dispatched": dispatch}},
    )
    if not changed.modified_count:
        raise GameLearningError("worker_fenced", "Build lost its dispatch reservation.", 409)
    await emit_event({"kind": "forge_source", "stage": "compiling", "request_digest": job["request_digest"]})
    if cancelled.is_set():
        raise GameLearningError("job_cancelled", "Source build was cancelled.", 409)
    started = time.monotonic()
    worker = asyncio.get_running_loop().run_in_executor(None, _compile_forge_source, job["request"]["run"])
    try:
        artifact, build = await asyncio.wait_for(
            asyncio.shield(worker), timeout=job["request"].get("timeout_seconds", 60)
        )
    except asyncio.CancelledError:
        cancelled.set()
        await _drain_executor(worker)
        raise
    except TimeoutError as exc:
        cancelled.set()
        try:
            await _drain_executor(worker)
        except Exception:
            pass
        raise GameLearningError("forge_build_timeout", "Source build deadline expired after physical compiler cleanup.", 409) from exc
    if cancelled.is_set():
        raise GameLearningError("job_cancelled", "Source build was cancelled after compiler cleanup.", 409)
    await workspace._authority(scope, job["input"])
    result = {
        "schema_version": FORGE_SOURCE_SCHEMA, "state": "source_ready", "build": build,
        "source_manifest": build["source_manifest"],
        "compiler_digest": job["input"]["forge_compiler_digest"],
        "artifacts": await _persist_artifacts(scope, job, SimpleNamespace(artifacts=[artifact])),
        "metrics": {"compile_seconds": round(time.monotonic() - started, 6)},
        "native_execution_verified": False,
    }
    _json(result, 2 * 1024 * 1024)
    prepared = {
        "request_digest": job["request_digest"], "compiler_digest": result["compiler_digest"],
        "result": result, "result_digest": json_digest(result),
    }
    admission = await workspace._admit(
        scope, "game-learning-job", job["job_id"] + ":forge:" + prepared["result_digest"],
        2 * len(_json(prepared)) + 4096,
    )
    await workspace._authority(scope, job["input"])
    try:
        changed = await workspace.jobs.update_one(
            _forge_worker_filter(scope, job),
            {"$set": {"_forge_prepared": prepared, "_forge_prepared_storage_receipt": admission}},
        )
    except PyMongoError:
        # A lost acknowledgement is not permission to run the compiler again.
        confirmed = await workspace.jobs.find_one(_forge_worker_filter(scope, job))
        if confirmed is None or confirmed.get("_forge_prepared") != prepared:
            raise
    else:
        if not changed.modified_count:
            raise GameLearningError("worker_fenced", "Source build lost its preparation fence.", 409)
    return result


def register_forge_source_handler():
    workspace.register_job_handler("forge_source", handle_forge_source, input_hook=_forge_input)


def _forge_receipt(job):
    if job.get("request_digest") != json_digest(job.get("request")):
        raise GameLearningError("forge_request_changed", "Stored build request identity differs.", 503)
    result = workspace._job_public(job)
    result.update(
        request_id=job["request"]["idempotency_key"], request_digest=job["request_digest"],
        brief=job["request"]["run"], project_version=job["input"]["project_version"],
        compiler_digest=job["input"].get("forge_compiler_digest"),
    )
    result["resume_available"] = result["resume_available"] and job.get("_forge_prepared") is not None
    task = getattr(workspace, "_tasks", {}).get(job["job_id"])
    result["local_worker_draining"] = bool(job["status"] == "interrupted" and task is not None and not task.done())
    if result["local_worker_draining"]:
        result["resume_available"] = False
    result["recovery"] = (
        "publication_ready" if job.get("_forge_prepared") is not None
        else "new_request_required" if job.get("_forge_dispatched") is not None else "not_dispatched"
    )
    return result


async def _forge_project(scope, project_id):
    project = await workspace._project(project_id, scope)
    if project["console_id"] != "forge:godot":
        raise GameLearningError("forge_project_not_found", "Original Forge project not found.", 404)
    return project


async def list_forge_projects(scope):
    rows = await workspace.projects.find({**scope, "state": "active", "console_id": "forge:godot"}).sort(
        "updated_at", DESCENDING
    ).limit(64).to_list(length=64)
    return [{key: value for key, value in _public(row).items() if key not in {
        "files", "program_text", "revision_ids", "job_ids", "session_ids", "source_ids",
    }} for row in rows]


async def get_forge_project(scope, project_id):
    history = await list_forge_builds(scope, project_id)
    return {"project": await workspace.get_project(scope, project_id), **history}


async def list_forge_builds(scope, project_id, *, before=None, limit=24):
    """Owned keyset history; reading a page never recovers or schedules jobs."""
    import re

    project = await _forge_project(scope, project_id)
    if type(limit) is not int or not 1 <= limit <= 24:
        raise GameLearningError("forge_history_limit", "Build history pages support 1–24 receipts.")
    query = {
        **scope, "project_id": project_id, "kind": "forge_source", "job_id": {"$in": project["job_ids"]},
    }
    if before is not None:
        if not isinstance(before, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", before) is None:
            raise GameLearningError("forge_history_cursor_invalid", "Build history cursor is invalid.")
        cursor = await workspace.jobs.find_one({
            "_id": before, **scope, "project_id": project_id, "kind": "forge_source",
            "job_id": {"$in": project["job_ids"]},
        })
        if cursor is None:
            raise GameLearningError("forge_history_cursor_not_found", "Build history cursor was not found.", 404)
        if cursor.get("job_id") != before or not isinstance(cursor.get("created_at"), datetime):
            raise GameLearningError("forge_history_cursor_corrupt", "Build history cursor identity differs.", 503)
        query["$or"] = [
            {"created_at": {"$lt": cursor["created_at"]}},
            {"created_at": cursor["created_at"], "job_id": {"$lt": before}},
        ]
    rows = await workspace.jobs.find(query).sort([
        ("created_at", DESCENDING), ("job_id", DESCENDING),
    ]).limit(limit + 1).to_list(length=limit + 1)
    page = rows[:limit]
    return {
        "builds": [_forge_receipt(row) for row in page],
        "next_cursor": page[-1]["job_id"] if len(rows) > limit else None,
    }


async def get_forge_build(scope, project_id, job_id, *, schedule=True):
    await _forge_project(scope, project_id)
    job = await workspace.jobs.find_one({"_id": job_id, **scope, "project_id": project_id, "kind": "forge_source"})
    if job is None:
        raise GameLearningError("forge_build_not_found", "Original source build not found.", 404)
    if schedule:
        await workspace.get_job(scope, job_id)
    else:
        project = await workspace._project(project_id, scope)
        if job_id not in project["job_ids"]:
            raise GameLearningError("forge_build_not_found", "Original source build was not admitted.", 404)
    return _forge_receipt(await workspace.jobs.find_one({"_id": job_id, **scope}))


async def resume_forge_build(scope, project_id, job_id):
    await get_forge_build(scope, project_id, job_id, schedule=False)
    job = await workspace.jobs.find_one({"_id": job_id, **scope})
    if job.get("_forge_prepared") is None:
        raise GameLearningError(
            "forge_dispatch_unresolved", "No exact prepared source receipt is recoverable; start a new explicit request.", 409
        )
    if await asyncio.to_thread(forge_compiler_digest) != job["input"].get("forge_compiler_digest"):
        raise GameLearningError("forge_compiler_changed", "Compiler changed; start a new explicit request.", 409)
    await _verify_forge_prepared(scope, job, job["_forge_prepared"])
    await workspace.resume_job(scope, job_id)
    return await get_forge_build(scope, project_id, job_id)
