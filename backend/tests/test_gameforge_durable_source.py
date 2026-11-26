"""Original Forge receipts retain exact source and fail closed on uncertain work."""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import threading
import time
import unittest
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from core import game_console_build as forge
from core.game_learning import GameLearningError, GameLearningWorkspace, _digest
from routes import skeleton_gameforge as routes
from routes.gameforge_auth import get_current_user
from skeleton.forge.source_manifest import source_manifest


SCOPE = {"tenant_id": "tenant-one", "owner_id": "owner-one"}


def payload():
    files = {"project.godot": "config_version=5\n", "scripts/game.gd": "extends Node\n# café\n"}
    return {"succeeded": True, "files": files, "source_manifest": source_manifest(files), "forge": {"file_count": 2}}


def job():
    request = {"expected_version": 1, "idempotency_key": "build-one", "run": {"vision": "Original extraction"}, "timeout_seconds": 60}
    return {
        "job_id": "job-one", "project_id": "project-one", "kind": "forge_source",
        "status": "running", "worker_token": "worker-one", "request": request,
        "request_digest": _digest(request), "cancel_requested": False, "input_changed": False,
        "input": {"project_id": "project-one", "project_version": 1, "input_epoch": 0,
                  "console_id": "forge:godot", "forge_compiler_digest": "compiler-one", "sources": []},
    }


def prepared_fixture():
    work = job()
    artifact, build = forge._forge_archive(payload())
    issued = {"artifact_id": "artifact-one", **artifact.as_dict(), "download_path": "/owned/source"}
    result = {"state": "source_ready", "source_manifest": build["source_manifest"], "build": build, "artifacts": [issued]}
    prepared = {"request_digest": work["request_digest"], "compiler_digest": "compiler-one",
                "result": result, "result_digest": _digest(result)}
    record = {**issued, "source_id": "build:artifact-one", "job_id": work["job_id"],
              "project_id": work["project_id"], "chunk_count": 1, "input": work["input"]}
    chunk = {"index": 0, "payload": artifact.data, "digest": hashlib.sha256(artifact.data).hexdigest()}
    return work, prepared, record, chunk


def history_job(index, created_at):
    work = job()
    work.update(_id=f"job-{index:03d}", job_id=f"job-{index:03d}", created_at=created_at, **SCOPE)
    work["request"]["idempotency_key"] = f"request-{index:03d}"
    work["request_digest"] = _digest(work["request"])
    return work


class ArchiveTests(unittest.TestCase):
    def test_exact_unicode_source_and_stable_zip_metadata(self):
        first, build = forge._forge_archive(payload())
        second, _ = forge._forge_archive(payload())
        self.assertEqual(first.data, second.data)
        with zipfile.ZipFile(io.BytesIO(first.data)) as archive:
            self.assertEqual({name: archive.read(name).decode() for name in archive.namelist()}, payload()["files"])
            self.assertTrue(all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist()))
        self.assertNotIn("files", build)
        self.assertEqual(build["source_export"]["manifest_sha256"], source_manifest(payload()["files"])["sha256"])

    def test_unsealed_or_mismatched_manifest_never_exports(self):
        for bad in ({**payload(), "succeeded": False}, {**payload(), "source_manifest": {"sha256": "0" * 64}}):
            with self.assertRaises(GameLearningError):
                forge._forge_archive(bad)

    def test_portable_path_and_source_byte_limits(self):
        for name in ("../escape.gd", "/absolute.gd", "C:/device.gd", "folder/CON.txt", "a\\b.gd", "a/.hidden"):
            with self.subTest(name=name), self.assertRaises(GameLearningError):
                forge._forge_archive({**payload(), "files": {name: "text"}})
        with self.assertRaises(GameLearningError) as raised:
            forge._forge_archive({**payload(), "files": {"large.txt": "a" * (8 * 1024 * 1024 + 1)}})
        self.assertEqual(raised.exception.status, 413)

    def test_durable_boundary_rejects_host_execution_and_unknown_options(self):
        for run in ({"project_root": "/tmp/project"}, {"overwrite": True}, {"target": "python"},
                    {"playtest": "require"}, {"playtest": None}, {"include_files": False}, {"command": "anything"},
                    {"playable_content": True, "playable_archetype": "unregistered"}):
            with self.subTest(run=run), self.assertRaises(ValidationError):
                routes.ForgeBuildRequest(expected_version=1, idempotency_key="one", run=run)

    def test_receipt_requires_new_request_for_unresolved_dispatch(self):
        work = {**job(), "status": "interrupted", "_forge_dispatched": {"reserved": True}}
        receipt = forge._forge_receipt(work)
        self.assertFalse(receipt["resume_available"])
        self.assertEqual(receipt["recovery"], "new_request_required")
        self.assertEqual(receipt["request_digest"], _digest(work["request"]))
        work["request"]["run"]["vision"] = "changed"
        with self.assertRaises(GameLearningError):
            forge._forge_receipt(work)


class AuthTests(unittest.TestCase):
    def test_anonymous_and_viewer_cannot_create_or_dispatch(self):
        app = FastAPI()
        app.include_router(routes.router)
        client = TestClient(app)
        for identity, expected in ((None, 401), ({"email": "viewer@example.test", "role": "viewer"}, 403)):
            app.dependency_overrides[get_current_user] = lambda: identity
            with patch.object(routes.workspace, "create_project", AsyncMock()) as create:
                response = client.post("/api/skeleton/projects", json={"name": "Mine", "idempotency_key": "one"})
                self.assertEqual(response.status_code, expected)
                create.assert_not_awaited()
            with patch.object(routes.workspace, "start_job", AsyncMock()) as start:
                response = client.post("/api/skeleton/projects/project-one/builds", json={"expected_version": 1, "idempotency_key": "one", "run": {}})
                self.assertEqual(response.status_code, expected)
                start.assert_not_awaited()

    def test_cancel_checks_ownership_without_scheduling(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_current_user] = lambda: {"email": "owner@example.test", "role": "editor"}
        with patch.object(routes, "get_forge_build", AsyncMock(return_value={"status": "cancelled"})) as read, \
             patch.object(routes.workspace, "cancel_job", AsyncMock()) as cancel:
            response = TestClient(app).post("/api/skeleton/projects/project-one/builds/job-one/cancel")
        self.assertEqual(response.status_code, 200)
        self.assertIs(read.await_args_list[0].kwargs["schedule"], False)
        self.assertEqual(cancel.await_args.args[0]["owner_id"], "owner@example.test")

    def test_history_query_is_bounded_before_storage_access(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_current_user] = lambda: {"email": "owner@example.test", "role": "editor"}
        for params in ({"limit": 0}, {"limit": 25}, {"limit": "not-a-count"},
                       {"before": "../invalid"}, {"before": "x" * 129}, {"before": ""}):
            with self.subTest(params=params), patch.object(routes, "list_forge_builds", AsyncMock()) as listing:
                response = TestClient(app).get("/api/skeleton/projects/project-one/builds", params=params)
                self.assertEqual(response.status_code, 422)
                listing.assert_not_awaited()

    def test_all_private_source_success_responses_disable_caching(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_current_user] = lambda: {"email": "owner@example.test", "role": "editor"}
        with patch.object(routes, "list_forge_projects", AsyncMock(return_value=[])), \
             patch.object(routes, "get_forge_project", AsyncMock(return_value={"project": {}, "builds": []})), \
             patch.object(routes, "list_forge_builds", AsyncMock(return_value={"builds": [], "next_cursor": None})), \
             patch.object(routes, "get_forge_build", AsyncMock(return_value={})), \
             patch.object(routes, "resume_forge_build", AsyncMock(return_value={})), \
             patch.object(routes.workspace, "create_project", AsyncMock(return_value={})), \
             patch.object(routes.workspace, "start_job", AsyncMock(return_value={})), \
             patch.object(routes.workspace, "cancel_job", AsyncMock(return_value={})):
            client = TestClient(app)
            for path in ("/projects", "/projects/project-one", "/projects/project-one/builds", "/projects/project-one/builds/job-one"):
                response = client.get("/api/skeleton" + path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "private, no-store")
                self.assertEqual(response.headers["vary"], "Authorization")
            for path, body in (
                ("/projects", {"name": "Mine", "idempotency_key": "one"}),
                ("/projects/project-one/builds", {"expected_version": 1, "idempotency_key": "one", "run": {}}),
                ("/projects/project-one/builds/job-one/cancel", {}),
                ("/projects/project-one/builds/job-one/resume", {}),
            ):
                response = client.post("/api/skeleton" + path, json=body)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "private, no-store")
                self.assertEqual(response.headers["vary"], "Authorization")
            public = client.get("/api/skeleton/eras")
            self.assertEqual(public.status_code, 200)
            self.assertNotIn("no-store", public.headers.get("cache-control", ""))


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, rows=(), *, boundary=None):
        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = AsyncMock(return_value=list(rows))
        workspace = SimpleNamespace(
            _project=AsyncMock(return_value={"console_id": "forge:godot", "job_ids": [f"job-{index:03d}" for index in range(60)]}),
            jobs=SimpleNamespace(find=MagicMock(return_value=cursor), find_one=AsyncMock(return_value=boundary)),
            _job_public=GameLearningWorkspace._job_public, _tasks={},
            _recover_jobs=AsyncMock(), _schedule_queued=AsyncMock(),
        )
        return workspace, cursor

    async def test_history_tiebreak_cursor_is_scoped_and_never_schedules(self):
        stamp = datetime(2026, 11, 20, tzinfo=timezone.utc)
        rows = [history_job(index, stamp) for index in range(30, 4, -1)]
        workspace, cursor = self.fixture(rows, boundary=history_job(31, stamp))
        with patch.object(forge, "workspace", workspace):
            result = await forge.list_forge_builds(SCOPE, "project-one", before="job-031", limit=24)
        self.assertEqual(len(result["builds"]), 24)
        self.assertEqual(result["next_cursor"], "job-007")
        self.assertEqual(workspace.jobs.find.call_args.args[0]["$or"], [
            {"created_at": {"$lt": stamp}}, {"created_at": stamp, "job_id": {"$lt": "job-031"}},
        ])
        cursor.sort.assert_called_once_with([("created_at", -1), ("job_id", -1)])
        cursor.limit.assert_called_once_with(25)
        self.assertEqual(workspace.jobs.find_one.await_args.args[0]["owner_id"], SCOPE["owner_id"])
        self.assertEqual(workspace.jobs.find_one.await_args.args[0]["kind"], "forge_source")
        workspace._recover_jobs.assert_not_awaited()
        workspace._schedule_queued.assert_not_awaited()

    async def test_empty_page_has_no_cursor(self):
        workspace, _ = self.fixture()
        with patch.object(forge, "workspace", workspace):
            self.assertEqual(await forge.list_forge_builds(SCOPE, "project-one"), {"builds": [], "next_cursor": None})
        workspace.jobs.find_one.assert_not_awaited()

    async def test_core_limits_and_malformed_cursor_cannot_reach_job_storage(self):
        for params in ({"limit": 0}, {"limit": 25}, {"limit": True}, {"limit": 1.5}, {"before": "../invalid"}):
            workspace, _ = self.fixture()
            with self.subTest(params=params), patch.object(forge, "workspace", workspace), self.assertRaises(GameLearningError) as raised:
                await forge.list_forge_builds(SCOPE, "project-one", **params)
            self.assertEqual(raised.exception.status, 422)
            workspace.jobs.find.assert_not_called()
            workspace.jobs.find_one.assert_not_awaited()

    async def test_foreign_or_unadmitted_cursor_fails_closed(self):
        workspace, _ = self.fixture()
        with patch.object(forge, "workspace", workspace), self.assertRaises(GameLearningError) as raised:
            await forge.list_forge_builds(SCOPE, "project-one", before="foreign-job")
        self.assertEqual(raised.exception.status, 404)
        query = workspace.jobs.find_one.await_args.args[0]
        self.assertEqual(query["project_id"], "project-one")
        self.assertEqual(query["tenant_id"], SCOPE["tenant_id"])
        self.assertIn("$in", query["job_id"])
        workspace.jobs.find.assert_not_called()

    async def test_corrupt_cursor_cannot_become_sort_authority(self):
        workspace, _ = self.fixture(boundary={"job_id": "job-001", "created_at": "untrusted"})
        with patch.object(forge, "workspace", workspace), self.assertRaises(GameLearningError) as raised:
            await forge.list_forge_builds(SCOPE, "project-one", before="job-001")
        self.assertEqual(raised.exception.status, 503)
        workspace.jobs.find.assert_not_called()


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def mocked_workspace(self, record, chunk):
        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = AsyncMock(return_value=[chunk])
        artifacts = SimpleNamespace(find_one=AsyncMock(return_value=record))
        return SimpleNamespace(
            _authority=AsyncMock(),
            _project=AsyncMock(return_value={"console_id": "forge:godot", "job_ids": ["job-one"]}),
            database={forge.ARTIFACT_COLLECTION: artifacts},
            chunks=SimpleNamespace(find=MagicMock(return_value=cursor)),
            jobs=SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))),
        )

    async def test_prepared_recovery_verifies_exact_bytes_without_recompiling(self):
        work, prepared, record, chunk = prepared_fixture()
        work["_forge_prepared"] = prepared
        with patch.object(forge, "workspace", self.mocked_workspace(record, chunk)), \
             patch.object(forge, "forge_compiler_digest", return_value="compiler-one"), \
             patch.object(forge, "_compile_forge_source") as compile:
            result = await forge.handle_forge_source(SCOPE, work, threading.Event(), AsyncMock())
        self.assertEqual(result, prepared["result"])
        compile.assert_not_called()

    async def test_corrupt_chunk_or_archive_manifest_cannot_recover(self):
        for corruption in ("chunk", "manifest"):
            work, prepared, record, chunk = prepared_fixture()
            if corruption == "chunk":
                chunk["payload"] = b"corrupted"
            else:
                prepared["result"]["source_manifest"]["sha256"] = "0" * 64
                prepared["result_digest"] = _digest(prepared["result"])
            with self.subTest(corruption=corruption), patch.object(forge, "workspace", self.mocked_workspace(record, chunk)):
                with self.assertRaises(GameLearningError) as raised:
                    await forge._verify_forge_prepared(SCOPE, work, prepared)
                self.assertEqual(raised.exception.status, 503)

    async def test_unknown_dispatch_or_changed_compiler_never_reexecutes(self):
        for digest, dispatched, expected in (("compiler-one", True, "forge_dispatch_unresolved"),
                                             ("compiler-two", False, "forge_compiler_changed")):
            work = job()
            if dispatched:
                work["_forge_dispatched"] = {"request_digest": work["request_digest"]}
            with patch.object(forge, "workspace", SimpleNamespace(_authority=AsyncMock())), \
                 patch.object(forge, "forge_compiler_digest", return_value=digest), \
                 patch.object(forge, "_compile_forge_source") as compile:
                with self.assertRaises(GameLearningError) as raised:
                    await forge.handle_forge_source(SCOPE, work, threading.Event(), AsyncMock())
                self.assertEqual(raised.exception.code, expected)
                compile.assert_not_called()

    async def test_timeout_retains_worker_until_actual_compiler_finishes(self):
        work = job()
        work["request"]["timeout_seconds"] = 0.005
        work["request_digest"] = _digest(work["request"])
        finished, cancelled = threading.Event(), threading.Event()

        def slow(_):
            time.sleep(0.04)
            finished.set()
            return forge._forge_archive(payload())

        workspace = SimpleNamespace(_authority=AsyncMock(), jobs=SimpleNamespace(
            update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))))
        with patch.object(forge, "workspace", workspace), \
             patch.object(forge, "forge_compiler_digest", return_value="compiler-one"), \
             patch.object(forge, "_compile_forge_source", side_effect=slow):
            with self.assertRaises(GameLearningError) as raised:
                await forge.handle_forge_source(SCOPE, work, cancelled, AsyncMock())
        self.assertEqual(raised.exception.code, "forge_build_timeout")
        self.assertTrue(finished.is_set())
        self.assertTrue(cancelled.is_set())
        self.assertEqual(workspace.jobs.update_one.await_count, 1)

    async def test_foreign_artifact_lookup_is_scoped_and_does_not_read_chunks(self):
        collection = SimpleNamespace(find_one=AsyncMock(return_value=None))
        workspace = SimpleNamespace(database={forge.ARTIFACT_COLLECTION: collection}, chunks=MagicMock())
        with patch.object(forge, "workspace", workspace), self.assertRaises(GameLearningError) as raised:
            await forge.download_build_artifact(SCOPE, "project-one", "unknown")
        self.assertEqual(raised.exception.status, 404)
        self.assertEqual(collection.find_one.await_args.args[0], {"_id": "unknown", **SCOPE, "project_id": "project-one"})
        workspace.chunks.find.assert_not_called()

    async def test_historical_original_source_does_not_weaken_console_authority(self):
        work = job()
        authority = AsyncMock(side_effect=GameLearningError("project_conflict", "Old console revision.", 409))
        workspace = SimpleNamespace(
            _project=AsyncMock(return_value={"console_id": "forge:godot", "version": 99, "job_ids": ["job-one"]}),
            _authority=authority,
        )
        with patch.object(forge, "workspace", workspace):
            self.assertEqual((await forge._artifact_authority(SCOPE, work))["version"], 99)
            authority.assert_not_awaited()
            with self.assertRaises(GameLearningError):
                await forge._artifact_authority(SCOPE, {**work, "kind": "build"})
            authority.assert_awaited_once()
            work["input"]["sources"] = [{"source_id": "acquired"}]
            with self.assertRaises(GameLearningError) as raised:
                await forge._artifact_authority(SCOPE, work)
            self.assertEqual(raised.exception.code, "forge_artifact_authority")

    async def test_repeated_cancellation_drains_actual_executor(self):
        work = job()
        started, finished, cancelled = threading.Event(), threading.Event(), threading.Event()

        def slow(_):
            started.set()
            time.sleep(0.05)
            finished.set()
            return forge._forge_archive(payload())

        workspace = SimpleNamespace(_authority=AsyncMock(), jobs=SimpleNamespace(
            update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))))
        with patch.object(forge, "workspace", workspace), \
             patch.object(forge, "forge_compiler_digest", return_value="compiler-one"), \
             patch.object(forge, "_compile_forge_source", side_effect=slow):
            task = asyncio.create_task(forge.handle_forge_source(SCOPE, work, cancelled, AsyncMock()))
            while not started.is_set():
                await asyncio.sleep(0.001)
            task.cancel()
            await asyncio.sleep(0.005)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(finished.is_set())
        self.assertTrue(cancelled.is_set())
        self.assertEqual(workspace.jobs.update_one.await_count, 1)


@unittest.skipUnless(os.environ.get("GAMEFORGE_TEST_MONGO_URI"), "Actual Mongo custody integration is opt-in")
class MongoCustodyTests(unittest.IsolatedAsyncioTestCase):
    """Actual Mongo/CAS/chunks; admission is explicitly a test-only fixture."""

    async def test_actual_mongo_history_reaches_all_pages_and_rejects_foreign_cursors(self):
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(os.environ["GAMEFORGE_TEST_MONGO_URI"], serverSelectionTimeoutMS=5000)
        database = client["forge_history_test_" + uuid4().hex]
        workspace = GameLearningWorkspace(database)
        stamp = datetime(2026, 11, 20, tzinfo=timezone.utc)
        rows = [history_job(index, stamp) for index in range(51)]
        foreign = {**history_job(60, stamp), "_id": "foreign-job", "job_id": "foreign-job", "owner_id": "other-owner"}
        other_project = {**history_job(61, stamp), "_id": "other-project-job", "job_id": "other-project-job", "project_id": "other-project"}
        other_kind = {**history_job(62, stamp), "_id": "other-kind-job", "job_id": "other-kind-job", "kind": "build"}
        orphan = {**history_job(63, stamp), "_id": "orphan-job", "job_id": "orphan-job"}
        try:
            await workspace.projects.insert_one({
                "_id": "project-one", **SCOPE, "project_id": "project-one", "console_id": "forge:godot", "state": "active", "version": 1,
                "job_ids": [row["job_id"] for row in rows] + ["foreign-job", "other-project-job", "other-kind-job"],
            })
            await workspace.jobs.insert_many(rows + [foreign, other_project, other_kind, orphan])
            with patch.object(forge, "workspace", workspace), \
                 patch.object(workspace, "_recover_jobs", AsyncMock()) as recover, \
                 patch.object(workspace, "_schedule_queued", AsyncMock()) as schedule:
                first = await forge.list_forge_builds(SCOPE, "project-one", limit=24)
                self.assertEqual([row["job_id"] for row in first["builds"]], [f"job-{index:03d}" for index in range(50, 26, -1)])
                self.assertEqual(first["next_cursor"], "job-027")
                # A newly submitted build cannot shift the older page boundary.
                newest = history_job(64, datetime(2027, 1, 1, tzinfo=timezone.utc))
                await workspace.jobs.insert_one(newest)
                await workspace.projects.update_one({"_id": "project-one"}, {"$push": {"job_ids": newest["job_id"]}})
                second = await forge.list_forge_builds(SCOPE, "project-one", before=first["next_cursor"], limit=24)
                third = await forge.list_forge_builds(SCOPE, "project-one", before=second["next_cursor"], limit=24)
                self.assertEqual(len(second["builds"]), 24)
                self.assertEqual(len(third["builds"]), 3)
                self.assertIsNone(third["next_cursor"])
                ids = [row["job_id"] for page in (first, second, third) for row in page["builds"]]
                self.assertEqual(ids, [f"job-{index:03d}" for index in range(50, -1, -1)])
                self.assertEqual(len(set(ids)), 51)
                for before in ("foreign-job", "other-project-job", "other-kind-job", "orphan-job", "missing-job"):
                    with self.subTest(before=before), self.assertRaises(GameLearningError) as denied:
                        await forge.list_forge_builds(SCOPE, "project-one", before=before)
                    self.assertEqual(denied.exception.status, 404)
                recover.assert_not_awaited()
                schedule.assert_not_awaited()
        finally:
            await client.drop_database(database.name)
            client.close()

    async def test_real_mongo_custody_reopen_recovery_and_historical_download(self):
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(os.environ["GAMEFORGE_TEST_MONGO_URI"], serverSelectionTimeoutMS=5000)
        database = client["forge_source_test_" + uuid4().hex]
        workspaces, admissions = [], []

        async def test_only_admission(scope, resource, write_id, size):
            admissions.append((resource, size))
            return {"storage_bytes": size, "test_only_admission_fixture": True}

        def reopened_workspace():
            workspace = GameLearningWorkspace(database)
            workspace._admit = test_only_admission
            workspace.register_job_handler("forge_source", forge.handle_forge_source, input_hook=forge._forge_input)
            workspaces.append(workspace)
            return workspace

        async def terminal(workspace, job_id, expected="completed"):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                row = await workspace.jobs.find_one({"_id": job_id, **SCOPE})
                if row["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                    self.assertEqual(row["status"], expected, row.get("error"))
                    while workspace._tasks:
                        await asyncio.sleep(0.01)
                    return row
                await asyncio.sleep(0.025)
            self.fail("Actual Mongo build did not reach a terminal state")

        try:
            first = reopened_workspace()
            with patch.object(forge, "workspace", first):
                project = await first.create_project(SCOPE, {"name": "Original Forge", "console_id": "forge:godot", "idempotency_key": "project-one"}, initial_files=[], source_only=True)
                request = routes.ForgeBuildRequest(expected_version=1, idempotency_key="build-one", run={
                    "vision": "A tense original extraction game with scarce fuel and safe exits",
                    "era": "extraction_now", "playable_content": True,
                    "playable_archetype": "extraction", "playable_main_scene": True,
                }).model_dump(exclude_none=True)
                with patch.object(forge, "_compile_forge_source", wraps=forge._compile_forge_source) as compile:
                    queued = await asyncio.gather(*(first.start_job(SCOPE, project["project_id"], "forge_source", request) for _ in range(2)))
                    self.assertEqual(queued[0]["job_id"], queued[1]["job_id"])
                    issued = await terminal(first, queued[0]["job_id"])
                    self.assertEqual(compile.call_count, 1)
                artifact_id = issued["result"]["artifacts"][0]["artifact_id"]
                _, original, digest = await forge.download_build_artifact(SCOPE, project["project_id"], artifact_id)
                self.assertEqual(hashlib.sha256(original).hexdigest(), digest)
                self.assertEqual((await forge.get_forge_project(SCOPE, project["project_id"]))["builds"][0]["brief"], request["run"])
                with self.assertRaises(GameLearningError) as conflict:
                    await first.start_job(SCOPE, project["project_id"], "forge_source", {**request, "run": {**request["run"], "vision": "Changed"}})
                self.assertEqual(conflict.exception.status, 409)
                with self.assertRaises(GameLearningError) as denied:
                    await forge.download_build_artifact({**SCOPE, "owner_id": "other-owner"}, project["project_id"], artifact_id)
                self.assertEqual(denied.exception.status, 404)
                # Inject storage failure at the actual terminal boundary of a
                # second build. Its genuine preparation must remain resumable.
                recovering_request = {**request, "idempotency_key": "recover-one"}
                with patch.object(first, "_complete_job", AsyncMock(side_effect=PyMongoError("Injected terminal storage failure"))):
                    pending = await first.start_job(SCOPE, project["project_id"], "forge_source", recovering_request)
                    interrupted = await terminal(first, pending["job_id"], "interrupted")
                self.assertIn("_forge_prepared", interrupted)
                self.assertNotIn("result", interrupted)
            reopened = reopened_workspace()
            with patch.object(forge, "workspace", reopened), patch.object(forge, "_compile_forge_source", side_effect=AssertionError("Prepared recovery must not recompile")) as compile:
                await forge.resume_forge_build(SCOPE, project["project_id"], interrupted["job_id"])
                recovered = await terminal(reopened, interrupted["job_id"])
                self.assertEqual(recovered["result"], interrupted["_forge_prepared"]["result"])
                compile.assert_not_called()
                await reopened.save_editor(SCOPE, project["project_id"], {
                    "expected_version": 1, "idempotency_key": "later-revision",
                    "files": [{"path": "notes.txt", "content": "A later project revision"}],
                })
                _, historical, historical_digest = await forge.download_build_artifact(SCOPE, project["project_id"], artifact_id)
                self.assertEqual(historical, original)
                self.assertEqual(historical_digest, digest)
                record = await database[forge.ARTIFACT_COLLECTION].find_one({"_id": artifact_id})
                await reopened.chunks.update_one({"source_id": record["source_id"], "index": 0}, {"$set": {"payload": b"corrupted"}})
                with self.assertRaises(GameLearningError) as corrupt:
                    await forge.download_build_artifact(SCOPE, project["project_id"], artifact_id)
                self.assertEqual(corrupt.exception.status, 503)
            self.assertTrue(admissions)
        finally:
            for workspace in workspaces:
                tasks = list(workspace._tasks.values())
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            await client.drop_database(database.name)
            client.close()


if __name__ == "__main__":
    unittest.main()
