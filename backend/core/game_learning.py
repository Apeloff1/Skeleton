"""Owned game-learning workspaces in the existing core Mongo authority.

Runtime adapters and learners remain in Jeeves. This application repository owns
authenticated project revisions, admitted source bytes, measured sessions and
fenced work receipts. In-process tasks are execution handles, never authority.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid4, uuid5

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from core.databases import core_db

log = logging.getLogger(__name__)
MAX_SOURCE = 16 * 1024 * 1024
CHUNK_BYTES = 512 * 1024
MAX_JSON = 8 * 1024 * 1024


class GameLearningError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _time(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _json(value: object, maximum: int = MAX_JSON) -> bytes:
    try:
        data = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    except (TypeError, ValueError) as exc:
        raise GameLearningError("invalid_payload", "Workspace payload is not bounded finite JSON.") from exc
    if len(data) > maximum:
        raise GameLearningError("payload_limit", "Workspace payload exceeds its size limit.", 413)
    return data


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _key(project_id: str, kind: str, key: str) -> str:
    if not isinstance(key, str) or not key.strip() or key != key.strip() or len(key) > 512:
        raise GameLearningError("invalid_idempotency", "A normalized idempotency key is required.")
    return str(uuid5(NAMESPACE_URL, "game-learning:" + project_id + ":" + kind + ":" + key))


async def _drain_executor(future):
    """Observe the real executor outcome even during repeated request cancellation."""
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    return future.result()


async def _close_environment(environment):
    from skeleton.jeeves.game_learning_demonstrations import close_environment

    cleanup = asyncio.get_running_loop().run_in_executor(None, close_environment, environment)
    try:
        await asyncio.shield(cleanup)
    except asyncio.CancelledError:
        await _drain_executor(cleanup)
        raise


async def _probe_environment(factory):
    """A cancelled native admission must still close its eventual environment."""
    worker = asyncio.get_running_loop().run_in_executor(None, factory)
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        try:
            environment = await _drain_executor(worker)
        except Exception:
            # Failed construction owns its own constructor cleanup. The real
            # executor has finished; no environment was handed to this caller.
            pass
        else:
            from skeleton.jeeves.game_learning_demonstrations import close_environment

            cleanup = asyncio.get_running_loop().run_in_executor(None, close_environment, environment)
            await _drain_executor(cleanup)
        raise


def _public(doc: Mapping[str, Any], *, payload: bool = False) -> dict[str, Any]:
    result = {}
    for key, value in doc.items():
        if key.startswith("_") or key in {
            "tenant_id",
            "owner_id",
            "payload",
            "snapshot",
            "input",
            "source_chunks",
            "storage_receipt",
            "checkpoint_storage_receipt",
            "request",
            "request_digest",
            "operation_ids",
            "content_manifest",
        }:
            continue
        if key in {"bundle", "policy_snapshot"} and not payload:
            continue
        result[key] = _time(value).isoformat() if isinstance(value, datetime) else value
    return result


def _files(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) > 128:
        raise GameLearningError("file_limit", "Projects support at most 128 text files.", 413)
    files, seen, size = [], set(), 0
    for item in raw:
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("content"), str)
        ):
            raise GameLearningError("invalid_file", "Each file requires an exact path and text content.")
        path, content = item["path"], item["content"]
        parsed = PurePosixPath(path)
        if (
            not path
            or parsed.is_absolute()
            or str(parsed) != path
            or "\\" in path
            or any(part in {"..", "."} for part in parsed.parts)
            or len(path) > 256
            or "\x00" in path
            or path in seen
        ):
            raise GameLearningError(
                "invalid_file_path", "Project file paths must be unique relative canonical paths."
            )
        count = len(content.encode())
        size += count
        file_limit = 4 * 1024 * 1024 if path == "game/editor/console.json" else 1024 * 1024
        if count > file_limit or size > 7 * 1024 * 1024:
            raise GameLearningError("file_bytes_limit", "Project file bytes exceed the editor limit.", 413)
        seen.add(path)
        files.append(
            {
                "path": path,
                "content": content,
                "language": str(item.get("language") or parsed.suffix.lstrip(".") or "text")[:32],
                "revision": item.get("revision", 1),
                "digest": hashlib.sha256(content.encode()).hexdigest(),
            }
        )
    return files


def _manifest_dialect(files):
    manifest = next((item["content"] for item in files if item["path"] == "engine/manifest.json"), None)
    if manifest is None:
        return None
    try:
        value = json.loads(manifest)
    except (ValueError, RecursionError) as exc:
        raise GameLearningError("invalid_manifest", "Executable manifest is invalid.") from exc
    if not isinstance(value, dict):
        raise GameLearningError("invalid_manifest", "Executable manifest must be an object.")
    dialect = value.get("gameplay_dialect")
    if dialect is not None and (not isinstance(dialect, str) or not 1 <= len(dialect) <= 64):
        raise GameLearningError("invalid_dialect", "Executable gameplay dialect must be bounded.")
    return dialect


class GameLearningWorkspace:
    def __init__(self, database=core_db):
        self.database = database
        self.projects = database["game_learning_projects"]
        self.revisions = database["game_learning_revisions"]
        self.sources = database["game_learning_sources"]
        self.chunks = database["game_learning_source_chunks"]
        self.sessions = database["game_learning_sessions"]
        self.receipts = database["game_learning_simulation_receipts"]
        self.jobs = database["game_learning_jobs"]
        self.episodes = database["game_learning_episodes"]
        self.policies = database["game_learning_policies"]
        self.quotas = database["game_learning_limits"]
        self.workers = database["game_learning_workers"]
        self._tasks: dict[str, asyncio.Task] = {}
        self._studio_continuations: set[asyncio.Task] = set()
        self._cancel: dict[str, threading.Event] = {}
        self._slots = asyncio.Semaphore(2)
        self._indexes_ready = False

    @staticmethod
    def _scope(tenant_id: str, owner_id: str) -> dict[str, str]:
        if not tenant_id or not owner_id or len(tenant_id) > 512 or len(owner_id) > 512:
            raise GameLearningError("authentication_required", "Workspace authentication is required.", 401)
        return {"tenant_id": tenant_id, "owner_id": owner_id}

    async def ensure_indexes(self):
        if self._indexes_ready:
            return
        await self.projects.create_index(
            [("tenant_id", ASCENDING), ("owner_id", ASCENDING), ("updated_at", DESCENDING)]
        )
        for collection in (self.sources, self.sessions, self.jobs, self.policies):
            await collection.create_index(
                [("tenant_id", ASCENDING), ("owner_id", ASCENDING), ("project_id", ASCENDING)]
            )
        await self.jobs.create_index([("status", ASCENDING), ("lease_until", ASCENDING)])
        await self.chunks.create_index([("source_id", ASCENDING), ("index", ASCENDING)], unique=True)
        self._indexes_ready = True

    async def _admit(self, scope: dict[str, str], resource: str, write_id: str, size: int):
        from core.conversations import conversation_authority

        admitter = conversation_authority.storage_admitter
        if admitter is None:
            raise GameLearningError(
                "storage_admission_unavailable", "Governed storage admission is unavailable.", 503
            )
        try:
            receipt = await admitter(
                tenant_id=scope["tenant_id"],
                capability="game-learning-persistence",
                resource_id=resource,
                write_id=write_id,
                storage_bytes=max(1, size),
            )
        except Exception as exc:
            raise GameLearningError(
                "storage_admission_unavailable", "Governed storage admission rejected the write.", 503
            ) from exc
        if (
            not isinstance(receipt, Mapping)
            or type(receipt.get("storage_bytes")) is not int
            or receipt["storage_bytes"] < max(1, size)
        ):
            raise GameLearningError(
                "storage_admission_invalid", "Storage admission did not cover the write.", 503
            )
        return dict(receipt)

    async def _project(self, project_id: str, scope: dict[str, str], version: int | None = None):
        doc = await self.projects.find_one({"_id": project_id, **scope, "state": "active"})
        if doc is None:
            raise GameLearningError("project_not_found", "Game-learning project not found.", 404)
        if version is not None and (type(version) is not int or version != doc["version"]):
            raise GameLearningError("project_conflict", "Project changed; reload its current revision.", 409)
        return doc

    async def catalog(self):
        from skeleton.jeeves.game_console_catalog import console_catalog, resolve_console
        from skeleton.jeeves.game_learning_runtime import GameLearningEnvironment, create_game_environment
        from skeleton.forge.eras import ERA_IDS

        consoles = []
        for raw in console_catalog():
            target = resolve_console(raw["target_id"])
            row = dict(raw)
            row.update(
                console_id=target.target_id,
                engine_kind=raw["runtime_kind"],
                available=bool(
                    raw["reference_supported"]
                    or raw["rom_execution"]
                    or raw.get("capabilities", {}).get("native_source_generation")
                    or raw.get("capabilities", {}).get("native_gameplay_execution")
                ),
                supported_source_kinds=["text", "rom", "dragon", "project"],
                editor_language="text",
            )
            readiness = dict(row.get("readiness", {}))
            readiness["message"] = readiness.get("reason", "Source implementation remains unverified.")
            row["readiness"] = readiness
            if raw.get("capabilities", {}).get("native_gameplay_execution"):
                row["actions"] = list(create_game_environment(target.target_id).spec.actions)
            elif target.reference_supported:
                env = GameLearningEnvironment(target.target_id)
                row["actions"] = list(env.spec.actions)
            elif target.requires_rom:
                row["actions"] = [
                    "idle",
                    "left",
                    "right",
                    "up",
                    "down",
                    "a",
                    "b",
                    "start",
                    "select",
                    "a_right",
                    "a_left",
                ]
            else:
                row["actions"] = []
            consoles.append(row)
        return {
            "consoles": consoles,
            "generation_genres": [{"id": value, "label": value.replace("_", " ")} for value in ERA_IDS],
            "algorithms": [
                {
                    "id": "q_learning",
                    "label": "Measured local Q-learning",
                    "available": True,
                    "readiness": {"message": "Candidate-only local policy; no production promotion."},
                }
            ],
            "storage_authority": "CORE_DB Mongo",
            "automated_verification": False,
        }

    async def create_project(self, scope: dict[str, str], body: dict[str, Any]):
        from skeleton.jeeves.game_console_catalog import resolve_console
        from skeleton.jeeves.game_learning_runtime import GameLearningEnvironment

        await self.ensure_indexes()
        target = resolve_console(body["console_id"])
        project_id = _key(scope["tenant_id"] + ":" + scope["owner_id"], "project", body["idempotency_key"])
        request_digest = _digest({"name": body["name"], "console_id": target.target_id})
        existing = await self.projects.find_one({"_id": project_id, **scope})
        if existing is not None:
            if existing["request_digest"] != request_digest:
                raise GameLearningError(
                    "idempotency_conflict", "Project key was reused with different input.", 409
                )
            return await self.get_project(scope, project_id)
        files = (
            []
            if not target.reference_supported
            else _files(
                [
                    {"path": path, "content": text}
                    for path, text in GameLearningEnvironment(target.target_id).tree.files.items()
                ]
            )
        )
        preferred = next(
            (
                item["path"]
                for item in files
                if "gameplay" in item["path"] and not item["path"].endswith(".json")
            ),
            files[0]["path"] if files else "",
        )
        stamp = _now()
        doc = {
            "_id": project_id,
            **scope,
            "schema_version": "skeleton.game_learning.project.v1",
            "project_id": project_id,
            "name": body["name"],
            "console_id": target.target_id,
            "engine_era": target.era.value,
            "execution_mode": (
                "rom"
                if target.requires_rom
                else (
                    "native_gameplay_python"
                    if target.as_dict().get("capabilities", {}).get("native_gameplay_execution")
                    else "reference" if target.reference_supported else "source_only"
                )
            ),
            "version": 1,
            "state": "active",
            "files": files,
            "entrypoint": preferred,
            "program_text": next((item["content"] for item in files if item["path"] == preferred), ""),
            "source_ids": [],
            "session_ids": [],
            "job_ids": [],
            "revision_ids": [],
            "policy_id": None,
            "request_digest": request_digest,
            "created_at": stamp,
            "updated_at": stamp,
            "_input_epoch": 0,
            "_job_count": 0,
            "_session_count": 0,
        }
        doc["storage_receipt"] = await self._admit(
            scope, "game-learning-project", project_id, len(_json(_public(doc)))
        )
        quota_id = _digest(scope)
        await self.quotas.update_one(
            {"_id": quota_id}, {"$setOnInsert": {**scope, "projects": 0}}, upsert=True
        )
        reserved = await self.quotas.find_one_and_update(
            {"_id": quota_id, "projects": {"$lt": 64}},
            {"$inc": {"projects": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if reserved is None:
            raise GameLearningError("project_limit", "This account has reached its 64-project limit.", 413)
        try:
            await self.projects.insert_one(doc)
        except DuplicateKeyError:
            await self.quotas.update_one({"_id": quota_id}, {"$inc": {"projects": -1}})
            existing = await self.projects.find_one({"_id": project_id, **scope})
            if existing is None or existing["request_digest"] != request_digest:
                raise GameLearningError(
                    "idempotency_conflict", "Project key was reused with different input.", 409
                ) from None
            return await self.get_project(scope, project_id)
        except BaseException:
            await self.quotas.update_one({"_id": quota_id}, {"$inc": {"projects": -1}})
            raise
        return await self.get_project(scope, project_id)

    async def list_projects(self, scope: dict[str, str], limit=50):
        rows = (
            await self.projects.find({**scope, "state": "active"})
            .sort("updated_at", DESCENDING)
            .limit(limit)
            .to_list(length=limit)
        )
        summaries = []
        for row in rows:
            public = _public(row)
            for key in ("files", "program_text", "revision_ids", "job_ids", "session_ids", "source_ids"):
                public.pop(key, None)
            summaries.append(public)
        _json(summaries)
        return summaries

    async def get_project(self, scope: dict[str, str], project_id: str):
        project = await self._project(project_id, scope)
        await self._recover_jobs(scope, project_id)
        await self._schedule_queued(scope, project_id)
        sources = (
            await self.sources.find(
                {**scope, "project_id": project_id, "source_id": {"$in": project["source_ids"]}}
            )
            .limit(64)
            .to_list(length=64)
        )
        sessions = (
            await self.sessions.find(
                {**scope, "project_id": project_id, "session_id": {"$in": project["session_ids"]}}
            )
            .sort("updated_at", DESCENDING)
            .limit(12)
            .to_list(length=12)
        )
        jobs = (
            await self.jobs.find({**scope, "project_id": project_id, "job_id": {"$in": project["job_ids"]}})
            .sort("created_at", DESCENDING)
            .limit(24)
            .to_list(length=24)
        )
        result = _public(project)
        result["environment_actions"] = []
        if (
            any(item["path"] == "game/generated/game.json" for item in project["files"])
            or project["execution_mode"] != "rom"
            and (project["files"] or project["execution_mode"] == "native_gameplay_python")
        ):
            from skeleton.jeeves.game_learning_runtime import create_game_environment

            try:
                from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest

                tree = {item["path"]: item["content"] for item in project["files"]}
                kind = self.authored_environment_kind(tree)
                current_environment = (
                    GameEnvironmentRequest(
                        project["console_id"], kind=kind, tree=self.authored_runtime_tree(tree, kind)
                    ).build()
                    if kind
                    else create_game_environment(
                        project["console_id"],
                        tree=tree or None,
                        gameplay_dialect=_manifest_dialect(project["files"]),
                    )
                )
                try:
                    result["environment_actions"] = list(current_environment.spec.actions)
                    result["execution_descriptor"] = (
                        current_environment.descriptor()
                        if callable(getattr(current_environment, "descriptor", None))
                        else current_environment.spec.as_dict()
                    )
                finally:
                    from skeleton.jeeves.game_learning_demonstrations import close_environment

                    close_environment(current_environment)
            except ValueError:
                result["execution_readiness"] = {
                    "state": "program_rejected",
                    "message": "Editor files need a valid executable manifest and configuration.",
                }
        result.update(
            sources=[
                {
                    **_public(row),
                    **(
                        {
                            "execution_current": row.get("state") == "active"
                            and row["artifact_manifest"]["producer_version"] == project["version"]
                            and row["artifact_manifest"]["producer_epoch"] == project.get("_input_epoch", 0),
                            "status": (
                                "withdrawn"
                                if row.get("state") != "active"
                                else (
                                    "current_compiled"
                                    if row["artifact_manifest"]["producer_version"] == project["version"]
                                    and row["artifact_manifest"]["producer_epoch"]
                                    == project.get("_input_epoch", 0)
                                    else "superseded"
                                )
                            ),
                        }
                        if row["kind"] == "build_artifact"
                        else {}
                    ),
                }
                for row in sources
            ],
            sessions=[
                {
                    **_public(row),
                    "stale": bool(row.get("_input_fenced"))
                    or row["input"]["project_version"] != project["version"]
                    or row["input"].get("input_epoch", 0) != project.get("_input_epoch", 0),
                }
                for row in sessions
            ],
            jobs=[self._job_public(row, include_result=False) for row in jobs],
        )
        _json(result)
        return result

    async def _fence_studio_campaigns(self, scope, project_id, *, version=None, epoch=None, cutoff=None):
        own = {"project_id": project_id}
        if version is not None:
            own["binding.project_version"] = {"$lte": version}
            own["binding.input_epoch"] = {"$lte": epoch}
        query = {
            **scope,
            "source_fenced": {"$ne": True},
            "$or": [
                own,
                {"binding.external_sources.project_id": project_id},
                {"binding.derived_sources.project_id": project_id},
            ],
        }
        if cutoff is not None:
            query["created_at"] = {"$lte": cutoff}
        await self.database["game_learning_campaigns"].update_many(
            query, {"$set": {"source_fenced": True, "desired_status": "cancelled", "updated_at": _now()}}
        )

    async def _fence_jobs(self, scope: dict[str, str], project_id: str, *, editor_claim=None):
        # This first authoritative head fence blocks admission of any new old-input session.
        cutoff, input_filter = {}, {}
        if editor_claim is not None:
            claim_filter = {
                "_id": project_id,
                **scope,
                "state": "active",
                "version": editor_claim["version"],
                "_editor_write_token": editor_claim["token"],
                "_editor_write_until": {"$gt": _now()},
            }
            head = await self.projects.find_one(claim_filter)
            if head is None:
                raise GameLearningError(
                    "editor_write_fenced", "Editor reservation lost its current head.", 409
                )
            await self._fence_studio_campaigns(
                scope,
                project_id,
                version=editor_claim["version"],
                epoch=head.get("_editor_previous_epoch", head.get("_input_epoch", 0)),
                cutoff=head.get("_editor_fenced_at", _now()),
            )
            if head.get("_editor_write_phase") != "fenced":
                previous_epoch = head.get("_input_epoch", 0)
                head = await self.projects.find_one_and_update(
                    {**claim_filter, "_input_epoch": previous_epoch, "_editor_write_phase": "reserved"},
                    {
                        "$inc": {"_input_epoch": 1},
                        "$set": {
                            "_editor_write_phase": "fenced",
                            "_editor_previous_epoch": previous_epoch,
                            "_editor_fenced_at": _now(),
                        },
                    },
                    return_document=ReturnDocument.AFTER,
                )
                if head is None:
                    raise GameLearningError(
                        "editor_write_fenced", "Project changed before its editor fence.", 409
                    )
            cutoff = {"created_at": {"$lte": head["_editor_fenced_at"]}}
            input_filter = {
                "input.project_version": {"$lte": editor_claim["version"]},
                "input.input_epoch": {"$lte": head["_editor_previous_epoch"]},
            }
        else:
            await self._fence_studio_campaigns(scope, project_id)
            await self.projects.update_one(
                {"_id": project_id, **scope, "state": "active"},
                {"$inc": {"_input_epoch": 1}, "$unset": self._editor_claim_fields()},
            )
        # Existing-session replacement is denied before actual source/editor authority changes.
        await self.sessions.update_many(
            {**scope, "project_id": project_id, **input_filter}, {"$set": {"_input_fenced": True}}
        )
        await self.database["game_learning_plays"].update_many(
            {**scope, "project_id": project_id, **input_filter},
            {"$set": {"_input_fenced": True, "cancel_requested": True}},
        )
        await self.database["game_learning_recordings"].update_many(
            {**scope, "project_id": project_id, **input_filter}, {"$set": {"_input_fenced": True}}
        )
        await self.database["game_learning_live_frames"].delete_many(
            {
                **scope,
                "project_id": project_id,
                **(
                    {"expires_at": {"$lte": head["_editor_fenced_at"] + timedelta(seconds=30)}}
                    if editor_claim
                    else {}
                ),
            }
        )
        # Existing derived jobs and active worlds retain all external source
        # dependencies; changing an origin fences dependants before publication.
        dependencies = {
            **scope,
            **cutoff,
            "$or": [
                {"input.external_sources.project_id": project_id},
                {"input.derived_sources.project_id": project_id},
            ],
        }
        await self.jobs.update_many(
            {**dependencies, "status": {"$in": ["queued", "running", "interrupted"]}},
            {"$set": {"cancel_requested": True, "input_changed": True}},
        )
        await self.database["game_learning_plays"].update_many(
            dependencies, {"$set": {"_input_fenced": True, "cancel_requested": True}}
        )
        await self.database["game_learning_recordings"].update_many(
            dependencies, {"$set": {"_input_fenced": True}}
        )
        await self.jobs.update_many(
            {
                **scope,
                "project_id": project_id,
                **input_filter,
                "status": {"$in": ["queued", "running", "interrupted"]},
            },
            {"$set": {"cancel_requested": True, "input_changed": True}},
        )
        for job_id, event in tuple(self._cancel.items()):
            row = await self.jobs.find_one(
                {"_id": job_id, **scope, "project_id": project_id, **input_filter}, {"_id": 1}
            )
            if row is not None:
                event.set()

    @staticmethod
    def _editor_claim_fields():
        return {
            key: ""
            for key in (
                "_editor_write_token",
                "_editor_write_until",
                "_editor_write_operation_id",
                "_editor_write_phase",
                "_editor_previous_epoch",
                "_editor_fenced_at",
            )
        }

    @staticmethod
    def _editor_pending(project):
        return project.get("_editor_write_phase") == "fenced" or (
            project.get("_editor_write_until") is not None and _time(project["_editor_write_until"]) > _now()
        )

    async def _reserve_editor(self, scope, project, operation_id):
        token = str(uuid4())
        phase = (
            "fenced"
            if project.get("_editor_write_operation_id") == operation_id
            and project.get("_editor_write_phase") == "fenced"
            else "reserved"
        )
        reserved = await self.projects.find_one_and_update(
            {
                "_id": project["project_id"],
                **scope,
                "state": "active",
                "version": project["version"],
                "$or": [
                    {"_editor_write_token": {"$exists": False}},
                    {"_editor_write_until": {"$lte": _now()}},
                ],
            },
            {
                "$set": {
                    "_editor_write_token": token,
                    "_editor_write_until": _now() + timedelta(seconds=120),
                    "_editor_write_operation_id": operation_id,
                    "_editor_write_phase": phase,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if reserved is None:
            raise GameLearningError(
                "editor_write_busy",
                "Another editor save owns this revision; retry the exact request when it finishes.",
                409,
            )
        return {"token": token, "version": project["version"]}

    async def save_editor(self, scope: dict[str, str], project_id: str, body: dict[str, Any]):
        operation_id = _key(project_id, "editor", body["idempotency_key"])
        digest = _digest(body)
        prior = await self.revisions.find_one({"_id": operation_id, **scope})
        project = await self._project(project_id, scope)
        if prior is not None:
            if prior["request_digest"] != digest:
                raise GameLearningError(
                    "idempotency_conflict", "Editor key was reused with different input.", 409
                )
            if operation_id in project["revision_ids"]:
                return await self.get_project(scope, project_id)
        await self._project(project_id, scope, body["expected_version"])
        if len(project["revision_ids"]) >= 512:
            raise GameLearningError("revision_limit", "Project editor revision limit is reached.", 413)
        raw = body.get("files")
        if raw is None:
            path = body.get("path") or project["entrypoint"]
            raw = [
                {**item, "content": body["program_text"] if item["path"] == path else item["content"]}
                for item in project["files"]
            ]
            if not any(item["path"] == path for item in raw):
                raw.append({"path": path or "gameplay/program.txt", "content": body["program_text"]})
        files = _files(raw)
        versions = {item["path"]: item for item in project["files"]}
        for item in files:
            original = versions.get(item["path"])
            item["revision"] = (
                1 if original is None else original["revision"] + int(original["digest"] != item["digest"])
            )
        revision = {
            "_id": operation_id,
            **scope,
            "project_id": project_id,
            "request_digest": digest,
            "files": files,
            "version": project["version"] + 1,
            "created_at": _now(),
        }
        await self._admit(scope, "game-learning-revision", operation_id, len(_json({"files": files})))
        await self.revisions.update_one({"_id": operation_id}, {"$setOnInsert": revision}, upsert=True)
        issued = await self.revisions.find_one({"_id": operation_id, **scope})
        if issued is None or issued["request_digest"] != digest or _digest(issued["files"]) != _digest(files):
            raise GameLearningError(
                "idempotency_conflict", "Editor key already binds a different revision.", 409
            )
        entrypoint = (
            body.get("entrypoint")
            or body.get("path")
            or project["entrypoint"]
            or (files[0]["path"] if files else "")
        )
        if files and entrypoint not in {item["path"] for item in files}:
            raise GameLearningError(
                "entrypoint_unavailable", "Editor entrypoint must name an existing project file."
            )
        try:
            claim = await self._reserve_editor(scope, project, operation_id)
            await self._fence_jobs(scope, project_id, editor_claim=claim)
        except GameLearningError:
            current = await self._project(project_id, scope)
            if operation_id in current["revision_ids"]:
                return await self.get_project(scope, project_id)
            raise
        updated = await self.projects.find_one_and_update(
            {
                "_id": project_id,
                **scope,
                "version": body["expected_version"],
                "state": "active",
                "_editor_write_token": claim["token"],
                "_editor_write_until": {"$gt": _now()},
                "_editor_write_phase": "fenced",
            },
            {
                "$set": {
                    "files": files,
                    "execution_mode": (
                        self.authored_environment_kind({item["path"]: item["content"] for item in files})
                        or "original_generated_grid"
                        if any(
                            item["path"]
                            in {
                                "game/generated/game.json",
                                "game/editor/console.json",
                                "game/successor/spec.json",
                            }
                            for item in files
                        )
                        else project["execution_mode"]
                    ),
                    "policy_id": (
                        project.get("policy_id") if _digest(files) == _digest(project["files"]) else None
                    ),
                    "derived_sources": body.get("_derived_sources", project.get("derived_sources", [])),
                    "derived_demonstrations": body.get(
                        "_derived_demonstrations", project.get("derived_demonstrations", [])
                    ),
                    "successor_candidate_id": body.get(
                        "_successor_candidate_id", project.get("successor_candidate_id")
                    ),
                    "entrypoint": entrypoint,
                    "program_text": next(
                        (item["content"] for item in files if item["path"] == entrypoint), ""
                    ),
                    "updated_at": _now(),
                },
                "$inc": {"version": 1},
                "$push": {"revision_ids": operation_id},
                "$unset": self._editor_claim_fields(),
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            current = await self._project(project_id, scope)
            if operation_id in current["revision_ids"]:
                return await self.get_project(scope, project_id)
            raise GameLearningError("project_conflict", "Project changed during editor save.", 409)
        return await self.get_project(scope, project_id)

    async def ingest_source(self, scope: dict[str, str], project_id: str, body: dict[str, Any]):
        from skeleton.jeeves.game_learning_ingestion import GameLearningIngestor, GameSourceProvenance

        source_id = _key(project_id, "source", body["idempotency_key"])
        payload = None
        if body["kind"] != "dragon":
            if body.get("content_base64") is not None:
                try:
                    payload = base64.b64decode(body["content_base64"], validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise GameLearningError(
                        "invalid_source_encoding", "Uploaded source must contain valid base64 bytes."
                    ) from exc
            else:
                payload = (body.get("text") or "").encode()
            if not payload or len(payload) > MAX_SOURCE:
                raise GameLearningError(
                    "source_bytes_limit", "Source bytes must be within the16MiB limit.", 413
                )
        request_identity = {
            key: value for key, value in body.items() if key not in {"content_base64", "text"}
        }
        digest = _digest(
            {
                "schema_version": "skeleton.game_source_request.v2",
                "request": request_identity,
                "payload_digest": hashlib.sha256(payload).hexdigest() if payload is not None else None,
                "payload_bytes": len(payload) if payload is not None else None,
            }
        )
        project = await self._project(project_id, scope)
        prior = await self.sources.find_one({"_id": source_id, **scope, "project_id": project_id})
        if prior is not None:
            compatible = prior["request_digest"] == digest
            if not compatible and prior.get("request_identity_schema") is None:
                try:
                    compatible = prior["request_digest"] == _digest(body)
                except GameLearningError as exc:
                    if exc.code != "payload_limit":
                        raise
            if not compatible:
                raise GameLearningError(
                    "idempotency_conflict", "Source key was reused with different input.", 409
                )
            # Preserve the issued identity of an exact legacy prepared source;
            # compatibility never rewrites its immutable journal or payload.
            digest = prior["request_digest"]
            if prior.get("state") != "active" or prior.get("rights_acknowledged") is not True:
                raise GameLearningError("source_withdrawn", "This source admission was withdrawn.", 410)
            if source_id in project["source_ids"]:
                return await self.get_project(scope, project_id), _public(prior)
        if body["kind"] == "rom":
            bridged = await self._ingest_native_media(scope, project, body, payload, digest, source_id)
            if bridged is not None:
                return bridged
        await self._project(project_id, scope, body["expected_version"])
        if len(project["source_ids"]) >= 64:
            raise GameLearningError("source_limit", "Project source limit reached.", 413)
        rights = tuple(body.get("rights_refs") or ())
        if not rights or body.get("rights_acknowledged") is not True:
            raise GameLearningError(
                "source_consent_required", "Explicit source rights and training consent are required.", 403
            )
        filename = body.get("filename") or "source.txt"
        kind = body["kind"]
        provenance = GameSourceProvenance(
            source_ref="game-learning-source://" + project_id + "/" + source_id,
            tenant_id=scope["tenant_id"],
            owner_id=scope["owner_id"],
            rights_refs=rights,
            license_ref=body.get("license_ref") or "user-attested",
            rights_acknowledged=True,
        )
        if kind == "dragon":
            record = await self._dragon_record(scope, body.get("dragon_ref", ""))
            payload = _json(record, MAX_SOURCE)
            provenance = GameSourceProvenance(
                source_ref=body["dragon_ref"],
                tenant_id=scope["tenant_id"],
                owner_id=scope["owner_id"],
                rights_refs=rights,
                license_ref=body.get("license_ref") or "user-attested",
                rights_acknowledged=True,
                origin="dragon_record",
                record_digest=hashlib.sha256(payload).hexdigest(),
            )
            bundle = await asyncio.to_thread(
                GameLearningIngestor().ingest_dragon_record,
                record,
                provenance=provenance,
                console_id=project["console_id"],
            )
        else:
            bundle = await asyncio.to_thread(
                GameLearningIngestor().ingest_bytes,
                payload,
                filename=filename,
                provenance=provenance,
                source_kind="auto" if kind in {"rom", "project"} else kind,
                console_id=project["console_id"],
            )
        result = bundle.to_dict()
        _json(result, 2 * 1024 * 1024)
        doc = {
            "_id": source_id,
            **scope,
            "project_id": project_id,
            "source_id": source_id,
            "request_digest": digest,
            "request_identity_schema": "skeleton.game_source_request.v2",
            "kind": kind,
            "filename": filename,
            "source_digest": hashlib.sha256(payload).hexdigest(),
            "byte_length": len(payload),
            "rights_refs": list(rights),
            "rights_acknowledged": True,
            "authority_epoch": 0,
            "state": "active",
            "created_at": _now(),
            "bundle": result,
            "metadata": result.get("metadata", {}),
            "chunk_count": (len(payload) + CHUNK_BYTES - 1) // CHUNK_BYTES,
        }
        doc["storage_receipt"] = await self._admit(
            scope, "game-learning-source", source_id, len(payload) + len(_json(result)) + 4096
        )
        await self.sources.update_one({"_id": source_id}, {"$setOnInsert": doc}, upsert=True)
        issued = await self.sources.find_one({"_id": source_id, **scope})
        if (
            issued is None
            or issued["request_digest"] != digest
            or issued["source_digest"] != doc["source_digest"]
            or issued.get("state") != "active"
        ):
            raise GameLearningError(
                "idempotency_conflict", "Source key already binds different or revoked bytes.", 409
            )
        for index, offset in enumerate(range(0, len(payload), CHUNK_BYTES)):
            chunk = payload[offset : offset + CHUNK_BYTES]
            await self.chunks.update_one(
                {"_id": source_id + ":" + str(index)},
                {
                    "$setOnInsert": {
                        **scope,
                        "project_id": project_id,
                        "source_id": source_id,
                        "index": index,
                        "payload": chunk,
                        "digest": hashlib.sha256(chunk).hexdigest(),
                    }
                },
                upsert=True,
            )
        await self._fence_jobs(scope, project_id)
        updated = await self.projects.find_one_and_update(
            {
                "_id": project_id,
                **scope,
                "version": body["expected_version"],
                "source_ids": {"$ne": source_id},
            },
            {
                "$push": {"source_ids": source_id},
                "$inc": {"version": 1},
                "$set": {"updated_at": _now()},
                "$unset": self._editor_claim_fields(),
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise GameLearningError("project_conflict", "Project changed during source admission.", 409)
        return await self.get_project(scope, project_id), _public(doc)

    async def _ingest_native_media(self, scope, project, body, payload, request_digest, source_operation_id):
        from core.game_content_uploads import CHUNK_BYTES as MEDIA_CHUNK_BYTES, content_uploads
        from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry, emulator_content_extensions
        from skeleton.jeeves.game_learning_ingestion import _ROM_EXTENSIONS, _has_rom_signature

        filename = body.get("filename") or "source.bin"
        target_id = project["console_id"].removeprefix("dragon_native:").removeprefix("emulator:")
        known_targets = {
            "nes",
            "famicom",
            "game_boy",
            "game_boy_color",
            "game_boy_pocket",
            "game_boy_light",
            "gb",
            "gbc",
            "snes",
            "super_famicom",
            "genesis",
            "mega_drive",
            "game_boy_advance",
            "gba",
            "nintendo_64",
            "n64",
        }
        if (
            target_id in known_targets
            or PurePosixPath(filename).suffix.casefold() in _ROM_EXTENSIONS
            or _has_rom_signature(payload)
        ):
            return None
        marker = await self.revisions.find_one(
            {"_id": source_operation_id, **scope, "kind": "native_media_source"}
        )
        if marker is not None and marker["request_digest"] != request_digest:
            raise GameLearningError(
                "idempotency_conflict", "Source key already binds different native media.", 409
            )
        if marker is None:
            registry = GameEmulatorRegistry.from_environment()
            try:
                core = registry.resolve(target_id)
            except ValueError:
                # Absence of actual installed approval does not widen intake.
                return None
            if PurePosixPath(filename).suffix.casefold() not in emulator_content_extensions(core.core_id):
                return None
            await self._project(project["project_id"], scope, body["expected_version"])
            if len(project["source_ids"]) >= 64:
                raise GameLearningError("source_limit", "Project source limit reached.", 413)
            admission = await self._admit(
                scope, "game-learning-native-media-admission", source_operation_id, 4096
            )
            await self.revisions.update_one(
                {"_id": source_operation_id},
                {
                    "$setOnInsert": {
                        "_id": source_operation_id,
                        **scope,
                        "project_id": project["project_id"],
                        "kind": "native_media_source",
                        "request_digest": request_digest,
                        "core_id": core.core_id,
                        "registry_digest": registry.registry_digest,
                        "filename": filename,
                        "payload_digest": hashlib.sha256(payload).hexdigest(),
                        "created_at": _now(),
                        "storage_receipt": admission,
                    }
                },
                upsert=True,
            )
            marker = await self.revisions.find_one(
                {"_id": source_operation_id, **scope, "kind": "native_media_source"}
            )
        if marker is None or marker["request_digest"] != request_digest:
            raise GameLearningError(
                "idempotency_conflict", "Native source operation identity conflicts.", 409
            )
        # This is the same canonical protocol used by streamed uploads. Its
        # immutable manifests, account quota, chunk receipts and source-head CAS
        # remain the sole media authority, including restart recovery.
        upload = await content_uploads.create(
            scope,
            project["project_id"],
            {
                "expected_version": body["expected_version"],
                "idempotency_key": "native-source:" + source_operation_id,
                "files": [
                    {"path": filename, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
                ],
                "entrypoint": filename,
                "rights_refs": body.get("rights_refs", []),
                "rights_acknowledged": body.get("rights_acknowledged") is True,
            },
        )
        if upload["status"] != "ready":
            current_registry = GameEmulatorRegistry.from_environment()
            current_core = current_registry.resolve_core(marker["core_id"])
            if (
                current_registry.registry_digest != marker["registry_digest"]
                or target_id not in current_core.target_ids
            ):
                raise GameLearningError(
                    "emulator_approval_changed",
                    "Native media upload approval changed; start a fresh upload under the current operator configuration.",
                    409,
                )
        if upload["status"] == "uploading":
            # On restart exact repeated chunks compare their actual digest and
            # byte range; no retained client buffer or invented parser evidence.
            for index, offset in enumerate(range(0, len(payload), MEDIA_CHUNK_BYTES)):
                chunk = payload[offset : offset + MEDIA_CHUNK_BYTES]
                await content_uploads.put_chunk(
                    scope, upload["upload_id"], 0, index, chunk, hashlib.sha256(chunk).hexdigest()
                )
        result = await content_uploads.complete(scope, upload["upload_id"])
        return result["project"], result["source"]

    @staticmethod
    def _source_bundle(scope, source):
        from skeleton.jeeves.game_learning_ingestion import GameSourceBundle

        if source["kind"] == "build_artifact":
            from core.game_console_build import artifact_source_projection

            return artifact_source_projection(scope, source)

        if source["kind"] == "content_bundle":
            from skeleton.jeeves.game_emulator_catalog import GameContentBundle

            descriptor = GameContentBundle.from_descriptor(source["content_manifest"]["descriptor"])
            if descriptor.bundle_digest != source["source_digest"]:
                raise GameLearningError("content_source_corrupt", "Content manifest identity changed.", 503)

            class Projection:
                bundle_digest = descriptor.bundle_digest

                def to_dict(self):
                    return {
                        "bundle_id": source["bundle_id"],
                        "source_digest": source["source_digest"],
                        "bundle_digest": source["source_digest"],
                        "source_kind": "content_bundle",
                        "features": {},
                        "provenance": {
                            **scope,
                            "rights_refs": source["rights_refs"],
                            "rights_acknowledged": True,
                            "origin": "user_upload",
                        },
                    }

            return Projection()

        bundle = GameSourceBundle(_json(source["bundle"], 2 * 1024 * 1024).decode())
        value = bundle.to_dict()
        provenance = value["provenance"]
        if (
            value["source_digest"] != source["source_digest"]
            or any(provenance.get(key) != scope[key] for key in ("tenant_id", "owner_id"))
            or provenance.get("rights_refs") != source["rights_refs"]
            or provenance.get("rights_acknowledged") is not True
        ):
            raise GameLearningError(
                "source_bundle_corrupt", "Stored source provenance or byte identity differs.", 503
            )
        if (source["kind"] == "dragon") != (provenance.get("origin") == "dragon_record"):
            raise GameLearningError(
                "source_origin_changed", "Stored source origin differs from its admitted type.", 503
            )
        return bundle

    @staticmethod
    def _dragon_owner(scope):
        from routes.dragon_academy import _principal

        return _principal({"email": scope["owner_id"], "tenant_id": scope["tenant_id"], "role": "viewer"})

    async def _dragon_record(self, scope, reference):
        from routes.dragon_academy import _lab
        from skeleton.jeeves.game_learning_ingestion import DragonGameKnowledgeAdapter

        owner = self._dragon_owner(scope)

        def read():
            with _lab() as (lab, _):
                return DragonGameKnowledgeAdapter(lab.db, owner).resolve_record(
                    source_ref=reference, authorized=True
                )

        return await asyncio.to_thread(read)

    async def dragon_sources(self, scope, limit=32):
        from routes.dragon_academy import _lab
        from skeleton.jeeves.game_learning_ingestion import DragonGameKnowledgeAdapter

        owner = self._dragon_owner(scope)

        def read():
            with _lab() as (lab, _):
                return DragonGameKnowledgeAdapter(lab.db, owner).list_sources(authorized=True, limit=limit)

        return await asyncio.to_thread(read)

    async def _dragon_guard_references(self, scope, binding):
        """Collect inherited review dependencies without loading Q tables/files."""
        roles = ("parent_policy", "generation_policy", "review_policy", "review_baseline_policy")
        fields = (
            "project_id",
            "sources",
            "external_sources",
            "derived_sources",
            "demonstrations",
            "inherited_demonstrations",
            "derived_demonstrations",
            *roles,
        )
        projection = {"input." + name: 1 for name in fields}
        pending, policies, teachers, source_ids = [binding], {}, {}, set()
        metadata_bytes = len(_json({name: binding[name] for name in fields if name in binding}))

        def retain_input(record):
            nonlocal metadata_bytes
            value = self._stored_evidence(record["input"])
            metadata_bytes += len(_json(value))
            if metadata_bytes > MAX_JSON:
                raise GameLearningError("review_guard_limit", "Inherited review metadata exceeds8MiB.", 413)
            pending.append(value)

        while pending:
            current = pending.pop()
            # Source-only guards are also used by prepared editor recovery.
            # They need no root project unless a relative policy/teacher pin
            # actually requires that scope.
            project_id = current.get("project_id")
            for reference in (
                current.get("sources", [])
                + current.get("external_sources", [])
                + current.get("derived_sources", [])
            ):
                source_ids.add(reference["source_id"])
            if len(source_ids) > 4096:
                raise GameLearningError(
                    "review_guard_limit", "Inherited review source inventory exceeds4096.", 413
                )
            for role in roles:
                pin = current.get(role)
                if not pin:
                    continue
                identity = (pin.get("project_id", project_id), pin["policy_id"])
                if not isinstance(identity[0], str) or not identity[0]:
                    raise GameLearningError(
                        "review_guard_scope", "An ancestor policy needs exact project scope.", 503
                    )
                if identity in policies:
                    if policies[identity] != pin["snapshot_digest"]:
                        raise GameLearningError(
                            "parent_policy_changed", "Ancestor policy identities conflict.", 403
                        )
                    continue
                if len(policies) >= 256:
                    raise GameLearningError(
                        "review_guard_limit", "Review guard exceeds256policy dependencies.", 413
                    )
                policy = await self.policies.find_one(
                    {"_id": identity[1], **scope, "project_id": identity[0]},
                    {**projection, "snapshot.snapshot_digest": 1},
                )
                if (
                    policy is None
                    or policy.get("snapshot", {}).get("snapshot_digest") != pin["snapshot_digest"]
                ):
                    raise GameLearningError(
                        "parent_policy_changed", "Ancestor policy review identity differs.", 403
                    )
                policies[identity] = pin["snapshot_digest"]
                retain_input(policy)
            for pin in (
                current.get("demonstrations", [])
                + current.get("inherited_demonstrations", [])
                + current.get("derived_demonstrations", [])
            ):
                identity = (pin.get("project_id", project_id), pin["recording_id"])
                if not isinstance(identity[0], str) or not identity[0]:
                    raise GameLearningError(
                        "review_guard_scope", "An ancestor teacher needs exact project scope.", 503
                    )
                if identity in teachers:
                    if teachers[identity] != pin["demonstration_digest"]:
                        raise GameLearningError(
                            "demonstration_identity_changed", "Teacher identities conflict.", 403
                        )
                    continue
                if len(teachers) >= 256:
                    raise GameLearningError(
                        "review_guard_limit", "Review guard exceeds256teacher dependencies.", 413
                    )
                teacher = await self.database["game_learning_recordings"].find_one(
                    {
                        "_id": identity[1],
                        **scope,
                        "project_id": identity[0],
                        "status": "completed",
                        "consent": True,
                    },
                    {**projection, "demonstration.demonstration_digest": 1},
                )
                if (
                    teacher is None
                    or teacher.get("demonstration", {}).get("demonstration_digest")
                    != pin["demonstration_digest"]
                ):
                    raise GameLearningError(
                        "demonstration_consent_withdrawn", "Teacher review authority differs.", 403
                    )
                teachers[identity] = pin["demonstration_digest"]
                retain_input(teacher)

        dragon = set()
        for source_id in sorted(source_ids):
            row = await self.sources.find_one({"_id": source_id, **scope, "kind": "dragon"})
            if row is not None:
                bundle = self._source_bundle(scope, row).to_dict()
                dragon.add((bundle["provenance"]["source_ref"], row["source_digest"]))
        return sorted(dragon)

    async def _guarded_write(self, scope, binding, operation):
        dragon = await self._dragon_guard_references(scope, binding)
        if not dragon:
            return await operation()
        from routes.dragon_academy import _lab
        from skeleton.jeeves.game_learning_ingestion import DragonGameKnowledgeAdapter

        owner, loop = self._dragon_owner(scope), asyncio.get_running_loop()

        def publish():
            with _lab() as (lab, _):
                adapter = DragonGameKnowledgeAdapter(lab.db, owner)
                lab.db.execute("BEGIN IMMEDIATE")
                try:
                    for reference, digest in dragon:
                        record = adapter.resolve_record(source_ref=reference, authorized=True)
                        if hashlib.sha256(_json(record)).hexdigest() != digest:
                            raise GameLearningError(
                                "dragon_authority_changed", "Dragon review or source identity changed.", 403
                            )

                    async def invoke():
                        return await operation()

                    future = asyncio.run_coroutine_threadsafe(invoke(), loop)
                    result = future.result()
                    lab.db.commit()
                    return result
                finally:
                    if lab.db.in_transaction:
                        lab.db.rollback()

        worker = loop.run_in_executor(None, publish)
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            # The review guard and its actual Mongo publication may still be
            # owned by the executor. Do not release that lifetime on wrapper
            # cancellation or detach it on repeated shutdown cancellation.
            await _drain_executor(worker)
            raise

    async def _source_bytes(self, scope: dict[str, str], project: Mapping[str, Any], source_id: str):
        if source_id not in project["source_ids"]:
            raise GameLearningError("source_not_found", "Source is not committed to this project.", 404)
        source = await self.sources.find_one(
            {
                "_id": source_id,
                **scope,
                "project_id": project["project_id"],
                "state": "active",
                "rights_acknowledged": True,
            }
        )
        if source is None:
            raise GameLearningError(
                "source_rights_unavailable", "Source authority is revoked or unavailable.", 403
            )
        self._source_bundle(scope, source)
        if source["kind"] == "build_artifact":
            from core.game_console_build import assert_artifact_source, download_build_artifact

            await assert_artifact_source(scope, source)
            _, payload, digest = await download_build_artifact(
                scope, project["project_id"], source["artifact_manifest"]["artifact_id"]
            )
            if digest != source["source_digest"] or len(payload) != source["byte_length"]:
                raise GameLearningError(
                    "compiled_source_corrupt", "Compiled bytes differ from their source authority.", 503
                )
            return source, payload
        if (
            type(source.get("byte_length")) is not int
            or not 1 <= source["byte_length"] <= MAX_SOURCE
            or type(source.get("chunk_count")) is not int
            or source["chunk_count"] != (source["byte_length"] + CHUNK_BYTES - 1) // CHUNK_BYTES
        ):
            raise GameLearningError(
                "source_manifest_corrupt", "Stored source size or chunk count is invalid.", 503
            )
        chunks = (
            await self.chunks.find({**scope, "source_id": source_id})
            .sort("index", ASCENDING)
            .limit(33)
            .to_list(length=33)
        )
        if len(chunks) != source["chunk_count"] or any(
            type(row.get("index")) is not int
            or row["index"] != index
            or not isinstance(row.get("payload"), bytes)
            or not 1 <= len(row["payload"]) <= CHUNK_BYTES
            or hashlib.sha256(row["payload"]).hexdigest() != row.get("digest")
            for index, row in enumerate(chunks)
        ):
            raise GameLearningError(
                "source_corrupt", "Stored source chunks failed identity verification.", 503
            )
        payload = b"".join(bytes(row["payload"]) for row in chunks)
        if (
            len(payload) != source["byte_length"]
            or hashlib.sha256(payload).hexdigest() != source["source_digest"]
        ):
            raise GameLearningError(
                "source_corrupt", "Stored source bytes failed identity verification.", 503
            )
        return source, payload

    async def _input(self, scope, project, *, source_id=None, episode_steps=256, require_execution=True):
        from skeleton.jeeves.game_console_catalog import resolve_console

        if self._editor_pending(project):
            raise GameLearningError(
                "editor_write_pending",
                "A prepared editor save must finish or recover before starting new work.",
                409,
            )
        target = resolve_console(project["console_id"])
        selected = source_id or project.get("default_source_id")
        sources = (
            await self.sources.find(
                {
                    **scope,
                    "project_id": project["project_id"],
                    "source_id": {"$in": project["source_ids"]},
                    "state": "active",
                }
            )
            .limit(64)
            .to_list(length=64)
        )
        sources = [row for row in sources if row["kind"] != "build_artifact" or row["source_id"] == selected]
        picked = next((row for row in sources if row["source_id"] == selected), None)
        compiled = picked is not None and picked["kind"] == "build_artifact"
        if compiled:
            from core.game_console_build import assert_artifact_source

            await assert_artifact_source(scope, picked)
        generated_grid = any(
            item["path"]
            in {"game/generated/game.json", "game/editor/console.json", "game/successor/spec.json"}
            for item in project["files"]
        )
        if target.requires_rom and not generated_grid and not compiled:
            selected = selected or next(
                (row["source_id"] for row in sources if row["kind"] in {"rom", "content_bundle"}), None
            )
            if selected is None and require_execution:
                raise GameLearningError(
                    "rom_required", "Upload and admit a compatible Game Boy cartridge before execution.", 409
                )
            if selected is not None:
                picked = next((row for row in sources if row["source_id"] == selected), None)
                if picked is not None and picked["kind"] != "content_bundle":
                    await self._source_bytes(scope, project, selected)
        elif selected is not None and selected not in project["source_ids"]:
            raise GameLearningError(
                "source_not_found", "Selected source is not admitted to this project.", 404
            )
        binding = {
            "schema_version": "skeleton.game_learning.input.v1",
            "project_id": project["project_id"],
            "project_version": project["version"],
            "input_epoch": project.get("_input_epoch", 0),
            "console_id": project["console_id"],
            "files": project["files"],
            "source_id": selected,
            "episode_steps": episode_steps,
            "sources": [
                {
                    "source_id": row["source_id"],
                    "source_digest": row["source_digest"],
                    "authority_epoch": row["authority_epoch"],
                    "bundle_digest": row["bundle"]["bundle_digest"],
                }
                for row in sources
            ],
            "tree_digest": _digest(project["files"]),
            "gameplay_dialect": _manifest_dialect(project["files"]),
            "derived_sources": list(project.get("derived_sources", [])),
            "derived_demonstrations": list(project.get("derived_demonstrations", [])),
        }
        if compiled:
            pin = picked["artifact_manifest"]
            binding["execution_selection"] = "compiled_artifact"
            binding["compiled_artifact"] = {
                key: pin[key]
                for key in ("artifact_id", "job_id", "artifact_digest", "producer_input_digest", "target_id")
            }
            binding["emulator_binding"] = {
                "core_id": pin["core_id"],
                "registry_digest": pin["registry_digest"],
            }
            from core.game_console_build import artifact_native_observation

            native = await artifact_native_observation(scope, picked)
            binding["native_observation_digest"] = native["descriptor_digest"] if native else None
        return binding

    async def _authority(self, scope, binding, *, dragon_guarded=False):
        project = await self._project(binding["project_id"], scope, binding["project_version"])
        if project.get("_input_epoch", 0) != binding.get("input_epoch", 0):
            raise GameLearningError(
                "input_fenced", "Project input authority changed; reset or start a new operation.", 409
            )
        if _digest(project["files"]) != binding["tree_digest"]:
            raise GameLearningError(
                "input_changed", "Project files changed; this operation cannot resume.", 409
            )
        if "files" in binding and _digest(binding["files"]) != binding["tree_digest"]:
            raise GameLearningError(
                "frozen_files_corrupt", "Frozen files do not match their admitted identity.", 503
            )
        if "files" not in binding and binding.get("files_omitted") is not True:
            raise GameLearningError("frozen_files_absent", "Input lacks its file binding.", 503)
        for expected in binding["sources"]:
            row = await self.sources.find_one(
                {
                    "_id": expected["source_id"],
                    **scope,
                    "project_id": project["project_id"],
                    "state": "active",
                    "rights_acknowledged": True,
                }
            )
            if (
                row is None
                or row["source_id"] not in project["source_ids"]
                or any(row[key] != expected[key] for key in ("source_digest", "authority_epoch"))
                or row["bundle"]["bundle_digest"] != expected["bundle_digest"]
            ):
                raise GameLearningError(
                    "source_authority_changed", "Source rights or source identity changed.", 403
                )
            bundle = self._source_bundle(scope, row)
            if row["kind"] == "build_artifact":
                from core.game_console_build import assert_artifact_source, _native_observation

                record, producer = await assert_artifact_source(scope, row, dragon_guarded=dragon_guarded)
                if expected["source_id"] == binding.get("source_id"):
                    native = _native_observation(record, producer, row["artifact_manifest"]["core_id"])
                    if binding.get("native_observation_digest") != (
                        native["descriptor_digest"] if native else None
                    ):
                        raise GameLearningError(
                            "native_observation_changed", "Native observation authority changed.", 409
                        )
                    pin = row["artifact_manifest"]
                    expected_pin = {
                        key: pin[key]
                        for key in (
                            "artifact_id",
                            "job_id",
                            "artifact_digest",
                            "producer_input_digest",
                            "target_id",
                        )
                    }
                    if (
                        binding.get("execution_selection") != "compiled_artifact"
                        or binding.get("compiled_artifact") != expected_pin
                    ):
                        raise GameLearningError(
                            "compiled_execution_binding_changed", "Compiled execution identity differs.", 503
                        )
            if row["kind"] == "content_bundle":
                await self._content_authority(scope, project["project_id"], row)
            if row["kind"] == "dragon" and not dragon_guarded:
                current = await self._dragon_record(scope, bundle.to_dict()["provenance"]["source_ref"])
                if hashlib.sha256(_json(current)).hexdigest() != row["source_digest"]:
                    raise GameLearningError(
                        "dragon_authority_changed",
                        "Current Dragon review no longer matches this source.",
                        403,
                    )
        if binding.get("emulator_binding"):
            from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry

            registry = GameEmulatorRegistry.from_environment()
            if registry.registry_digest != binding["emulator_binding"]["registry_digest"]:
                raise GameLearningError(
                    "emulator_registry_changed", "Emulator approval changed; this operation is fenced.", 409
                )
            registry.resolve_core(binding["emulator_binding"]["core_id"])
        if binding.get("demonstrations") or binding.get("inherited_demonstrations"):
            await self._demonstration_authority(scope, binding, dragon_guarded=dragon_guarded)
        for role in ("parent_policy", "generation_policy", "review_policy", "review_baseline_policy"):
            if binding.get(role):
                parent = await self._admitted_policy(
                    scope, project["project_id"], binding[role]["policy_id"], dragon_guarded=dragon_guarded
                )
                if parent["snapshot"]["snapshot_digest"] != binding[role]["snapshot_digest"]:
                    raise GameLearningError("parent_policy_changed", "Admitted policy identity changed.", 409)
        await self._external_authority(scope, binding, dragon_guarded=dragon_guarded)
        await self._derived_demonstration_authority(scope, binding, dragon_guarded=dragon_guarded)
        return project

    async def _derived_demonstration_authority(
        self, scope, binding, *, dragon_guarded=False, allowed_editor_operation_id=None
    ):
        from skeleton.jeeves.game_learning_demonstrations import GameDemonstration

        references = binding.get("derived_demonstrations", [])
        if not isinstance(references, list) or len(references) > 64:
            raise GameLearningError(
                "teacher_lineage_limit", "Derived teacher provenance exceeds capacity.", 413
            )
        for expected in references:
            recorded = await self.database["game_learning_recordings"].find_one(
                {
                    "_id": expected["recording_id"],
                    **scope,
                    "project_id": expected["project_id"],
                    "status": "completed",
                    "consent": True,
                }
            )
            if recorded is None:
                raise GameLearningError(
                    "derived_teacher_withdrawn", "An original teacher withdrew consent.", 403
                )
            demo = GameDemonstration.from_dict(self._stored_evidence(recorded["demonstration"]))
            if (
                demo.digest != expected["demonstration_digest"]
                or recorded["input"]["tree_digest"] != expected["tree_digest"]
            ):
                raise GameLearningError("derived_teacher_changed", "Original teacher evidence changed.", 403)
            sources = [{**ref, "project_id": recorded["project_id"]} for ref in recorded["input"]["sources"]]
            sources += recorded["input"].get("derived_sources", [])
            await self._external_authority(
                scope,
                {"derived_sources": sources},
                dragon_guarded=dragon_guarded,
                allowed_editor_operation_id=allowed_editor_operation_id,
            )

    async def _external_authority(
        self, scope, binding, *, dragon_guarded=False, allowed_editor_operation_id=None
    ):
        for reference in binding.get("external_sources", []) + binding.get("derived_sources", []):
            origin = await self._project(reference["project_id"], scope)
            if self._editor_pending(origin):
                same_operation = bool(
                    allowed_editor_operation_id
                    and origin.get("_editor_write_operation_id") == allowed_editor_operation_id
                )
                prepared = (
                    await self.revisions.find_one(
                        {
                            "_id": allowed_editor_operation_id,
                            **scope,
                            "project_id": origin["project_id"],
                            "version": origin["version"] + 1,
                        }
                    )
                    if same_operation
                    else None
                )
                if prepared is None:
                    raise GameLearningError(
                        "origin_write_pending",
                        "An unrelated or unprepared origin editor save is pending.",
                        409,
                    )
            if reference in binding.get("external_sources", []) and (
                origin["version"] != reference["project_version"]
                or origin.get("_input_epoch", 0) != reference["input_epoch"]
            ):
                raise GameLearningError("origin_revision_changed", "An origin project changed.", 409)
            row = await self.sources.find_one(
                {
                    "_id": reference["source_id"],
                    **scope,
                    "project_id": reference["project_id"],
                    "state": "active",
                    "rights_acknowledged": True,
                }
            )
            if (
                row is None
                or row["source_id"] not in origin["source_ids"]
                or any(row[key] != reference[key] for key in ("source_digest", "authority_epoch"))
            ):
                raise GameLearningError("origin_source_withdrawn", "An origin source was withdrawn.", 403)
            bundle = self._source_bundle(scope, row)
            if bundle.bundle_digest != reference["bundle_digest"]:
                raise GameLearningError("origin_source_changed", "Origin source content changed.", 403)
            if row["kind"] == "build_artifact":
                from core.game_console_build import assert_artifact_source

                await assert_artifact_source(scope, row, dragon_guarded=dragon_guarded)
            if row["kind"] == "content_bundle":
                await self._content_authority(scope, origin["project_id"], row)
            if row["kind"] == "dragon" and not dragon_guarded:
                current = await self._dragon_record(scope, bundle.to_dict()["provenance"]["source_ref"])
                if hashlib.sha256(_json(current)).hexdigest() != row["source_digest"]:
                    raise GameLearningError("dragon_authority_changed", "Origin Dragon review changed.", 403)

    async def _admitted_policy(
        self,
        scope,
        project_id,
        policy_id,
        *,
        dragon_guarded=False,
        allow_environment_changed=False,
        allowed_editor_operation_id=None,
        _ancestor_ids=(),
    ):
        identity = (project_id, policy_id)
        if identity in _ancestor_ids or len(_ancestor_ids) >= 64:
            raise GameLearningError(
                "policy_ancestry_invalid", "Policy ancestry contains a cycle or exceeds64parents.", 413
            )
        ancestry = (*_ancestor_ids, identity)
        saved = await self.policies.find_one({"_id": policy_id, **scope, "project_id": project_id})
        if saved is None:
            raise GameLearningError("policy_not_found", "An owned completed policy is required.", 404)
        saved["snapshot"] = self._stored_evidence(saved["snapshot"])
        issuer = await self.jobs.find_one(
            {"_id": saved["job_id"], **scope, "project_id": project_id, "status": "completed"}
        )
        if (
            issuer is None
            or issuer.get("input") != saved["input"]
            or issuer.get("policy_id") != policy_id
            or issuer.get("result", {}).get("policy_digest") != saved["snapshot"]["snapshot_digest"]
            or _digest({k: v for k, v in saved["snapshot"].items() if k != "snapshot_digest"})
            != saved["snapshot"]["snapshot_digest"]
        ):
            raise GameLearningError("policy_uncommitted", "Policy lacks its completed issuing receipt.", 409)
        project = await self._project(project_id, scope)
        if not allow_environment_changed and _digest(project["files"]) != saved["input"]["tree_digest"]:
            raise GameLearningError(
                "policy_environment_changed", "Policy belongs to a different editor tree.", 409
            )
        for source in saved["input"]["sources"]:
            row = await self.sources.find_one(
                {"_id": source["source_id"], **scope, "state": "active", "rights_acknowledged": True}
            )
            if (
                row is None
                or row["source_id"] not in project["source_ids"]
                or any(row[key] != source[key] for key in ("source_digest", "authority_epoch"))
            ):
                raise GameLearningError(
                    "policy_source_revoked", "Policy source authority is unavailable.", 403
                )
            bundle = self._source_bundle(scope, row)
            if bundle.bundle_digest != source["bundle_digest"]:
                raise GameLearningError("policy_source_changed", "Parent source features changed.", 403)
            if row["kind"] == "build_artifact":
                from core.game_console_build import assert_artifact_source

                await assert_artifact_source(scope, row, dragon_guarded=dragon_guarded)
            if row["kind"] == "content_bundle":
                await self._content_authority(scope, project_id, row)
            if row["kind"] == "dragon" and not dragon_guarded:
                current = await self._dragon_record(scope, bundle.to_dict()["provenance"]["source_ref"])
                if hashlib.sha256(_json(current)).hexdigest() != row["source_digest"]:
                    raise GameLearningError(
                        "policy_review_withdrawn", "Policy Dragon review is no longer current.", 403
                    )
        if saved["input"].get("demonstrations") or saved["input"].get("inherited_demonstrations"):
            await self._demonstration_authority(
                scope,
                saved["input"],
                dragon_guarded=dragon_guarded,
                allowed_editor_operation_id=allowed_editor_operation_id,
            )
        await self._external_authority(
            scope,
            {"derived_sources": saved["input"].get("derived_sources", [])},
            dragon_guarded=dragon_guarded,
            allowed_editor_operation_id=allowed_editor_operation_id,
        )
        await self._derived_demonstration_authority(
            scope,
            saved["input"],
            dragon_guarded=dragon_guarded,
            allowed_editor_operation_id=allowed_editor_operation_id,
        )
        parent_pin = saved["input"].get("parent_policy")
        parent_digest = saved["snapshot"].get("parent_snapshot_digest")
        if parent_pin:
            if parent_digest != parent_pin.get("snapshot_digest") or saved["snapshot"].get(
                "parent_policy_id"
            ) != parent_pin.get("policy_id"):
                raise GameLearningError(
                    "policy_parent_changed",
                    "Full learned policy differs from its admitted parent identity.",
                    503,
                )
            parent = await self._admitted_policy(
                scope,
                project_id,
                parent_pin["policy_id"],
                dragon_guarded=dragon_guarded,
                allow_environment_changed=allow_environment_changed,
                allowed_editor_operation_id=allowed_editor_operation_id,
                _ancestor_ids=ancestry,
            )
            if parent["snapshot"]["snapshot_digest"] != parent_pin["snapshot_digest"]:
                raise GameLearningError(
                    "policy_parent_changed", "Original learned parent snapshot differs.", 403
                )
        elif parent_digest is not None or saved["snapshot"].get("parent_policy_id") is not None:
            raise GameLearningError(
                "policy_parent_missing", "Inherited learned policy lacks its original admitted parent.", 503
            )
        return saved

    async def _policy_evidence(self, scope, project_id, policy_id):
        """Read only a completed current-rights issuer, never an orphan row."""
        from skeleton.jeeves.game_learning import GamePolicyLearner

        saved = await self._admitted_policy(scope, project_id, policy_id, allow_environment_changed=True)
        project = await self._project(project_id, scope)
        issuer = await self.jobs.find_one(
            {"_id": saved["job_id"], **scope, "project_id": project_id, "status": "completed"}
        )
        if (
            issuer is None
            or issuer["job_id"] not in project["job_ids"]
            or issuer.get("kind") != "train"
            or issuer.get("request_digest") != _digest(issuer.get("request"))
            or _digest(issuer.get("input")) != _digest(saved["input"])
        ):
            raise GameLearningError("policy_issuer_invalid", "Policy issuing input is unavailable.", 409)
        try:
            learner = GamePolicyLearner.from_snapshot(saved["snapshot"])
        except ValueError as exc:
            raise GameLearningError(
                "policy_runtime_unavailable", "Policy runtime or full snapshot identity is unavailable.", 409
            ) from exc
        lineage = saved["snapshot"]["source_lineage"]
        if (
            lineage.get("project_id") != project_id
            or lineage.get("input_digest") != _digest(saved["input"])
            or lineage.get("sources") != saved["input"]["sources"]
            or saved["snapshot"]["environment"] != issuer["environment"]
            or issuer.get("learning_config") is not None
            and saved["snapshot"]["configuration"] != issuer["learning_config"]
        ):
            raise GameLearningError(
                "policy_issuer_invalid", "Policy differs from its admitted configuration.", 503
            )
        result = self._stored_evidence(issuer["result"])
        configuration_digest = _digest(saved["snapshot"]["configuration"])
        if (
            result.get("learning_config_digest", configuration_digest) != configuration_digest
            or issuer.get("learning_config") is not None
            and issuer.get("learning_config_digest") != configuration_digest
        ):
            raise GameLearningError(
                "policy_configuration_invalid", "Issued numerical configuration differs.", 503
            )
        evaluation = result.get("evaluation")
        if (
            not isinstance(evaluation, dict)
            or evaluation.get("evaluation_digest")
            != _digest({key: value for key, value in evaluation.items() if key != "evaluation_digest"})
            or evaluation.get("policy_digest") != saved["snapshot"]["snapshot_digest"]
            or evaluation.get("policy_id") != policy_id
            or evaluation.get("environment") != saved["snapshot"]["environment"]
            or evaluation.get("source_lineage") != lineage
            or len(evaluation.get("episodes", [])) != issuer["request"].get("evaluation_seeds", 4)
            or set(evaluation.get("heldout_seeds", [])) & set(saved["snapshot"]["training_seeds"])
        ):
            raise GameLearningError("policy_evaluation_invalid", "Policy paired evaluation differs.", 503)
        acceptance = result.get("acceptance")
        if acceptance is not None and acceptance != self._training_acceptance(evaluation, issuer["request"]):
            raise GameLearningError("policy_acceptance_invalid", "Recorded return gate differs.", 503)
        return saved, issuer, learner

    async def _policy_projection(self, scope, saved, issuer):
        from skeleton.jeeves.game_learning import MAX_LIFETIME_EPISODES, MAX_LIFETIME_UPDATES

        project = await self._project(saved["project_id"], scope)
        snapshot, result = saved["snapshot"], issuer["result"]
        return {
            "policy_id": saved["policy_id"],
            "project_id": saved["project_id"],
            "job_id": saved["job_id"],
            "created_at": _time(saved["created_at"]).isoformat(),
            "available": True,
            "status": "bounded_candidate",
            "policy_digest": snapshot["snapshot_digest"],
            "is_default": project.get("policy_id") == saved["policy_id"],
            "input_digest": _digest(saved["input"]),
            "environment": snapshot["environment"],
            "configuration": snapshot["configuration"],
            "committed_episodes": snapshot["committed_episodes"],
            "committed_updates": snapshot["committed_updates"],
            "inherited_episodes": snapshot.get(
                "inherited_episode_count", len(snapshot.get("inherited_episodes", []))
            ),
            "inherited_updates": snapshot.get("inherited_updates", 0),
            "imitation_observations": snapshot.get("imitation_observations", 0),
            "parent_policy_id": snapshot.get("parent_policy_id"),
            "remaining_lifetime_episodes": max(
                0,
                MAX_LIFETIME_EPISODES
                - snapshot["committed_episodes"]
                - len(snapshot.get("inherited_episodes", [])),
            ),
            "remaining_lifetime_updates": max(
                0, MAX_LIFETIME_UPDATES - snapshot["committed_updates"] - snapshot.get("inherited_updates", 0)
            ),
            "metrics": result["metrics"],
            "acceptance": result.get("acceptance"),
            "selected_source_id": saved["input"].get("source_id"),
            "executable_current_revision": (
                not self._editor_pending(project)
                and _digest(project["files"]) == saved["input"]["tree_digest"]
                and project.get("_input_epoch", 0) == saved["input"].get("input_epoch", 0)
                and project["version"] == saved["input"]["project_version"]
            ),
            "production_promotion_authorized": False,
        }

    async def list_policies(self, scope, project_id, *, limit=16, cursor=None):
        if type(limit) is not int or not 1 <= limit <= 32:
            raise GameLearningError("policy_page_invalid", "Policy page exceeds its bound.")
        await self._project(project_id, scope)
        predicate = {**scope, "project_id": project_id}
        if cursor is not None:
            anchor = await self.policies.find_one({"_id": cursor, **scope, "project_id": project_id})
            if anchor is None:
                raise GameLearningError("policy_cursor_invalid", "Owned policy cursor not found.", 409)
            predicate["$or"] = [
                {"created_at": {"$lt": anchor["created_at"]}},
                {"created_at": anchor["created_at"], "_id": {"$lt": cursor}},
            ]
        rows = (
            await self.policies.find(predicate, {"snapshot": 0})
            .sort([("created_at", -1), ("_id", -1)])
            .limit(limit + 1)
            .max_time_ms(2000)
            .to_list(length=limit + 1)
        )
        output = []
        for row in rows[:limit]:
            try:
                saved, issuer, _ = await self._policy_evidence(scope, project_id, row["policy_id"])
                output.append(await self._policy_projection(scope, saved, issuer))
            except GameLearningError as exc:
                # An owned metadata row is not evidence that its issuer or
                # withdrawn sources are still usable. Never expose its payload.
                output.append(
                    {
                        "policy_id": row["policy_id"],
                        "project_id": project_id,
                        "job_id": row["job_id"],
                        "available": False,
                        "readiness": {"code": exc.code, "message": exc.message},
                        "production_promotion_authorized": False,
                    }
                )
        return {"policies": output, "next_cursor": rows[limit - 1]["_id"] if len(rows) > limit else None}

    async def read_policy(self, scope, project_id, policy_id):
        saved, issuer, _ = await self._policy_evidence(scope, project_id, policy_id)
        result = await self._policy_projection(scope, saved, issuer)
        result["evaluation"] = self._stored_evidence(issuer["result"]["evaluation"])
        await self._admitted_policy(scope, project_id, policy_id, allow_environment_changed=True)
        return {"policy": result}

    async def policy_episodes(self, scope, project_id, policy_id, *, after=-1, limit=16):
        if type(after) is not int or not -1 <= after <= 255 or type(limit) is not int or not 1 <= limit <= 32:
            raise GameLearningError("episode_page_invalid", "Episode page exceeds its bound.")
        saved, _, _ = await self._policy_evidence(scope, project_id, policy_id)
        rows = [item for item in saved["snapshot"]["episodes"] if item["ordinal"] > after]
        page = rows[:limit]
        await self._admitted_policy(scope, project_id, policy_id, allow_environment_changed=True)
        return {
            "policy_id": policy_id,
            "policy_digest": saved["snapshot"]["snapshot_digest"],
            "episodes": page,
            "next_after": page[-1]["ordinal"] if len(rows) > limit else None,
            "scope": "current_job_committed_episodes",
        }

    async def export_policy(self, scope, project_id, policy_id):
        saved, issuer, _ = await self._policy_evidence(scope, project_id, policy_id)
        payload = {
            "schema_version": "skeleton.game.policy_export.v1",
            "policy": await self._policy_projection(scope, saved, issuer),
            "snapshot": saved["snapshot"],
            "evaluation": self._stored_evidence(issuer["result"]["evaluation"]),
            "source_authority": {
                "project_id": project_id,
                "tree_digest": saved["input"]["tree_digest"],
                "input_digest": _digest(saved["input"]),
                "sources": saved["input"]["sources"],
                "parent_policy": saved["input"].get("parent_policy"),
                "demonstrations": saved["input"].get("demonstrations", []),
                "inherited_demonstrations": saved["input"].get("inherited_demonstrations", []),
            },
            "authority_scope": "same-store issued evidence; exported JSON grants no execution/import authority",
            "production_promotion_authorized": False,
        }
        encoded = _json(payload)
        await self._admitted_policy(scope, project_id, policy_id, allow_environment_changed=True)
        return {
            "project_id": project_id,
            "policy_id": policy_id,
            "policy_digest": saved["snapshot"]["snapshot_digest"],
            "filename": "game-policy-" + policy_id + ".json",
            "media_type": "application/json",
            "content": encoded.decode(),
            "content_digest": hashlib.sha256(encoded).hexdigest(),
        }

    async def export_policy_episode(self, scope, project_id, policy_id, episode_id):
        saved, issuer, learner = await self._policy_evidence(scope, project_id, policy_id)
        summary = next(
            (row for row in saved["snapshot"]["episodes"] if row["episode_id"] == episode_id), None
        )
        if summary is None:
            raise GameLearningError("episode_not_found", "Committed policy episode not found.", 404)
        record = await self.episodes.find_one(
            {
                "_id": issuer["job_id"] + ":" + episode_id,
                **scope,
                "project_id": project_id,
                "job_id": issuer["job_id"],
                "trace.trace_digest": summary["trace_digest"],
            }
        )
        if record is None:
            # The latest authoritative checkpoint retains the complete trace
            # across an interrupted projection. Older committed rows are never
            # replaced using an unacknowledged rollout or caller payload.
            await self._project_committed_episode(scope, issuer)
            record = await self.episodes.find_one(
                {
                    "_id": issuer["job_id"] + ":" + episode_id,
                    **scope,
                    "project_id": project_id,
                    "job_id": issuer["job_id"],
                    "trace.trace_digest": summary["trace_digest"],
                }
            )
        if record is None:
            raise GameLearningError(
                "episode_evidence_unavailable", "Committed episode trace is unavailable.", 503
            )
        trace = self._stored_evidence(record["trace"])
        try:
            learner.validate_trace(trace)
        except ValueError as exc:
            raise GameLearningError(
                "episode_evidence_corrupt", "Committed episode validation failed.", 503
            ) from exc
        if any(
            trace[key] != summary[key] for key in ("episode_id", "trace_digest", "seed", "steps", "return")
        ):
            raise GameLearningError(
                "episode_evidence_corrupt", "Episode differs from its committed policy ledger.", 503
            )
        encoded = _json(
            {
                "schema_version": "skeleton.game.policy_episode_export.v1",
                "policy_id": policy_id,
                "job_id": issuer["job_id"],
                "policy_digest": saved["snapshot"]["snapshot_digest"],
                "summary": summary,
                "trace": trace,
                "import_authority": False,
                "production_promotion_authorized": False,
            },
            2 * 1024 * 1024,
        )
        await self._admitted_policy(scope, project_id, policy_id, allow_environment_changed=True)
        return {
            "project_id": project_id,
            "policy_id": policy_id,
            "episode_id": episode_id,
            "filename": "game-episode-" + hashlib.sha256(episode_id.encode()).hexdigest()[:20] + ".json",
            "media_type": "application/json",
            "content": encoded.decode(),
            "content_digest": hashlib.sha256(encoded).hexdigest(),
        }

    async def _factory(self, scope, binding):
        from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest

        request = GameEnvironmentRequest.from_dict(await self.environment_request(scope, binding))
        return request.build

    async def _simulation_receipt(self, scope, project_id, operation_id, request_digest, receipt):
        """Publish only an issued prepared result; never replay native execution."""
        if receipt.get("request_digest") != request_digest or receipt.get("project_id") != project_id:
            raise GameLearningError(
                "idempotency_conflict", "Simulation key was reused with different input.", 409
            )
        prepared = receipt.get("prepared_session")
        result = receipt.get("result")
        if prepared is not None:
            if (
                prepared.get("project_id") != project_id
                or any(prepared.get(key) != value for key, value in scope.items())
                or prepared.get("_id") != receipt.get("session_id")
                or prepared.get("session_id") != receipt.get("session_id")
                or operation_id not in prepared.get("operation_ids", [])
                or receipt.get("input_digest") != _digest(prepared.get("input"))
                or prepared.get("snapshot_digest") != _digest(prepared.get("snapshot"))
                or not isinstance(result, dict)
                or result.get("snapshot_digest") != prepared.get("snapshot_digest")
                or receipt.get("prepared_digest")
                != _digest(
                    {
                        "session": _public(prepared),
                        "snapshot": prepared["snapshot"],
                        "input": prepared["input"],
                        "result": result,
                    }
                )
            ):
                raise GameLearningError(
                    "session_receipt_corrupt", "Prepared simulation identity is invalid.", 503
                )
            expected = receipt.get("expected_session_version")
            if prepared.get("version") != (1 if expected is None else expected + 1):
                raise GameLearningError(
                    "session_receipt_corrupt", "Prepared simulation revision is invalid.", 503
                )
            await self._authority(scope, prepared["input"])

            async def publish_prepared():
                await self._authority(scope, prepared["input"], dragon_guarded=True)
                current = await self.sessions.find_one(
                    {"_id": receipt["session_id"], **scope, "project_id": project_id}
                )
                if current is None:
                    if expected is not None:
                        raise GameLearningError("session_conflict", "Simulation session is missing.", 409)
                    try:
                        await self.sessions.insert_one(prepared)
                    except DuplicateKeyError:
                        current = await self.sessions.find_one(
                            {"_id": receipt["session_id"], **scope, "project_id": project_id}
                        )
                        if current is None or operation_id not in current.get("operation_ids", []):
                            raise GameLearningError(
                                "session_conflict", "Simulation session changed concurrently.", 409
                            ) from None
                elif operation_id not in current.get("operation_ids", []):
                    if expected is None:
                        raise GameLearningError(
                            "session_conflict", "Simulation session changed concurrently.", 409
                        )
                    changed = await self.sessions.replace_one(
                        {
                            "_id": receipt["session_id"],
                            **scope,
                            "project_id": project_id,
                            "version": expected,
                            "_input_fenced": False,
                        },
                        prepared,
                    )
                    if not changed.modified_count:
                        raise GameLearningError(
                            "session_conflict", "Simulation session changed concurrently.", 409
                        )

            await self._guarded_write(scope, prepared["input"], publish_prepared)
        current = await self.sessions.find_one(
            {"_id": receipt["session_id"], **scope, "project_id": project_id, "operation_ids": operation_id}
        )
        if current is None or result is None:
            code = (
                "simulation_dispatch_failed"
                if receipt.get("state") == "failed"
                else "simulation_dispatch_pending"
            )
            raise GameLearningError(
                code,
                "The reserved simulation has no committed result; this key cannot dispatch again.",
                409,
            )
        await self._authority(scope, current["input"])
        if current.get("_input_fenced"):
            raise GameLearningError(
                "session_fenced", "This session receipt belongs to withdrawn input authority.", 409
            )
        head = await self._project(project_id, scope)
        if current["session_id"] not in head["session_ids"]:
            if (
                current["version"] != 1
                or current["snapshot_digest"] != result["snapshot_digest"]
                or _digest(current["snapshot"]) != current["snapshot_digest"]
            ):
                raise GameLearningError(
                    "session_receipt_corrupt", "Prepared session identity is invalid.", 503
                )

            async def repair_session():
                await self._authority(scope, current["input"], dragon_guarded=True)
                changed = await self.projects.update_one(
                    {
                        "_id": project_id,
                        **scope,
                        "version": current["input"]["project_version"],
                        "_input_epoch": current["input"].get("input_epoch", 0),
                        "_session_count": {"$lt": 128},
                        "session_ids": {"$ne": current["session_id"]},
                    },
                    {"$push": {"session_ids": current["session_id"]}, "$inc": {"_session_count": 1}},
                )
                if not changed.modified_count:
                    live = await self._project(project_id, scope)
                    if current["session_id"] not in live["session_ids"]:
                        raise GameLearningError(
                            "session_recovery_conflict", "Project changed before session recovery.", 409
                        )

            await self._guarded_write(scope, current["input"], repair_session)
        await self._authority(scope, current["input"])
        await self.receipts.update_one(
            {"_id": operation_id, **scope, "request_digest": request_digest},
            {"$set": {"state": "committed", "committed_at": _now()}},
        )
        return await self.get_project(scope, project_id), result

    async def simulate(self, scope, project_id, body):
        operation_id = _key(project_id, "simulation", body["idempotency_key"])
        request_digest = _digest(body)
        receipt = await self.receipts.find_one({"_id": operation_id, **scope})
        if receipt is not None:
            return await self._simulation_receipt(scope, project_id, operation_id, request_digest, receipt)
        project = await self._project(project_id, scope, body["expected_version"])
        session_id = body.get("session_id") or _key(project_id, "session", body["idempotency_key"])
        existing = await self.sessions.find_one({"_id": session_id, **scope, "project_id": project_id})
        if existing is not None and session_id not in project["session_ids"]:
            raise GameLearningError("session_uncommitted", "Session was not committed to this project.", 409)
        reset = bool(body.get("reset", existing is None))
        if existing is None and not reset:
            raise GameLearningError("session_missing", "Reset is required for a new session.", 409)
        if existing is not None and body.get("expected_session_version") != existing["version"]:
            raise GameLearningError(
                "session_conflict", "Reload the current session revision before stepping.", 409
            )
        if (
            existing is not None
            and reset
            and (
                existing.get("_input_fenced")
                or existing["input"]["project_version"] != project["version"]
                or existing["input"].get("input_epoch", 0) != project.get("_input_epoch", 0)
            )
        ):
            session_id = _key(project_id, "session", body["idempotency_key"])
            existing = None
        if existing is not None and len(existing.get("operation_ids", [])) >= 4096:
            raise GameLearningError(
                "session_operation_limit", "Start a new session after4096 operations.", 413
            )
        if existing is None and project["_session_count"] >= 128:
            raise GameLearningError("session_limit", "Project session limit is reached.", 413)
        binding = (
            await self._input(
                scope,
                project,
                source_id=body.get("source_id"),
                episode_steps=body.get("episode_steps") or body.get("max_steps") or 512,
            )
            if reset
            else existing["input"]
        )
        await self._authority(scope, binding)
        factory = await self._factory(scope, binding)
        actions = body.get("actions") or ([body["action"]] if body.get("action") else [])
        seed = body.get("seed", 0)
        token = str(uuid4())
        reservation = {
            "_id": operation_id,
            **scope,
            "project_id": project_id,
            "session_id": session_id,
            "request_digest": request_digest,
            "state": "dispatch_reserved",
            "dispatch_token": token,
            "input_digest": _digest(binding),
            "created_at": _now(),
            "expected_session_version": None if existing is None else existing["version"],
        }
        reservation["storage_receipt"] = await self._admit(
            scope,
            "game-learning-simulation-dispatch",
            operation_id + ":dispatch",
            len(_json({key: value for key, value in reservation.items() if key != "created_at"})),
        )
        try:
            await self.receipts.insert_one(reservation)
        except DuplicateKeyError:
            prior = await self.receipts.find_one({"_id": operation_id, **scope})
            if prior is None:
                raise GameLearningError(
                    "simulation_conflict", "Simulation reservation conflicts.", 409
                ) from None
            return await self._simulation_receipt(scope, project_id, operation_id, request_digest, prior)
        cancelled = threading.Event()
        deadline = time.monotonic() + 120

        def check():
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise GameLearningError("simulation_stopped", "Simulation stopped before publication.", 409)

        def execute():
            from skeleton.jeeves.game_learning_demonstrations import close_environment, current_observation

            check()
            env = factory()
            try:
                check()
                initial = (
                    env.reset(seed) if reset else env.restore(self._stored_evidence(existing["snapshot"]))
                )
                observation = current_observation(env, initial)
                transitions = []
                reward = 0.0 if reset else existing["total_reward"]
                steps = 0 if reset else existing["steps"]
                terminated = False if reset else existing["terminated"]
                truncated = False if reset else existing["truncated"]
                selected_actions = actions or ([env.spec.actions[0]] * body.get("steps", 0))
                if selected_actions and (terminated or truncated):
                    raise GameLearningError(
                        "session_terminal", "Reset a terminal session before stepping.", 409
                    )
                for action in selected_actions:
                    check()
                    if steps >= 4096:
                        raise GameLearningError("step_limit", "Session step budget is exhausted.", 413)
                    outcome = env.step(action)
                    check()
                    transitions.append(outcome.as_dict())
                    observation = dict(outcome.observation)
                    reward += outcome.reward
                    steps += 1
                    terminated, truncated = outcome.terminated, outcome.truncated
                    if terminated or truncated:
                        break
                snapshot, frame = env.snapshot(), env.preview()
                check()
                return (
                    dict(observation),
                    snapshot,
                    frame,
                    transitions,
                    reward,
                    steps,
                    terminated,
                    truncated,
                    env.spec.as_dict(),
                )
            finally:
                close_environment(env)

        worker = None
        try:
            await self._authority(scope, binding)
            worker = asyncio.get_running_loop().run_in_executor(None, execute)
            try:
                observed = await asyncio.wait_for(asyncio.shield(worker), timeout=120)
            except (asyncio.CancelledError, asyncio.TimeoutError) as exc:
                cancelled.set()
                # Repeated request/shutdown cancellation cannot detach physical native work.
                while not worker.done():
                    try:
                        await asyncio.shield(worker)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if worker.done() and not worker.cancelled():
                    worker.exception()
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise GameLearningError(
                    "simulation_deadline", "Simulation deadline elapsed; physical cleanup completed.", 409
                ) from exc
            observation, snapshot, frame, transitions, reward, steps, terminated, truncated, descriptor = (
                observed
            )
            await self._authority(scope, binding)
            # Mongo stores datetimes at millisecond precision. Freeze that exact
            # representation before issuing the prepared payload digest.
            stamp = _now()
            stamp = stamp.replace(microsecond=stamp.microsecond // 1000 * 1000)
            doc = {
                "_id": session_id,
                **scope,
                "project_id": project_id,
                "session_id": session_id,
                "input_project_version": binding["project_version"],
                "_input_fenced": False,
                "version": 1 if existing is None else existing["version"] + 1,
                "input": binding,
                "snapshot": snapshot,
                "snapshot_digest": _digest(snapshot),
                "last_observation": observation,
                "last_frame": frame,
                "actions": descriptor["actions"],
                "environment": descriptor,
                "steps": steps,
                "total_reward": reward,
                "terminated": terminated,
                "truncated": truncated,
                "updated_at": stamp,
                "operation_ids": (existing.get("operation_ids", []) if existing else []) + [operation_id],
            }
            result = {**_public(doc), "transitions": transitions}
            encoded = _json(
                {"session": _public(doc), "snapshot": snapshot, "input": binding, "result": result},
                MAX_JSON - 65536,
            )
            admission = await self._admit(scope, "game-learning-session", operation_id, len(encoded))
            changed = await self.receipts.update_one(
                {"_id": operation_id, **scope, "dispatch_token": token, "state": "dispatch_reserved"},
                {
                    "$set": {
                        "state": "prepared",
                        "prepared_session": doc,
                        "result": result,
                        "prepared_digest": hashlib.sha256(encoded).hexdigest(),
                        "storage_receipt": admission,
                        "prepared_at": _now(),
                    }
                },
            )
            if not changed.modified_count:
                raise GameLearningError("simulation_fenced", "Simulation dispatch authority changed.", 409)
        except BaseException:
            # A failed reservation deliberately cannot dispatch again under this key.
            # Prepared results remain recoverable when only publication is interrupted.
            await self.receipts.update_one(
                {"_id": operation_id, **scope, "dispatch_token": token, "state": "dispatch_reserved"},
                {"$set": {"state": "failed", "finished_at": _now()}},
            )
            raise
        receipt = await self.receipts.find_one({"_id": operation_id, **scope})
        return await self._simulation_receipt(scope, project_id, operation_id, request_digest, receipt)

    @staticmethod
    def _job_public(job, *, include_result=True):
        result = _public(job)
        result.pop("request_digest", None)
        result.pop("worker_token", None)
        result.pop("worker_epoch", None)
        result.pop("lease_until", None)
        checkpoint = job.get("_checkpoint")
        if checkpoint:
            snapshot = checkpoint["snapshot"]
            result["checkpoints"] = [
                {
                    "policy_digest": snapshot["snapshot_digest"],
                    "committed_episodes": snapshot["committed_episodes"],
                    "committed_updates": snapshot["committed_updates"],
                }
            ]
        if not include_result and isinstance(result.get("result"), dict):
            result["result"] = {
                key: value
                for key, value in result["result"].items()
                if key not in {"files", "file_contents", "evaluation", "config", "recipe", "comparison"}
            }
        result["resume_available"] = (
            job["status"] == "interrupted"
            and not job.get("cancel_requested")
            and not job.get("input_changed")
        )
        return result

    @staticmethod
    def _stored_evidence(value):
        """Lossless BSON numeric roundtrip at the durable runtime JSON boundary."""
        try:
            encoded = json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            if len(encoded) > MAX_JSON:
                raise GameLearningError(
                    "stored_evidence_limit", "Stored runtime JSON exceeds its byte bound.", 413
                )
            return json.loads(encoded)
        except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as exc:
            if isinstance(exc, GameLearningError):
                raise
            raise GameLearningError(
                "stored_evidence_invalid", "Stored runtime evidence is not finite JSON.", 503
            ) from exc

    @staticmethod
    def _training_configuration(request, binding, demonstrations):
        from skeleton.jeeves.game_learning import GameLearningConfig

        episodes, steps = request.get("epochs", 16), binding["episode_steps"]
        if (
            type(episodes) is not int
            or not 1 <= episodes <= 256
            or type(steps) is not int
            or not 1 <= steps <= 4096
            or len(demonstrations) != len(binding.get("demonstrations", []))
        ):
            raise GameLearningError(
                "training_plan_invalid", "The admitted training episode plan differs.", 503
            )
        total = episodes + len(demonstrations)
        if total > 256:
            raise GameLearningError("episode_budget", "Demonstration plus online episodes exceed256.", 413)
        demo_steps = 0
        for demonstration in demonstrations:
            measured = demonstration["trace"]["steps"]
            if type(measured) is not int or not 1 <= measured <= steps:
                raise GameLearningError(
                    "training_plan_invalid", "The selected demonstration transition count differs.", 503
                )
            demo_steps += measured
        online_steps = episodes * steps
        if online_steps + demo_steps > 65536:
            raise GameLearningError(
                "update_budget",
                "Online episodes plus the selected measured demonstrations exceed65536updates.",
                413,
            )
        config = GameLearningConfig(
            **{
                key: request[key]
                for key in (
                    "alpha",
                    "gamma",
                    "epsilon",
                    "epsilon_decay",
                    "min_epsilon",
                    "reward_clip",
                    "imitation_strength",
                    "exploration_strategy",
                    "n_step",
                )
                if key in request
            },
            seed=request.get("seed", 0),
            max_episodes=total,
            max_updates=online_steps + demo_steps,
            max_states=request.get("max_states", 4096),
            trace_byte_limit=2 * 1024 * 1024,
        )
        plan = {
            "online_episodes": episodes,
            "demonstration_episodes": len(demonstrations),
            "demonstration_transitions": demo_steps,
            "online_transition_upper_bound": online_steps,
            "update_upper_bound": online_steps + demo_steps,
            "evaluation_seed_count": request.get("evaluation_seeds", 4),
            "evaluation_transition_upper_bound": request.get("evaluation_seeds", 4) * 2 * steps,
        }
        return config, plan

    async def start_job(self, scope, project_id, kind, body):
        environment = None
        try:
            job_id = _key(project_id, kind, body["idempotency_key"])
            digest = _digest(body)
            old = await self.jobs.find_one({"_id": job_id, **scope, "project_id": project_id})
            if old is not None:
                if old["request_digest"] != digest:
                    raise GameLearningError(
                        "idempotency_conflict", "Job key was reused with different input.", 409
                    )
                project = await self._project(project_id, scope)
                if job_id not in project["job_ids"]:
                    await self._authority(scope, old["input"])
                    changed = await self.projects.update_one(
                        {
                            "_id": project_id,
                            **scope,
                            "version": body["expected_version"],
                            "_input_epoch": old["input"].get("input_epoch", 0),
                            "_job_count": {"$lt": 512},
                            "job_ids": {"$ne": job_id},
                        },
                        {"$push": {"job_ids": job_id}, "$inc": {"_job_count": 1}},
                    )
                    if not changed.modified_count:
                        raise GameLearningError(
                            "project_conflict", "Project changed before prepared job recovery.", 409
                        )
                await self._schedule(job_id, scope)
                return await self.get_job(scope, job_id)
            project = await self._project(project_id, scope, body["expected_version"])
            if project["_job_count"] >= 512:
                raise GameLearningError("job_limit", "This project has reached its job limit.", 413)
            from core.game_play import resource_profiles

            profile_id = body.get("resource_profile", "cpu") if kind == "train" else "cpu"
            capacity = next(
                (item for item in resource_profiles()["profiles"] if item["profile_id"] == profile_id), None
            )
            if capacity is None:
                raise GameLearningError(
                    "resource_profile_unavailable", "Choose an available resource profile.", 409
                )
            requested_workers = body.get("workers", 1) if kind == "train" else 1
            if not capacity["available"] or requested_workers > capacity["max_training_workers"]:
                raise GameLearningError(
                    "worker_capacity", "Requested workers exceed current CPU/memory instance capacity.", 429
                )
            binding = await self._input(
                scope,
                project,
                source_id=body.get("source_id"),
                episode_steps=body.get("episode_steps") or 256,
                require_execution=kind == "train",
            )
            input_hook = getattr(self, "_job_input_hooks", {}).get(kind)
            if input_hook is not None:
                binding = await input_hook(scope, project, binding, body)
            await self._authority(scope, binding)
            # Source generation does not confer emulator or native-toolchain execution.
            environment = None
            if kind == "train":
                factory = await self._factory(scope, binding)
                environment = await _probe_environment(factory)
            if kind not in {"train", "generate"} and kind not in getattr(self, "_job_handlers", {}):
                raise GameLearningError(
                    "job_handler_unavailable", "This declared job handler is unavailable.", 503
                )
            if kind == "train" and body.get("algorithm", "q_learning") != "q_learning":
                raise GameLearningError(
                    "algorithm_unavailable", "Only measured tabular Q-learning is available."
                )
            parent = None
            parent_id = (
                (body.get("parent_policy_id") or project.get("policy_id"))
                if kind == "train" and not body.get("fresh_policy")
                else None
            )
            if parent_id:
                saved = await self._admitted_policy(scope, project_id, parent_id)
                if saved["snapshot"]["environment"] != environment.spec.as_dict():
                    raise GameLearningError(
                        "parent_environment_changed",
                        "The parent policy belongs to a different executable revision. Request fresh_policy explicitly.",
                        409,
                    )
                parent = saved["snapshot"]
                _json(parent, 2 * 1024 * 1024)
                binding["parent_policy"] = {
                    "policy_id": parent_id,
                    "snapshot_digest": parent["snapshot_digest"],
                }
                inherited = saved["input"].get("inherited_demonstrations", []) + saved["input"].get(
                    "demonstrations", []
                )
                binding["inherited_demonstrations"] = list(
                    {item["recording_id"]: item for item in inherited}.values()
                )
                if len(binding["inherited_demonstrations"]) > 64:
                    raise GameLearningError(
                        "teacher_lineage_limit",
                        "Parent teacher lineage exceeds the bounded policy budget.",
                        413,
                    )
            if kind == "generate" and body.get("policy_id"):
                admitted = await self._admitted_policy(scope, project_id, body["policy_id"])
                binding["generation_policy"] = {
                    "policy_id": body["policy_id"],
                    "snapshot_digest": admitted["snapshot"]["snapshot_digest"],
                }
            for session_id in body.get("session_ids", []):
                session = await self.sessions.find_one({"_id": session_id, **scope, "project_id": project_id})
                if (
                    session is None
                    or session_id not in project["session_ids"]
                    or session["input"]["tree_digest"] != binding["tree_digest"]
                    or session.get("_input_fenced")
                    or session["input"].get("input_epoch", 0) != binding.get("input_epoch", 0)
                ):
                    raise GameLearningError(
                        "session_lineage_unavailable",
                        "Training session lineage is unavailable for this revision.",
                        409,
                    )
            binding["session_ids"] = list(body.get("session_ids", []))
            binding["demonstrations"] = []
            for identifier in body.get("demonstration_ids", []):
                recorded = await self.database["game_learning_recordings"].find_one(
                    {
                        "_id": identifier,
                        **scope,
                        "project_id": project_id,
                        "status": "completed",
                        "consent": True,
                    }
                )
                if recorded is None:
                    raise GameLearningError(
                        "demonstration_unavailable", "Choose an owned completed consented recording.", 403
                    )
                if recorded["demonstration"]["trace"]["environment"] != environment.spec.as_dict():
                    raise GameLearningError(
                        "demonstration_environment_mismatch",
                        "Recording and training step budget/executable environment must match.",
                        409,
                    )
                binding["demonstrations"].append(
                    {
                        "recording_id": identifier,
                        "demonstration_digest": recorded["demonstration"]["demonstration_digest"],
                    }
                )
            demonstrations = (
                await self._demonstration_authority(scope, binding) if binding["demonstrations"] else []
            )
            total = body.get("epochs", 16) + len(binding["demonstrations"]) if kind == "train" else 1
            if total > 256:
                raise GameLearningError(
                    "episode_budget", "Demonstration plus online episodes exceed 256.", 413
                )
            learning_config = None
            training_plan = None
            if kind == "train":
                config, training_plan = self._training_configuration(body, binding, demonstrations)
                learning_config = config.as_dict()
            stamp = _now()
            doc = {
                "_id": job_id,
                **scope,
                "job_id": job_id,
                "project_id": project_id,
                "kind": kind,
                "status": "queued",
                "input": binding,
                "environment": environment.spec.as_dict() if environment is not None else None,
                "request": body,
                "request_digest": digest,
                "created_at": stamp,
                "updated_at": stamp,
                "progress": {
                    "completed": 0,
                    "total": total,
                    "unit": "episodes" if kind == "train" else "projects",
                },
                "cancel_requested": False,
                "input_changed": False,
                "worker_epoch": 0,
                "policy_id": _key(project_id, "policy", job_id),
                "_checkpoint": None,
                "_parent": parent,
            }
            if kind == "train":
                # Operational default selection is separate from immutable
                # numerical lineage. Freeze the pointer before execution so a
                # delayed completion cannot replace a concurrently newer policy.
                doc["default_policy_id_at_admission"] = project.get("policy_id")
                doc["_default_selection_pending"] = True
            if learning_config is not None:
                doc["learning_config"] = learning_config
                doc["learning_config_digest"] = _digest(learning_config)
                doc["training_plan"] = training_plan
            doc["storage_receipt"] = await self._admit(
                scope,
                "game-learning-job",
                job_id,
                len(_json(_public(doc))) + len(_json(binding)) + (len(_json(parent)) if parent else 0),
            )
            _json({"input": binding, "request": body, "parent": parent}, MAX_JSON - 65536)
            await self.jobs.update_one({"_id": job_id}, {"$setOnInsert": doc}, upsert=True)
            issued = await self.jobs.find_one({"_id": job_id, **scope})
            if (
                issued is None
                or issued["request_digest"] != digest
                or _digest(issued["input"]) != _digest(binding)
            ):
                raise GameLearningError(
                    "idempotency_conflict", "Job key already binds different admitted inputs.", 409
                )
            head = await self.projects.update_one(
                {
                    "_id": project_id,
                    **scope,
                    "version": project["version"],
                    "_job_count": {"$lt": 512},
                    "_input_epoch": binding["input_epoch"],
                    "job_ids": {"$ne": job_id},
                },
                {"$push": {"job_ids": job_id}, "$inc": {"_job_count": 1}},
            )
            if not head.modified_count:
                committed = await self._project(project_id, scope)
                if job_id in committed["job_ids"]:
                    await self._schedule(job_id, scope)
                    return self._job_public(await self.jobs.find_one({"_id": job_id, **scope}))
                await self.jobs.update_one(
                    {"_id": job_id, **scope, "status": "queued"},
                    {
                        "$set": {
                            "status": "failed",
                            "error": {
                                "code": "project_conflict",
                                "message": "Project changed before job admission.",
                            },
                        }
                    },
                )
                raise GameLearningError("project_conflict", "Project changed before job admission.", 409)
            await self._schedule(job_id, scope)
            return self._job_public(doc)

        finally:
            if environment is not None:
                await _close_environment(environment)

    async def _recover_jobs(self, scope, project_id):
        await self.jobs.update_many(
            {**scope, "project_id": project_id, "status": "running", "lease_until": {"$lt": _now()}},
            {
                "$set": {
                    "status": "interrupted",
                    "updated_at": _now(),
                    "error": {
                        "code": "worker_interrupted",
                        "message": "Worker lease expired; committed episodes are preserved.",
                    },
                },
                "$unset": {"worker_token": "", "lease_until": ""},
            },
        )
        await self.jobs.update_many(
            {
                **scope,
                "project_id": project_id,
                "status": {"$in": ["queued", "interrupted"]},
                "cancel_requested": True,
            },
            {"$set": {"status": "cancelled", "updated_at": _now()}},
        )

    async def _schedule_queued(self, scope, project_id):
        rows = (
            await self.jobs.find(
                {**scope, "project_id": project_id, "status": "queued", "cancel_requested": False}
            )
            .limit(8)
            .to_list(length=8)
        )
        for row in rows:
            await self._schedule(row["job_id"], scope)

    async def _schedule(self, job_id, scope):
        if job_id not in self._tasks and len(self._tasks) < 8:
            queued = await self.jobs.find_one(
                {"_id": job_id, **scope, "status": "queued", "cancel_requested": False}
            )
            if queued is None or job_id in self._tasks or len(self._tasks) >= 8:
                return
            expected_worker_epoch = queued.get("worker_epoch", 0) + 1
            task = asyncio.create_task(self._run_job(job_id, scope))
            self._tasks[job_id] = task

            def completed(task):
                if self._tasks.get(job_id) is not task:
                    return
                self._tasks.pop(job_id, None)
                if queued["kind"] == "studio_learning" and not task.cancelled() and task.exception() is None:
                    from core.game_studio_learning import after_job

                    continuation = asyncio.create_task(
                        after_job(scope, job_id, expected_worker_epoch=expected_worker_epoch)
                    )
                    self._studio_continuations.add(continuation)

                    def settled(done):
                        self._studio_continuations.discard(done)
                        if not done.cancelled() and done.exception() is not None:
                            log.warning(
                                "Studio continuation %s stopped with %s",
                                job_id,
                                type(done.exception()).__name__,
                            )

                    continuation.add_done_callback(settled)
                if not task.cancelled() and task.exception() is not None:
                    log.warning(
                        "Game learning task %s ended with %s", job_id, type(task.exception()).__name__
                    )

            task.add_done_callback(completed)

    async def get_job(self, scope, job_id):
        doc = await self.jobs.find_one({"_id": job_id, **scope})
        if doc is None:
            raise GameLearningError("job_not_found", "Learning job not found.", 404)
        project = await self._project(doc["project_id"], scope)
        if job_id not in project["job_ids"]:
            raise GameLearningError("job_not_found", "Learning job was not admitted to this project.", 404)
        await self._recover_jobs(scope, doc["project_id"])
        await self._schedule(job_id, scope)
        current = await self.jobs.find_one({"_id": job_id, **scope})
        if await self._repair_default_selection(scope, current):
            current = await self.jobs.find_one({"_id": job_id, **scope})
        result = self._job_public(current)
        task = self._tasks.get(job_id)
        result["local_worker_draining"] = bool(
            current["status"] == "interrupted" and task is not None and not task.done()
        )
        if result["local_worker_draining"]:
            result["resume_available"] = False
        return result

    async def cancel_job(self, scope, job_id):
        # A stop request must not start a queued worker through get_job's
        # ordinary read-driven scheduler before applying the cancellation CAS.
        owned = await self.jobs.find_one({"_id": job_id, **scope})
        if owned is None:
            raise GameLearningError("job_not_found", "Learning job not found.", 404)
        project = await self._project(owned["project_id"], scope)
        if job_id not in project["job_ids"]:
            raise GameLearningError("job_not_found", "Learning job was not admitted to this project.", 404)
        result = await self.jobs.find_one_and_update(
            {"_id": job_id, **scope, "status": {"$in": ["queued", "running", "interrupted"]}},
            {"$set": {"cancel_requested": True, "updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )
        if job_id in self._cancel:
            self._cancel[job_id].set()
        if result is not None and result["status"] != "running":
            await self.jobs.update_one(
                {"_id": job_id, **scope, "status": result["status"]}, {"$set": {"status": "cancelled"}}
            )
        return await self.get_job(scope, job_id)

    async def resume_job(self, scope, job_id):
        await self.get_job(scope, job_id)
        active = self._tasks.get(job_id)
        if active is not None and not active.done():
            raise GameLearningError(
                "worker_draining", "The previous physical worker must stop before this job can resume.", 409
            )
        doc = await self.jobs.find_one({"_id": job_id, **scope})
        if doc["status"] != "interrupted" or doc["cancel_requested"] or doc["input_changed"]:
            raise GameLearningError(
                "job_not_resumable", "Only an interrupted, unchanged job can resume.", 409
            )
        await self._authority(scope, doc["input"])
        changed = await self.jobs.update_one(
            {
                "_id": job_id,
                **scope,
                "status": "interrupted",
                "worker_epoch": doc["worker_epoch"],
                "cancel_requested": False,
                "input_changed": False,
            },
            {"$set": {"status": "queued", "updated_at": _now()}, "$unset": {"error": ""}},
        )
        if not changed.modified_count:
            raise GameLearningError("job_conflict", "Job state changed before resume.", 409)
        await self._schedule(job_id, scope)
        return await self.get_job(scope, job_id)

    async def _checkpoint(self, scope, job, token, snapshot, trace, batch_state=None):
        return await self._guarded_write(
            scope,
            job["input"],
            lambda: self._commit_checkpoint(scope, job, token, snapshot, trace, batch_state),
        )

    async def _project_committed_episode(self, scope, job):
        checkpoint = job.get("_checkpoint")
        if not checkpoint or checkpoint.get("trace") is None:
            return
        checkpoint = self._stored_evidence(checkpoint)
        snapshot, trace = checkpoint["snapshot"], checkpoint["trace"]
        summary = next(
            (row for row in snapshot["episodes"] if row["episode_id"] == trace["episode_id"]), None
        )
        if (
            summary is None
            or snapshot.get("policy_id") != job["policy_id"]
            or snapshot.get("snapshot_digest")
            != _digest({key: value for key, value in snapshot.items() if key != "snapshot_digest"})
            or trace.get("trace_digest")
            != _digest({key: value for key, value in trace.items() if key != "trace_digest"})
            or any(
                trace.get(key) != summary.get(key)
                for key in ("episode_id", "trace_digest", "seed", "steps", "return")
            )
        ):
            raise GameLearningError(
                "episode_checkpoint_corrupt",
                "The authoritative checkpoint trace differs from its ledger.",
                503,
            )
        episode_id = trace["episode_id"]
        await self.episodes.update_one(
            {
                "_id": job["job_id"] + ":" + episode_id,
                **scope,
                "project_id": job["project_id"],
                "job_id": job["job_id"],
            },
            {
                "$set": {
                    "episode_id": episode_id,
                    "trace": trace,
                    "policy_digest": snapshot["snapshot_digest"],
                }
            },
            upsert=True,
        )
        projected = await self.episodes.find_one(
            {"_id": job["job_id"] + ":" + episode_id, **scope, "job_id": job["job_id"]},
            {"trace.trace_digest": 1, "project_id": 1},
        )
        if (
            projected is None
            or projected.get("project_id") != job["project_id"]
            or projected.get("trace", {}).get("trace_digest") != trace["trace_digest"]
        ):
            raise GameLearningError("episode_projection_conflict", "Committed trace projection differs.", 503)

    async def _commit_checkpoint(self, scope, job, token, snapshot, trace, batch_state=None):
        await self._authority(scope, job["input"], dragon_guarded=True)
        current = await self.jobs.find_one(
            {
                "_id": job["job_id"],
                **scope,
                "status": "running",
                "worker_token": token,
                "lease_until": {"$gt": _now()},
                "cancel_requested": False,
                "input_changed": False,
            }
        )
        if current is None:
            raise GameLearningError("worker_fenced", "Worker lost its publication fence.", 409)
        # Finish the last acknowledged projection before replacing the only
        # authoritative full trace. This keeps one bounded row per episode.
        await self._project_committed_episode(scope, current)
        payload = {"snapshot": snapshot, "trace": trace, "batch_state": batch_state}
        _json({"input": job["input"], "parent": job.get("_parent"), "checkpoint": payload}, MAX_JSON - 65536)
        admission = await self._admit(
            scope,
            "game-learning-checkpoint",
            job["job_id"] + ":" + _digest(payload),
            len(_json(payload)),
        )
        frame_scope = {**scope, "job_id": job["job_id"], "stream_id": job.get("frame_stream_id")}
        if batch_state is not None and trace is None and job.get("frame_stream_id"):
            await self.database["game_learning_live_frames"].delete_many(frame_scope)
        elif batch_state is not None and job.get("frame_stream_id"):
            await self.database["game_learning_live_frames"].update_many(
                frame_scope, {"$set": {"instance_status": "stopped"}}
            )
        publication_filter = {
            "_id": job["job_id"],
            **scope,
            "status": "running",
            "worker_token": token,
            "lease_until": {"$gt": _now()},
            "cancel_requested": False,
            "input_changed": False,
        }
        try:
            result = await self.jobs.update_one(
                publication_filter,
                {
                    "$set": {
                        "_checkpoint": payload,
                        "progress.completed": snapshot["committed_episodes"],
                        "updated_at": _now(),
                        "checkpoint_storage_receipt": admission,
                    }
                },
            )
        except PyMongoError as exc:
            # A transport failure can follow a committed server-side update.
            # Only an exact authoritative readback under the same live worker
            # may acknowledge it; an unreadable outcome remains resumable.
            try:
                observed = await self.jobs.find_one({**publication_filter, "lease_until": {"$gt": _now()}})
            except PyMongoError as read_error:
                raise GameLearningError(
                    "checkpoint_publication_unconfirmed",
                    "Checkpoint acknowledgement and readback are unavailable; resume authoritative stored progress.",
                    503,
                ) from read_error
            if observed is None or _digest(self._stored_evidence(observed.get("_checkpoint"))) != _digest(
                payload
            ):
                raise GameLearningError(
                    "checkpoint_publication_unconfirmed",
                    "Checkpoint acknowledgement was lost; resume from authoritative stored progress.",
                    503,
                ) from exc
        else:
            if not result.matched_count:
                raise GameLearningError("worker_fenced", "Worker lost its publication fence.", 409)
        try:
            await self._project_committed_episode(scope, {**current, "_checkpoint": payload})
        except Exception as exc:
            # The episode has committed. Keep its full trace in the job and
            # repair it before the next checkpoint/terminal overwrite; raising
            # here would incorrectly roll back acknowledged learner progress.
            log.warning(
                "Committed episode projection %s awaits repair: %s", job["job_id"], type(exc).__name__
            )

    async def _heartbeat(self, scope, job_id, token, cancelled, slot_id, slot_token):
        try:
            while not cancelled.is_set():
                await asyncio.sleep(1)
                slot = await self.workers.update_one(
                    {"_id": slot_id, "worker_token": slot_token, "lease_until": {"$gt": _now()}},
                    {"$set": {"lease_until": _now() + timedelta(seconds=30)}},
                )
                credits = await self.workers.update_many(
                    {
                        "worker_token": slot_token,
                        "job_id": job_id,
                        "resource_class": "training",
                        "lease_until": {"$gt": _now()},
                    },
                    {"$set": {"lease_until": _now() + timedelta(seconds=30)}},
                )
                if not slot.modified_count:
                    cancelled.set()
                    return
                row = await self.jobs.find_one_and_update(
                    {
                        "_id": job_id,
                        **scope,
                        "status": "running",
                        "worker_token": token,
                        "lease_until": {"$gt": _now()},
                        "cancel_requested": False,
                        "input_changed": False,
                    },
                    {"$set": {"lease_until": _now() + timedelta(seconds=30)}},
                    return_document=ReturnDocument.AFTER,
                )
                expected_credits = (
                    row["request"].get("workers", 1)
                    if row is not None and row["kind"] == "train"
                    else (
                        1
                        if row is not None
                        and row["kind"]
                        in {
                            "build",
                            "generate",
                            "successor",
                            "successor_compare",
                            "desktop",
                            "studio_learning",
                            "review",
                        }
                        else 0
                    )
                )
                if row is None or credits.matched_count != expected_credits:
                    cancelled.set()
                    return
                if row["kind"] == "studio_learning":
                    campaigns = self.database["game_learning_campaigns"]
                    renewed = await campaigns.update_one(
                        {
                            **scope,
                            "active_job_id": job_id,
                            "_worker_token": token,
                            "_worker_epoch": row["worker_epoch"],
                            "source_fenced": False,
                            "_worker_lease_until": {"$gt": _now()},
                        },
                        {"$set": {"_worker_lease_until": row["lease_until"]}},
                    )
                    if not renewed.matched_count:
                        claim = await campaigns.find_one(
                            {**scope, "active_job_id": job_id},
                            {"_worker_token": 1, "_worker_epoch": 1, "source_fenced": 1},
                        )
                        if (
                            claim is None
                            or claim.get("source_fenced")
                            or claim.get("_worker_token") is not None
                        ):
                            cancelled.set()
                            return
        except PyMongoError:
            cancelled.set()
            log.warning("Game learning worker lease could not be renewed")

    async def _run_job(self, job_id, scope):
        async with self._slots:
            slot_id, slot_token = None, str(uuid4())
            for index in range(2):
                identifier = "game-learning-worker:" + str(index)
                await self.workers.update_one(
                    {"_id": identifier},
                    {"$setOnInsert": {"lease_until": datetime(1970, 1, 1, tzinfo=timezone.utc)}},
                    upsert=True,
                )
                claimed = await self.workers.find_one_and_update(
                    {"_id": identifier, "lease_until": {"$lt": _now()}},
                    {
                        "$set": {
                            "worker_token": slot_token,
                            "job_id": job_id,
                            "lease_until": _now() + timedelta(seconds=30),
                        }
                    },
                    return_document=ReturnDocument.AFTER,
                )
                if claimed is not None:
                    slot_id = identifier
                    break
            if slot_id is None:
                return
            actor_slots = []
            try:
                admitted = await self.jobs.find_one({"_id": job_id, **scope})
                required = (
                    admitted["request"].get("workers", 1)
                    if admitted["kind"] == "train"
                    else (
                        1
                        if admitted["kind"]
                        in {
                            "build",
                            "generate",
                            "successor",
                            "successor_compare",
                            "desktop",
                            "studio_learning",
                            "review",
                        }
                        else 0
                    )
                )
                from core.game_play import resource_profiles

                profile_id = (
                    admitted["request"].get("resource_profile", "cpu")
                    if admitted["kind"] == "train"
                    else "cpu"
                )
                profile = next(
                    (item for item in resource_profiles()["profiles"] if item["profile_id"] == profile_id),
                    None,
                )
                if profile is None or not profile["available"] or required > profile["max_training_workers"]:
                    return
                credit_ids = profile.get("training_credit_ids") or [
                    "game-learning-actor:" + str(index) for index in range(profile["max_training_workers"])
                ]
                if (
                    not isinstance(credit_ids, list)
                    or len(credit_ids) > 8
                    or len(set(credit_ids)) != len(credit_ids)
                    or len(credit_ids) < required
                    or any(
                        not isinstance(value, str)
                        or not value.startswith(("game-learning-actor:", "game-learning-play:"))
                        for value in credit_ids
                    )
                ):
                    return
                for identity in credit_ids:
                    if len(actor_slots) == required:
                        break
                    await self.workers.update_one(
                        {"_id": identity},
                        {"$setOnInsert": {"lease_until": datetime(1970, 1, 1, tzinfo=timezone.utc)}},
                        upsert=True,
                    )
                    credit = await self.workers.find_one_and_update(
                        {"_id": identity, "lease_until": {"$lt": _now()}},
                        {
                            "$set": {
                                "worker_token": slot_token,
                                "job_id": job_id,
                                "resource_class": "training",
                                "lease_until": _now() + timedelta(seconds=30),
                            },
                            "$unset": {"play_id": "", "credit_kind": ""},
                        },
                        return_document=ReturnDocument.AFTER,
                    )
                    if credit:
                        actor_slots.append(identity)
                if len(actor_slots) != required:
                    return
                await self._run_claimed_job(job_id, scope, slot_id, slot_token)
            finally:
                if actor_slots:
                    await self.workers.update_many(
                        {"_id": {"$in": actor_slots}, "worker_token": slot_token},
                        {
                            "$set": {"lease_until": _now()},
                            "$unset": {"worker_token": "", "job_id": "", "resource_class": ""},
                        },
                    )
                await self.workers.update_one(
                    {"_id": slot_id, "worker_token": slot_token},
                    {"$set": {"lease_until": _now()}, "$unset": {"worker_token": "", "job_id": ""}},
                )

    async def _run_claimed_job(self, job_id, scope, slot_id, slot_token):
        project = await self._project(
            (await self.jobs.find_one({"_id": job_id, **scope}))["project_id"], scope
        )
        if job_id not in project["job_ids"]:
            return
        token = str(uuid4())
        job = await self.jobs.find_one_and_update(
            {
                "_id": job_id,
                **scope,
                "status": "queued",
                "cancel_requested": False,
                "input_changed": False,
            },
            {
                "$set": {
                    "status": "running",
                    "worker_token": token,
                    "lease_until": _now() + timedelta(seconds=30),
                    "updated_at": _now(),
                },
                "$inc": {"worker_epoch": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if job is None:
            return
        cancelled = threading.Event()
        self._cancel[job_id] = cancelled
        heartbeat = asyncio.create_task(self._heartbeat(scope, job_id, token, cancelled, slot_id, slot_token))
        loop = asyncio.get_running_loop()
        worker_deadline = time.monotonic() + (
            job["request"].get("execution_seconds", 300) if job["kind"] == "train" else 300
        )

        def checkpoint(snapshot, trace, batch_state=None):
            future = asyncio.run_coroutine_threadsafe(
                self._checkpoint(scope, job, token, snapshot, trace, batch_state), loop
            )
            try:
                future.result(timeout=max(0.001, min(30.0, worker_deadline - time.monotonic())))
            except TimeoutError:
                cancelled.set()
                # Publication may already have reached Mongo. Keep physical
                # ownership and observe its outcome before the learner decides
                # whether to retain or roll back this episode in memory.
                future.result()

        def authorize():
            if time.monotonic() >= worker_deadline:
                cancelled.set()
                raise GameLearningError(
                    "job_deadline", "The bounded worker execution deadline was reached.", 409
                )
            if cancelled.is_set():
                raise GameLearningError("job_cancelled", "Learning worker was cancelled.", 409)

        async def emit_event(payload):
            await self.emit_job_event(scope, job, token, payload)

        def on_frame(payload):
            future = asyncio.run_coroutine_threadsafe(emit_event(payload), loop)
            try:
                future.result(timeout=max(0.001, min(10.0, worker_deadline - time.monotonic())))
            except TimeoutError:
                cancelled.set()
                future.result()

        try:
            for key in ("request", "input", "_checkpoint", "_parent", "learning_config", "training_plan"):
                if job.get(key) is not None:
                    job[key] = self._stored_evidence(job[key])
            frame_stream_id = str(uuid4())
            await self.jobs.update_one(
                {"_id": job_id, **scope, "worker_token": token},
                {"$set": {"frame_stream_id": frame_stream_id}},
            )
            job["frame_stream_id"] = frame_stream_id
            factory = await self._factory(scope, job["input"]) if job["kind"] == "train" else None
            if job["kind"] == "train":
                job["_environment_request"] = await self.environment_request(scope, job["input"])
                job["_demonstrations"] = await self._demonstration_authority(scope, job["input"])
                # This must remain an executor Future, not a Task wrapping
                # to_thread: loop shutdown cancels every Task, which can finish
                # the wrapper while its real actor-owning thread is still alive.
                worker = loop.run_in_executor(
                    None, self._train, job, factory, checkpoint, cancelled, authorize, on_frame
                )
                try:
                    result, policy = await asyncio.shield(worker)
                except asyncio.CancelledError:
                    cancelled.set()
                    cleanup = asyncio.ensure_future(asyncio.gather(worker, return_exceptions=True))
                    while not cleanup.done():
                        try:
                            await asyncio.shield(cleanup)
                        except asyncio.CancelledError:
                            cancelled.set()
                    raise
                await self._authority(scope, job["input"])
                _json({"policy": policy, "input": job["input"]})
                await self.policies.update_one(
                    {"_id": job["policy_id"]},
                    {
                        "$setOnInsert": {
                            **scope,
                            "project_id": job["project_id"],
                            "policy_id": job["policy_id"],
                            "job_id": job_id,
                            "input": job["input"],
                            "snapshot": policy,
                            "created_at": _now(),
                        }
                    },
                    upsert=True,
                )
            else:
                if job["kind"] == "generate":
                    operation = self._generate(scope, job, factory, cancelled)
                else:
                    operation = self._job_handlers[job["kind"]](scope, job, cancelled, emit_event)
                worker = asyncio.create_task(operation)
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
            _json(result, 2 * 1024 * 1024)
            done = await self._complete_job(scope, job, token, result)
            if not done.modified_count:
                raise GameLearningError("worker_fenced", "Worker lost its completion fence.", 409)
            if job["kind"] == "train":
                if job.get("_default_selection_pending"):
                    completed = await self.jobs.find_one({"_id": job_id, **scope})
                    await self._repair_default_selection(scope, completed)
                else:
                    # An already admitted historical job keeps its original
                    # completion path; reads do not retrofit a selection intent.
                    await self._select_default_policy(scope, job, result, project)
        except asyncio.CancelledError:
            # The shielded worker path above has already drained its physical
            # thread/actors. Publish interruption only after that exact outcome.
            cancelled.set()
            stopping = await self.jobs.find_one({"_id": job_id, **scope})
            interrupted_state = (
                "cancelled"
                if stopping and (stopping.get("cancel_requested") or stopping.get("input_changed"))
                else "interrupted"
            )
            await self.jobs.update_one(
                {"_id": job_id, **scope, "status": "running", "worker_token": token},
                {
                    "$set": {
                        "status": interrupted_state,
                        "updated_at": _now(),
                        "error": {
                            "code": "worker_interrupted",
                            "message": "Execution stopped after worker cleanup; exact committed checkpoints may resume.",
                        },
                    },
                    "$unset": {"worker_token": "", "lease_until": ""},
                },
            )
            raise
        except Exception as exc:
            log.warning("Game learning job %s ended with %s", job_id, type(exc).__name__)
            row = await self.jobs.find_one({"_id": job_id, **scope})
            stopped = row.get("cancel_requested") or row.get("input_changed")
            time_slice = (
                job["kind"] == "train"
                and time.monotonic() >= worker_deadline
                and row.get("_checkpoint") is not None
            )
            storage_interrupted = job["kind"] == "train" and (
                isinstance(exc, PyMongoError)
                or getattr(exc, "code", None) == "checkpoint_publication_unconfirmed"
            )
            state = (
                "cancelled" if stopped else "interrupted" if time_slice or storage_interrupted else "failed"
            )
            await self.jobs.update_one(
                {"_id": job_id, **scope, "status": "running", "worker_token": token},
                {
                    "$set": {
                        "status": state,
                        "error": {
                            "code": (
                                "worker_time_slice_exhausted"
                                if time_slice and not stopped
                                else (
                                    "worker_storage_interrupted"
                                    if storage_interrupted and not stopped
                                    else getattr(exc, "code", "execution_rejected")
                                )
                            ),
                            "message": (
                                "The bounded time slice ended after actor cleanup; resume the exact committed checkpoint."
                                if time_slice and not stopped
                                else (
                                    "Storage acknowledgement was interrupted after worker cleanup; resume authoritative committed progress."
                                    if storage_interrupted and not stopped
                                    else "Execution stopped; committed checkpoints remain available."
                                )
                            ),
                        },
                        "updated_at": _now(),
                    },
                    "$unset": {"worker_token": "", "lease_until": ""},
                },
            )
        finally:
            cancelled.set()
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            self._cancel.pop(job_id, None)

    async def _select_default_policy(self, scope, job, result, claimed_project):
        parent = job["input"].get("parent_policy")
        observed = job.get(
            "default_policy_id_at_admission",
            parent["policy_id"] if parent else claimed_project.get("policy_id"),
        )
        receipt = {"policy_id": job["policy_id"], "comparator_policy_id": observed}
        acceptance = result.get("acceptance")
        if acceptance is not None:
            if acceptance.get("meets_configured_return_gate") is not True:
                return {**receipt, "state": "rejected", "reason": "configured_return_gate_not_met"}
            baseline = acceptance.get("baseline", {})
            if parent:
                if (
                    parent["policy_id"] != observed
                    or baseline.get("kind") != "parent_policy"
                    or baseline.get("policy_digest") != parent["snapshot_digest"]
                ):
                    return {**receipt, "state": "superseded", "reason": "admission_comparator_differs"}
            elif observed is not None or baseline.get("kind") != "seeded_uniform_random":
                # A fresh candidate beating random has not demonstrated that
                # it beats an already selected project policy.
                return {**receipt, "state": "superseded", "reason": "admission_comparator_differs"}
        if claimed_project["version"] != job["input"]["project_version"] or claimed_project.get(
            "_input_epoch", 0
        ) != job["input"].get("input_epoch", 0):
            return {**receipt, "state": "superseded", "reason": "project_revision_changed"}

        async def publish():
            await self._authority(scope, job["input"], dragon_guarded=True)
            changed = await self.projects.update_one(
                {
                    "_id": job["project_id"],
                    **scope,
                    "version": job["input"]["project_version"],
                    "_input_epoch": job["input"].get("input_epoch", 0),
                    "policy_id": observed,
                },
                {"$set": {"policy_id": job["policy_id"]}},
            )
            if changed.modified_count:
                return {**receipt, "state": "selected", "reason": "admission_comparator_cas"}
            selected = await self.projects.find_one(
                {
                    "_id": job["project_id"],
                    **scope,
                    "version": job["input"]["project_version"],
                    "_input_epoch": job["input"].get("input_epoch", 0),
                    "policy_id": job["policy_id"],
                },
                {"_id": 1},
            )
            return {
                **receipt,
                "state": "selected" if selected else "superseded",
                "reason": "already_selected" if selected else "project_default_changed",
            }

        return await self._guarded_write(scope, job["input"], publish)

    async def _repair_default_selection(self, scope, job):
        """Finish only a new job's issued post-completion selection intent."""
        if (
            job is None
            or job.get("kind") != "train"
            or job.get("status") != "completed"
            or job.get("_default_selection_pending") is not True
        ):
            return False
        try:
            # A prepared policy row or caller-supplied passing scalar is never
            # enough. Reopen the exact completed issuer and current rights.
            _, issuer, _ = await self._policy_evidence(scope, job["project_id"], job["policy_id"])
            project = await self._project(job["project_id"], scope)
            receipt = await self._select_default_policy(scope, job, issuer["result"], project)
        except GameLearningError as exc:
            if exc.status not in {403, 404} and exc.code not in {
                "input_changed",
                "input_fenced",
                "project_conflict",
                "policy_runtime_unavailable",
            }:
                log.warning("Policy default selection %s awaits repair: %s", job["job_id"], exc.code)
                return False
            receipt = {"policy_id": job["policy_id"], "state": "unavailable", "reason": exc.code}
        except PyMongoError as exc:
            log.warning(
                "Policy default selection %s awaits storage recovery: %s", job["job_id"], type(exc).__name__
            )
            return False
        receipt["selection_digest"] = _digest(receipt)
        changed = await self.jobs.update_one(
            {
                "_id": job["job_id"],
                **scope,
                "status": "completed",
                "policy_id": job["policy_id"],
                "_default_selection_pending": True,
            },
            {"$set": {"default_selection": receipt}, "$unset": {"_default_selection_pending": ""}},
        )
        return bool(changed.modified_count)

    async def _complete_job(self, scope, job, token, result):
        await self._authority(scope, job["input"])
        job_id = job["job_id"]

        async def publish():
            await self._authority(scope, job["input"], dragon_guarded=True)
            if job["kind"] == "train":
                current = await self.jobs.find_one(
                    {
                        "_id": job_id,
                        **scope,
                        "status": "running",
                        "worker_token": token,
                        "cancel_requested": False,
                        "input_changed": False,
                        "lease_until": {"$gt": _now()},
                    }
                )
                if current is None:
                    raise GameLearningError("worker_fenced", "Worker lost its completion fence.", 409)
                await self._project_committed_episode(scope, current)
            return await self.jobs.update_one(
                {
                    "_id": job_id,
                    **scope,
                    "status": "running",
                    "worker_token": token,
                    "cancel_requested": False,
                    "input_changed": False,
                    "lease_until": {"$gt": _now()},
                },
                {
                    "$set": {
                        "status": "completed",
                        "result": result,
                        "metrics": result.get("metrics", {}),
                        "progress.completed": job["progress"]["total"],
                        "updated_at": _now(),
                    },
                    "$unset": {"worker_token": "", "lease_until": ""},
                },
            )

        return await self._guarded_write(scope, job["input"], publish)

    @staticmethod
    def _train(job, factory, checkpoint, cancelled, authorize, on_frame=None):
        from skeleton.jeeves.game_learning import GameLearningConfig, GamePolicyLearner

        request = job["request"]
        recordings = job.get("_demonstrations", [])
        if job.get("request_digest") != _digest(request):
            raise GameLearningError("training_request_changed", "The frozen training request differs.", 503)
        if job.get("learning_config") is not None:
            config, plan = GameLearningWorkspace._training_configuration(request, job["input"], recordings)
            if (
                config.as_dict() != job["learning_config"]
                or job.get("learning_config_digest") != _digest(config.as_dict())
                or job.get("training_plan") != plan
                or job["progress"]["total"] != config.max_episodes
            ):
                raise GameLearningError(
                    "training_configuration_changed",
                    "Frozen training knobs or measured work plan differ.",
                    503,
                )
        else:
            # Historical jobs retain their original fixed numerical defaults.
            # They do not acquire newly requested knobs while recovering.
            config = GameLearningConfig(
                seed=request.get("seed", 0),
                max_episodes=256,
                max_updates=65536,
                max_states=4096,
                trace_byte_limit=2 * 1024 * 1024,
            )
        parent_pin, parent = job["input"].get("parent_policy"), job.get("_parent")
        if (
            (parent_pin is None) != (parent is None)
            or parent_pin
            and (
                parent.get("snapshot_digest") != parent_pin.get("snapshot_digest")
                or parent.get("policy_id") != parent_pin.get("policy_id")
            )
        ):
            raise GameLearningError(
                "training_parent_changed", "The full admitted parent snapshot differs.", 503
            )
        authorize()
        environment = factory()
        try:
            # A descriptor probe may own a real native subprocess. Release it
            # before actors claim their physical process budget.
            environment_spec = environment.spec
            if environment_spec.as_dict() != job.get("environment"):
                raise GameLearningError(
                    "training_environment_changed",
                    "Runtime code, controller profile or environment differs from the admitted descriptor.",
                    409,
                )
            authorize()
            from skeleton.jeeves.game_learning_demonstrations import close_environment

            close_environment(environment)
            environment = None
            lineage = {
                "project_id": job["project_id"],
                "input_digest": _digest(job["input"]),
                "sources": job["input"]["sources"],
            }
            if recordings:
                lineage["admitted_traces"] = {
                    recording["trace"]["trace_digest"]: recording["trace"]["source_lineage"]
                    for recording in recordings
                }
            prior = job.get("_checkpoint")
            if prior is not None:
                learner = GamePolicyLearner(
                    environment_spec,
                    config,
                    policy_id=job["policy_id"],
                    source_lineage=lineage,
                    parent_snapshot=prior["snapshot"],
                )
            elif job.get("_parent") is not None:
                learner = GamePolicyLearner.fork(
                    job["_parent"],
                    newpolicy_id=job["policy_id"],
                    newsource_lineage=lineage,
                    config=config,
                    expected_spec=environment_spec,
                )
            else:
                learner = GamePolicyLearner(
                    environment_spec, config, policy_id=job["policy_id"], source_lineage=lineage
                )
            restored = learner.snapshot()
            if parent_pin and (
                restored.get("parent_snapshot_digest") != parent_pin["snapshot_digest"]
                or restored.get("parent_policy_id") != parent_pin["policy_id"]
            ):
                raise GameLearningError(
                    "training_parent_changed",
                    "Recovered policy no longer binds its admitted full parent.",
                    503,
                )
            from skeleton.jeeves.game_learning_parallel import (
                GameEnvironmentRequest,
                ParallelGamePolicyTrainer,
            )
            from skeleton.jeeves.game_learning_demonstrations import learn_demonstrations

            environment_request = GameEnvironmentRequest.from_dict(job["_environment_request"])
            committed = {row["trace_digest"] for row in learner.snapshot()["episodes"]}
            pending_recordings = [
                recording for recording in recordings if recording["trace"]["trace_digest"] not in committed
            ]
            if pending_recordings:
                learn_demonstrations(
                    learner,
                    environment_request,
                    pending_recordings,
                    on_checkpoint=checkpoint,
                    cancel=cancelled.is_set,
                    authorize=authorize,
                )
            remaining = job["progress"]["total"] - learner.snapshot()["committed_episodes"]
            if remaining > 0:
                trainer = ParallelGamePolicyTrainer(
                    learner,
                    environment_request,
                    actors=request.get("workers", 1),
                    frame_stride=request.get("frame_stride", 8),
                    actor_timeout_seconds=120,
                )
                trainer.train(
                    episodes=remaining,
                    resume_state=prior.get("batch_state") if prior else None,
                    on_checkpoint=checkpoint,
                    on_frame=on_frame,
                    cancel=cancelled.is_set,
                    authorize=authorize,
                )
            authorize()
            snapshot = learner.snapshot()
            seeds = []
            probe = (request.get("seed", 0) + 1_000_003) % (2**63)
            while len(seeds) < request.get("evaluation_seeds", 4):
                if probe not in snapshot["training_seeds"]:
                    seeds.append(probe)
                probe = (probe + 1) % (2**63)
            evaluation = learner.evaluate(
                factory,
                heldout_seeds=seeds,
                baseline_snapshot=job.get("_parent"),
                cancel=cancelled.is_set,
                authorize=authorize,
            ).as_dict()
            metrics = {
                key: evaluation[key]
                for key in (
                    "candidate_mean_return",
                    "baseline_mean_return",
                    "mean_return_difference",
                    "measured_steps",
                    "evaluation_digest",
                )
            }
            return {
                "policy_id": job["policy_id"],
                "policy_digest": snapshot["snapshot_digest"],
                "committed_episodes": snapshot["committed_episodes"],
                "committed_updates": snapshot["committed_updates"],
                "learning_config_digest": _digest(config.as_dict()),
                "metrics": metrics,
                "evaluation": evaluation,
                "acceptance": GameLearningWorkspace._training_acceptance(evaluation, request),
                "promotion_authorized": False,
            }, snapshot

        finally:
            from skeleton.jeeves.game_learning_demonstrations import close_environment

            if environment is not None:
                close_environment(environment)

    @staticmethod
    def _training_acceptance(evaluation, request):
        """Derive a declared return gate from actual paired trajectories only."""
        episodes = evaluation["episodes"]
        seeds = evaluation.get("heldout_seeds")
        if (
            not isinstance(episodes, list)
            or not 1 <= len(episodes) <= 8
            or not isinstance(seeds, list)
            or len(seeds) != len(episodes)
            or any(type(seed) is not int or not 0 <= seed < 2**63 for seed in seeds)
            or len(set(seeds)) != len(seeds)
        ):
            raise GameLearningError(
                "policy_evaluation_invalid", "Paired evaluation seed ledger differs.", 503
            )
        for item, seed in zip(episodes, seeds):
            if type(seed) is not int or not 0 <= seed < 2**63 or item.get("seed") != seed:
                raise GameLearningError("policy_evaluation_invalid", "Paired evaluation seed differs.", 503)
            returns = [item[label]["return"] for label in ("candidate", "baseline")]
            if any(type(value) not in (int, float) or not math.isfinite(value) for value in returns):
                raise GameLearningError(
                    "policy_evaluation_invalid", "Measured paired returns are not finite.", 503
                )
            if item.get("return_difference") != returns[0] - returns[1]:
                raise GameLearningError(
                    "policy_evaluation_invalid", "Measured paired return difference differs.", 503
                )
        difference = math.fsum(item["return_difference"] for item in episodes) / len(episodes)
        if difference != evaluation["mean_return_difference"]:
            raise GameLearningError(
                "policy_evaluation_invalid", "Measured mean return difference differs.", 503
            )
        worst = min(item["return_difference"] for item in episodes)
        minimum = request.get("min_improvement", 0)
        regression = request.get("max_worst_seed_regression", 0)
        evidence = {
            "schema_version": "skeleton.game.policy_acceptance.v1",
            "policy_id": evaluation["policy_id"],
            "policy_digest": evaluation["policy_digest"],
            "evaluation_digest": evaluation["evaluation_digest"],
            "baseline": evaluation["baseline"],
            "heldout_seeds": evaluation["heldout_seeds"],
            "mean_return_difference": difference,
            "worst_seed_difference": worst,
            "thresholds": {
                "min_improvement": minimum,
                "max_worst_seed_regression": regression,
            },
            "meets_configured_return_gate": difference >= minimum and worst >= -regression,
            "strict_improvement": difference > 0,
            "interpretation": "Measured declared reward returns only; termination is not assumed to mean success.",
            "production_promotion_authorized": False,
        }
        evidence["acceptance_digest"] = _digest(evidence)
        return evidence

    async def _generate(self, scope, job, factory, cancelled):
        from skeleton.jeeves.game_learning_generation import GameGenerationRequest, generate_game_project
        from skeleton.jeeves.game_learning import GamePolicyLearner

        body = job["request"]
        policy, policy_environment = None, None
        try:
            policy_id = body.get("policy_id")
            if policy_id:
                saved = await self._admitted_policy(scope, job["project_id"], policy_id)
                if (
                    saved["snapshot"]["snapshot_digest"]
                    != job["input"]["generation_policy"]["snapshot_digest"]
                ):
                    raise GameLearningError(
                        "policy_identity_changed",
                        "Generation policy differs from its admitted snapshot.",
                        409,
                    )
                live_input = dict(saved["input"])
                current_head = await self._project(job["project_id"], scope)
                live_input["project_version"] = current_head["version"]
                live_input["input_epoch"] = current_head.get("_input_epoch", 0)
                policy_factory = await self._factory(scope, live_input)
                policy_environment = policy_factory()
                policy = GamePolicyLearner.from_snapshot(
                    saved["snapshot"], expected_spec=policy_environment.spec
                )
            source_features = []
            for source in job["input"]["sources"]:
                saved = await self.sources.find_one({"_id": source["source_id"], **scope})
                bundle = self._source_bundle(scope, saved)
                if bundle.bundle_digest != source["bundle_digest"]:
                    raise GameLearningError(
                        "source_bundle_changed", "Source features differ from the admitted job.", 409
                    )
                if saved["kind"] != "build_artifact":
                    source_features.append(bundle.to_dict())
            request = GameGenerationRequest(
                project_id=job["job_id"],
                title=body.get("title") or "Original learned game",
                engine_era=(await self._project(job["project_id"], scope))["engine_era"],
                hardware_target=job["input"]["console_id"],
                genre=body.get("genre") or "arcade_golden_age",
                seed=body.get("seed", 0),
                complexity=body.get("complexity", 2),
            )
            generated = await asyncio.to_thread(
                generate_game_project,
                request,
                policy=policy,
                source_features=source_features,
                policy_environment=policy_environment,
            )
            if cancelled.is_set():
                raise GameLearningError("job_cancelled", "Generation was cancelled.", 409)
            await self._authority(scope, job["input"])
            result = generated.as_dict(include_files=True)
            result["files"] = _files(
                [{"path": path, "content": content} for path, content in generated.tree.files.items()]
            )
            result.pop("file_contents", None)
            result["adoption"] = "Save these candidate files through the versioned editor to adopt them."
            return result

        finally:
            if policy_environment is not None:
                from skeleton.jeeves.game_learning_demonstrations import close_environment

                await asyncio.to_thread(close_environment, policy_environment)

    async def revoke_source(self, scope, project_id, source_id, expected_version):
        project = await self._project(project_id, scope, expected_version)
        if source_id not in project["source_ids"]:
            raise GameLearningError("source_not_found", "Source not found.", 404)
        source = await self.sources.find_one({"_id": source_id, **scope})
        await self._fence_jobs(scope, project_id)
        await self.sources.update_one(
            {"_id": source_id, **scope, "state": "active"},
            {
                "$set": {"state": "revoked", "rights_acknowledged": False, "revoked_at": _now()},
                "$inc": {"authority_epoch": 1},
            },
        )
        changed = await self.projects.update_one(
            {"_id": project_id, **scope, "version": expected_version},
            {
                "$inc": {"version": 1},
                "$set": {"updated_at": _now(), "policy_id": None},
                "$unset": self._editor_claim_fields(),
            },
        )
        await self.chunks.delete_many({**scope, "source_id": source_id})
        if source is not None and source["kind"] == "content_bundle":
            from core.game_content_uploads import content_uploads

            await content_uploads.withdraw_source(scope, source_id)
        if not changed.modified_count:
            raise GameLearningError(
                "project_conflict", "Project changed during revocation; source remains revoked.", 409
            )
        return await self.get_project(scope, project_id)

    async def export_project(self, scope, project_id, *, expected_version=None, generated_job_id=None):
        project = await self._project(project_id, scope, expected_version)
        binding = await self._input(scope, project, require_execution=False)
        await self._authority(scope, binding)
        files, generated = project["files"], None
        if generated_job_id:
            job = await self.jobs.find_one(
                {
                    "_id": generated_job_id,
                    **scope,
                    "project_id": project_id,
                    "kind": "generate",
                    "status": "completed",
                }
            )
            if job is None or generated_job_id not in project["job_ids"]:
                raise GameLearningError("generated_project_not_found", "Generated candidate not found.", 404)
            await self._authority(scope, job["input"])
            files, generated = job["result"]["files"], job["result"]["manifest"]
        sources = (
            await self.sources.find(
                {**scope, "project_id": project_id, "source_id": {"$in": project["source_ids"]}}
            )
            .limit(64)
            .to_list(length=64)
        )
        content = {
            "schema_version": "skeleton.game_learning.export.v1",
            "project_id": project_id,
            "snapshot_version": project["version"],
            "name": project["name"],
            "console_id": project["console_id"],
            "files": files,
            "sources": [
                {
                    key: row.get(key)
                    for key in (
                        "source_id",
                        "source_digest",
                        "kind",
                        "filename",
                        "rights_refs",
                        "state",
                        "authority_epoch",
                    )
                }
                for row in sources
            ],
            "generated_manifest": generated,
            "raw_source_bytes_included": False,
            "production_promotion_authorized": False,
        }
        encoded = _json(content, MAX_JSON)
        await self._authority(scope, binding)
        return {
            "project_id": project_id,
            "snapshot_version": project["version"],
            "filename": "game-project-" + project_id + ".json",
            "media_type": "application/json",
            "content": encoded.decode(),
            "content_digest": hashlib.sha256(encoded).hexdigest(),
        }

    def register_job_handler(self, kind, handler, *, input_hook=None):
        if kind not in {
            "build",
            "successor",
            "successor_compare",
            "desktop",
            "studio_learning",
            "review",
        } or not callable(handler):
            raise GameLearningError("job_handler_undeclared", "Job handler is not declared by construction.")
        if not hasattr(self, "_job_handlers"):
            self._job_handlers = {}
        previous = self._job_handlers.get(kind)
        if previous is not None and previous is not handler:
            raise GameLearningError("job_handler_conflict", "A different handler already owns this job kind.")
        self._job_handlers[kind] = handler
        if input_hook is not None:
            if not callable(input_hook):
                raise GameLearningError("job_input_hook_invalid", "Job admission hook must be callable.")
            if not hasattr(self, "_job_input_hooks"):
                self._job_input_hooks = {}
            prior = self._job_input_hooks.get(kind)
            if prior is not None and prior is not input_hook:
                raise GameLearningError(
                    "job_input_hook_conflict", "Job input admission already has an owner."
                )
            self._job_input_hooks[kind] = input_hook

    async def register_content_source(self, scope, project_id, manifest, source_id, expected_version):
        from skeleton.jeeves.game_emulator_catalog import GameContentBundle

        project = await self._project(project_id, scope)
        descriptor = GameContentBundle.from_descriptor(manifest["descriptor"])
        if (
            descriptor.bundle_digest != manifest["content_digest"]
            or manifest.get("rights_acknowledged") is not True
            or not manifest.get("rights_refs")
        ):
            raise GameLearningError(
                "content_manifest_invalid", "Content identity and explicit rights are required.", 403
            )
        existing = await self.sources.find_one({"_id": source_id, **scope})
        if existing is not None:
            if existing["source_digest"] != descriptor.bundle_digest:
                raise GameLearningError(
                    "content_identity_conflict", "Content source already binds another bundle.", 409
                )
            if (
                existing.get("state") != "active"
                or existing.get("rights_refs") != manifest["rights_refs"]
                or existing.get("content_manifest") != manifest
            ):
                raise GameLearningError(
                    "content_authority_conflict",
                    "Content source was withdrawn or its exact manifest changed.",
                    409,
                )
            if source_id in project["source_ids"]:
                return await self.get_project(scope, project_id), _public(existing)
        await self._project(project_id, scope, expected_version)
        if len(project["source_ids"]) >= 64:
            raise GameLearningError("source_limit", "Project source limit is reached.", 413)
        doc = {
            "_id": source_id,
            **scope,
            "project_id": project_id,
            "source_id": source_id,
            "kind": "content_bundle",
            "filename": manifest["entrypoint"],
            "bundle_id": manifest["bundle_id"],
            "source_digest": descriptor.bundle_digest,
            "byte_length": manifest["byte_length"],
            "authority_epoch": 0,
            "rights_refs": manifest["rights_refs"],
            "rights_acknowledged": True,
            "state": "active",
            "created_at": _now(),
            "metadata": {
                "files": [
                    {key: item[key] for key in ("path", "bytes", "sha256")} for item in manifest["files"]
                ],
                "entrypoint": manifest["entrypoint"],
            },
            "content_manifest": manifest,
            "bundle": {"bundle_digest": descriptor.bundle_digest},
        }
        _json(manifest, 6 * 1024 * 1024)
        await self._admit(scope, "game-learning-content-source", source_id, len(_json(manifest)) + 4096)
        await self.sources.update_one({"_id": source_id}, {"$setOnInsert": doc}, upsert=True)
        await self._fence_jobs(scope, project_id)
        result = await self.projects.update_one(
            {"_id": project_id, **scope, "version": expected_version, "source_ids": {"$ne": source_id}},
            {
                "$push": {"source_ids": source_id},
                "$inc": {"version": 1},
                "$set": {"default_source_id": source_id, "updated_at": _now()},
                "$unset": self._editor_claim_fields(),
            },
        )
        if not result.modified_count:
            raise GameLearningError(
                "project_conflict", "Project changed during content source admission.", 409
            )
        return await self.get_project(scope, project_id), _public(doc)

    async def environment_request(self, scope, binding):
        from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
        from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry
        from core.game_console_build import artifact_native_observation

        project = await self._authority(scope, binding)
        frozen_files = binding.get("files", project["files"])
        tree = {item["path"]: item["content"] for item in frozen_files}
        source_id = binding.get("source_id")
        selected_source = (
            await self.sources.find_one(
                {"_id": source_id, **scope, "project_id": project["project_id"], "state": "active"}
            )
            if source_id
            else None
        )
        compiled = selected_source is not None and selected_source["kind"] == "build_artifact"
        if binding.get("execution_selection") == "compiled_artifact" and not compiled:
            raise GameLearningError(
                "compiled_source_unavailable", "Selected compiled source is unavailable.", 403
            )
        authored_kind = self.authored_environment_kind(tree)
        if authored_kind and not compiled:
            return GameEnvironmentRequest(
                binding["console_id"],
                kind=authored_kind,
                tree=self.authored_runtime_tree(tree, authored_kind),
                max_steps=binding["episode_steps"],
            ).as_dict()
        generated = "game/generated/game.json" in tree and not compiled
        rom, content, filename = None, None, "game.bin"
        source_id = binding.get("source_id")
        if source_id is not None and not generated:
            source = await self.sources.find_one(
                {"_id": source_id, **scope, "state": "active", "rights_acknowledged": True}
            )
            if source is None:
                raise GameLearningError(
                    "source_authority_unavailable", "Selected content is unavailable.", 403
                )
            filename = source["filename"]
            if source["kind"] == "content_bundle":
                from core.game_content_uploads import materialize_content

                content = await materialize_content(scope, project["project_id"], source["bundle_id"])
            elif source["kind"] == "build_artifact":
                _, payload = await self._source_bytes(scope, project, source_id)
                content = await asyncio.to_thread(
                    self._materialize_cartridge, scope, project["project_id"], source, payload
                )
            elif source["kind"] == "rom":
                _, rom = await self._source_bytes(scope, project, source_id)
                if len(rom) > 2 * 1024 * 1024:
                    content = await asyncio.to_thread(
                        self._materialize_cartridge, scope, project["project_id"], source, rom
                    )
                    rom = None
        if not generated and (content is not None or rom is not None):
            registry = GameEmulatorRegistry.from_environment()
            target_id = binding["console_id"].removeprefix("dragon_native:").removeprefix("emulator:")
            try:
                pin = binding.get("emulator_binding")
                if pin is not None:
                    if registry.registry_digest != pin["registry_digest"]:
                        raise GameLearningError(
                            "emulator_registry_changed",
                            "Approved emulator configuration changed; start a new operation.",
                            409,
                        )
                    core = registry.resolve_core(pin["core_id"])
                    if target_id not in core.target_ids:
                        raise GameLearningError(
                            "emulator_target_changed", "Approved core no longer covers this hardware.", 409
                        )
                else:
                    core = registry.resolve(target_id)
            except ValueError:
                if content is not None or binding["console_id"] != "game_boy":
                    raise GameLearningError(
                        "emulator_unavailable",
                        "Install and approve a compatible local core for this content.",
                        409,
                    ) from None
            else:
                binding["emulator_binding"] = {
                    "core_id": core.core_id,
                    "registry_digest": registry.registry_digest,
                }
                request = GameEnvironmentRequest(
                    target_id=target_id,
                    max_steps=binding["episode_steps"],
                    kind="libretro",
                    core_id=core.core_id,
                    registry_digest=registry.registry_digest,
                    content=content,
                    rom_source=rom,
                    filename=filename,
                    native_observation=(
                        await artifact_native_observation(scope, selected_source) if compiled else None
                    ),
                )
                return request.as_dict()
        request = GameEnvironmentRequest(
            target_id=binding["console_id"],
            max_steps=binding["episode_steps"],
            tree=tree or None,
            rom_source=rom,
            gameplay_dialect=_manifest_dialect(frozen_files),
        )
        return request.as_dict()

    @staticmethod
    def authored_environment_kind(tree):
        if "game/successor/spec.json" in tree:
            return "successor"
        if "game/editor/console.json" in tree:
            return "console_editor"
        return None

    @staticmethod
    def authored_runtime_tree(tree, kind):
        if kind == "console_editor":
            from skeleton.jeeves.game_console_editor import file_manifest_digest

            return {
                **(
                    {"game/editor/graph.json": tree["game/editor/graph.json"]}
                    if "game/editor/graph.json" in tree
                    else {}
                ),
                "game/editor/console.json": tree["game/editor/console.json"],
                "game/editor/source_manifest.json": _json(
                    {
                        "schema_version": "skeleton.console_editor_source_identity.v1",
                        "manifest_digest": file_manifest_digest(tree),
                    }
                ).decode(),
            }
        return {"game/successor/spec.json": tree["game/successor/spec.json"]}

    @staticmethod
    def _materialize_cartridge(scope, project_id, source, payload):
        import os
        import tempfile
        import stat
        from pathlib import Path

        root = Path(tempfile.gettempdir()) / "skeleton-game-cartridges"
        root.mkdir(mode=0o700, exist_ok=True)
        if root.is_symlink() or root.stat().st_uid != os.getuid():
            raise GameLearningError("private_content_root", "Private content storage is unavailable.", 503)
        identity = _digest(
            {
                **scope,
                "project_id": project_id,
                "source_id": source["source_id"],
                "epoch": source["authority_epoch"],
                "digest": source["source_digest"],
            }
        )
        directory = root / identity
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.is_symlink() or directory.stat().st_uid != os.getuid():
            raise GameLearningError("private_content_root", "Private content storage is unavailable.", 503)
        filename = Path(source["filename"]).name
        target = directory / filename
        if target.exists():
            descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as reader:
                info = os.fstat(reader.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_size != len(payload)
                    or hashlib.sha256(reader.read(len(payload) + 1)).hexdigest() != source["source_digest"]
                ):
                    raise GameLearningError(
                        "private_content_changed", "Private cartridge identity changed.", 503
                    )
        else:
            descriptor, temporary = tempfile.mkstemp(prefix=".prepare-", dir=directory)
            try:
                with os.fdopen(descriptor, "wb") as writer:
                    writer.write(payload)
                    writer.flush()
                    os.fsync(writer.fileno())
                os.chmod(temporary, 0o400)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return {
            "root": str(directory),
            "entrypoint": filename,
            "files": [{"path": filename, "bytes": len(payload), "sha256": source["source_digest"]}],
            "content_digest": source["source_digest"],
            "bundle_id": source["source_id"],
        }

    async def _content_authority(self, scope, project_id, source):
        from core.game_content_uploads import assert_content_authority

        await assert_content_authority(scope, project_id, source["bundle_id"], source["source_digest"])

    async def _demonstration_authority(
        self, scope, binding, *, dragon_guarded=False, allowed_editor_operation_id=None
    ):
        from skeleton.jeeves.game_learning_demonstrations import GameDemonstration

        records = []
        references = binding.get("inherited_demonstrations", []) + binding.get("demonstrations", [])
        for reference in references:
            row = await self.database["game_learning_recordings"].find_one(
                {
                    "_id": reference["recording_id"],
                    **scope,
                    "project_id": binding["project_id"],
                    "status": "completed",
                    "consent": True,
                }
            )
            if row is None:
                raise GameLearningError(
                    "demonstration_consent_withdrawn",
                    "Recording is unavailable or its consent was withdrawn.",
                    403,
                )
            demo = GameDemonstration.from_dict(self._stored_evidence(row["demonstration"]))
            if (
                demo.digest != reference["demonstration_digest"]
                or row["input"]["tree_digest"] != binding["tree_digest"]
            ):
                raise GameLearningError(
                    "demonstration_identity_changed", "Recording identity or executable source changed.", 409
                )
            for expected in row["input"]["sources"]:
                source = await self.sources.find_one(
                    {"_id": expected["source_id"], **scope, "state": "active", "rights_acknowledged": True}
                )
                if source is None or any(
                    source[key] != expected[key] for key in ("source_digest", "authority_epoch")
                ):
                    raise GameLearningError(
                        "demonstration_source_withdrawn", "Recording source authority changed.", 403
                    )
                if source["kind"] == "build_artifact":
                    from core.game_console_build import assert_artifact_source

                    await assert_artifact_source(scope, source, dragon_guarded=dragon_guarded)
            await self._external_authority(
                scope,
                {"derived_sources": row["input"].get("derived_sources", [])},
                dragon_guarded=dragon_guarded,
                allowed_editor_operation_id=allowed_editor_operation_id,
            )
            if reference in binding.get("demonstrations", []):
                records.append(demo.as_dict())
        _json(records)
        return records

    async def emit_job_event(self, scope, job, token, payload):
        from core.game_learning_events import frame_hub

        live = await self.jobs.find_one(
            {
                "_id": job["job_id"],
                **scope,
                "status": "running",
                "worker_token": token,
                "cancel_requested": False,
                "input_changed": False,
                "lease_until": {"$gt": _now()},
            }
        )
        if live is None:
            raise GameLearningError("job_frame_fenced", "The actor no longer owns this job.", 409)
        await self._authority(scope, job["input"])
        stream_id = live["frame_stream_id"]
        instance = str(
            payload.get("instance_id") or payload.get("actor_id") or payload.get("actor_index") or "build"
        )
        event = frame_hub.publish(
            "job:" + job["job_id"],
            stream_id,
            {**payload, "job_id": job["job_id"], "instance_id": instance},
            event="frame" if payload.get("type") == "frame" else "log",
        )
        await self.database["game_learning_live_frames"].update_one(
            {"_id": "job:" + job["job_id"] + ":" + instance},
            {
                "$set": {
                    **scope,
                    "project_id": job["project_id"],
                    "job_id": job["job_id"],
                    "instance_id": instance,
                    "stream_id": stream_id,
                    "event": event,
                    "instance_status": "running",
                    "expires_at": _now() + timedelta(seconds=30),
                }
            },
            upsert=True,
        )

    async def job_instances(self, scope, job_id):
        job = await self.get_job(scope, job_id)
        raw = await self.jobs.find_one({"_id": job_id, **scope})
        await self._authority(scope, raw["input"])
        rows = (
            await self.database["game_learning_live_frames"]
            .find(
                {
                    **scope,
                    "job_id": job_id,
                    "stream_id": raw.get("frame_stream_id"),
                    "expires_at": {"$gt": _now()},
                }
            )
            .limit(8)
            .to_list(length=8)
        )
        instances = []
        for row in rows:
            frame = row["event"]["payload"]
            instances.append(
                {
                    "instance_id": row["instance_id"],
                    "job_id": job_id,
                    "status": row.get(
                        "instance_status", "running" if job["status"] == "running" else "stopped"
                    ),
                    "controller": "ai",
                    "frame_sequence": row["event"]["sequence"],
                    "latest_frame": frame.get("frame"),
                    "observation": frame.get("observation"),
                    "steps": frame.get("step"),
                    "reward": frame.get("reward"),
                    "episode": frame.get("episode_id"),
                    "worker": frame.get("actor_pid"),
                    "policy_digest": frame.get("policy_digest"),
                    "stream_id": row["stream_id"],
                }
            )
        return {
            "job_id": job_id,
            "instances": instances,
            "status": job["status"],
            "job_status": job["status"],
            "stream_id": raw.get("frame_stream_id"),
        }


workspace = GameLearningWorkspace()
