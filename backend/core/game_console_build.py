"""Console build projection in the existing governed game-workspace owner."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pymongo import ASCENDING

from core.game_learning import GameLearningError, workspace
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
    if len(result.artifacts) > MAX_ARTIFACTS:
        raise GameLearningError("build_artifact_limit", "Compiler output count exceeds its budget.", 413)
    for artifact in result.artifacts:
        total += len(artifact.data)
        if len(artifact.data) > MAX_ARTIFACT or total > MAX_OUTPUT:
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
        await asyncio.shield(worker)
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


async def download_build_artifact(scope, project_id: str, artifact_id: str):
    """Prepared CAS bytes confer no authority without the completed issuer."""
    record = await workspace.database[ARTIFACT_COLLECTION].find_one(
        {"_id": artifact_id, **scope, "project_id": project_id}
    )
    if record is None:
        raise GameLearningError("build_artifact_not_found", "This build artifact is unavailable.", 404)
    job = await workspace.jobs.find_one(
        {"_id": record["job_id"], **scope, "project_id": project_id, "kind": "build", "status": "completed"}
    )
    if job is None or job.get("result", {}).get("state") != "binary_ready":
        raise GameLearningError(
            "build_artifact_uncommitted", "This build has no completed artifact receipt.", 409
        )
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
    await workspace._authority(scope, job["input"])
    if (
        type(record["chunk_count"]) is not int
        or not 1 <= record["chunk_count"] <= 32
        or type(record["bytes"]) is not int
        or not 1 <= record["bytes"] <= MAX_ARTIFACT
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
        .limit(33)
        .to_list(length=33)
    )
    if len(rows) != record["chunk_count"]:
        raise GameLearningError("build_artifact_corrupt", "Artifact chunk coverage is incomplete.", 503)
    data = bytearray()
    for index, row in enumerate(rows):
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
