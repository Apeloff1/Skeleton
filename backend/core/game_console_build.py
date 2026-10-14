"""Console build projection in the existing governed game-workspace owner."""

from __future__ import annotations

import asyncio
import hashlib
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pymongo import ASCENDING

from core.game_learning import (
    GameLearningError,
    _digest as json_digest,
    _json,
    _key,
    _now,
    _public,
    workspace,
)
from skeleton.jeeves.game_console_build import (
    MAX_ARTIFACT,
    MAX_ARTIFACTS,
    MAX_OUTPUT,
    BuildSourceTree,
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

    worker = asyncio.create_task(
        asyncio.to_thread(build_runner.run, request, cancel=cancelled.is_set, on_event=event)
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
            "kind": {"$in": ["build", "desktop"]},
            "status": "completed",
        }
    )
    if job is None or job.get("result", {}).get("state") != "binary_ready":
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
    project = await workspace._authority(scope, job["input"], dragon_guarded=dragon_guarded)
    if job["job_id"] not in project["job_ids"]:
        raise GameLearningError(
            "build_artifact_uncommitted", "Producer job is not linked to this project.", 409
        )
    return record, job


async def download_build_artifact(scope, project_id: str, artifact_id: str):
    record, job = await _completed_artifact(scope, project_id, artifact_id)
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
    await workspace._authority(scope, job["input"])
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
        "target_id": target,
        "available": True,
        "readiness": {
            "code": "approved_core_ready",
            "message": "Ready to attempt actual emulator playback; compilation and core availability do not prove game compatibility.",
        },
        "core": core.public_dict(),
        "source_id": source_id if source and source_id in project["source_ids"] else None,
    }


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
