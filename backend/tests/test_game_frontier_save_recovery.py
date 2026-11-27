"""Actual Mongo authoring outcomes; only governed write admission is a fixture."""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient

from core import game_frontier_authoring as authoring
from core.game_learning import GameLearningWorkspace, GameLearningError, _digest, _json, _key, _now
from skeleton.forge.game_frontier_studio_authoring import apply_authoring_batch, project_digest
from skeleton.forge.game_frontier_studio_document import authored_document


class FrontierSaveRecoveryMongoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        config_path = Path(os.environ.get("SKL_TEST_MONGO_CONFIG", "/workspace/verticals-runtime/mongo.json"))
        if not config_path.is_file():
            self.skipTest("Actual authenticated disposable Mongo configuration is required")
        config = json.loads(config_path.read_text())
        self.client = AsyncIOMotorClient(config["uri"], serverSelectionTimeoutMS=5000)
        self.database_name = config["database_prefix"][:12] + "_frontier_" + uuid4().hex[:16]
        self.old_owner = authoring.workspace
        self.owner = GameLearningWorkspace(self.client[self.database_name])
        authoring.workspace = self.owner
        self.addAsyncCleanup(self.cleanup)
        self.admissions = []

        async def test_only_admission(scope, resource, key, size):
            self.admissions.append({"resource": resource, "key": key, "bytes": size})
            return {"storage_bytes": size, "fixture": "governed-storage-admission-only"}

        self.owner._admit = test_only_admission
        self.scope = self.owner._scope("frontier-recovery", "frontier-owner@example.test")
        project = await self.owner.create_project(self.scope, {
            "name": "Original authoring outcomes", "console_id": "studio:economy", "idempotency_key": "create"})
        self.project_id = project["project_id"]
        self.owner_before, self.source_before = await authoring._source(self.scope, self.project_id)
        self.original_rows = await self.owner.revisions.count_documents({})
        self.body = {"expected_version": self.owner_before["version"],
                     "expected_sha256": project_digest(self.source_before), "idempotency_key": "original-save",
                     "steps": [{"action": "tile_set", "parameters": {"layer": "ground", "x": 2, "y": 3, "tile": 2}}]}

    async def cleanup(self):
        authoring.workspace = self.old_owner
        await self.client.drop_database(self.database_name)
        self.client.close()

    async def record(self, key=None):
        return await self.owner.revisions.find_one({"_id": _key(self.project_id, "editor", key or self.body["idempotency_key"]), **self.scope})

    async def head(self):
        return await self.owner._project(self.project_id, self.scope)

    async def prepare_only(self):
        with patch.object(self.owner, "_reserve_editor", side_effect=GameLearningError("fixture_stopped", "Stopped before publication.", 503)):
            with self.assertRaises(GameLearningError):
                await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        return await self.record()

    async def test_lost_commit_acknowledgement_recovers_once_without_readmission_or_step_replay(self):
        original_writer = self.owner.save_editor

        async def lost_ack(*args, **kwargs):
            await original_writer(*args, **kwargs)
            raise ConnectionError("Declared lost acknowledgement after actual source publication")

        with patch.object(self.owner, "save_editor", side_effect=lost_ack):
            with self.assertRaises(ConnectionError):
                await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        before = len(self.admissions)
        with patch.object(authoring, "apply_authoring_batch", side_effect=AssertionError("Committed recovery cannot rerun authoring")):
            recovered = await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        self.assertTrue(recovered["replayed"])
        self.assertEqual(recovered["request_id"], self.body["idempotency_key"])
        self.assertEqual(recovered["expected_version"], self.body["expected_version"] + 1)
        self.assertEqual(recovered["original_source_sha256"], self.body["expected_sha256"])
        self.assertEqual(len(self.admissions), before)
        self.assertEqual(await self.owner.revisions.count_documents({}), self.original_rows + 1)
        head = await self.head()
        self.assertEqual(head["version"], recovered["expected_version"])
        self.assertEqual(head["revision_ids"].count((await self.record())["_id"]), 1)

    async def test_recovery_after_a_later_edit_returns_the_original_result_not_the_current_candidate(self):
        first = await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        current = await authoring.document(self.scope, self.project_id)
        later = {"expected_version": current["expected_version"], "expected_sha256": current["source_sha256"],
                 "idempotency_key": "later-save", "steps": [{"action": "tile_set", "parameters": {
                     "layer": "ground", "x": 4, "y": 5, "tile": 1}}]}
        second = await authoring.edit(self.scope, self.project_id, later, preview=False)
        admissions = len(self.admissions)
        with patch.object(authoring, "apply_authoring_batch", side_effect=AssertionError("Do not regenerate a historical outcome")):
            recovered = await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        self.assertEqual(recovered["expected_version"], first["expected_version"])
        self.assertEqual(recovered["head_version"], second["expected_version"])
        self.assertEqual(recovered["source_sha256"], first["source_sha256"])
        self.assertNotEqual(recovered["source_sha256"], second["source_sha256"])
        self.assertEqual(recovered["batch_receipt"], first["batch_receipt"])
        self.assertEqual(len(self.admissions), admissions)

    async def test_equal_candidate_from_different_steps_cannot_reuse_the_original_key(self):
        first = await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        different = {**deepcopy(self.body), "steps": deepcopy(self.body["steps"] * 2)}
        candidate = apply_authoring_batch(self.source_before, different["steps"])["project"]
        self.assertEqual(project_digest(candidate), first["source_sha256"], "The mutation candidates intentionally coincide")
        with patch.object(authoring, "apply_authoring_batch", side_effect=AssertionError("Different intent must fail before replay")):
            with self.assertRaises(GameLearningError) as error:
                await authoring.edit(self.scope, self.project_id, different, preview=False)
        self.assertEqual(error.exception.code, "idempotency_conflict")
        self.assertEqual((await self.head())["version"], first["expected_version"])

    async def test_foreign_scope_and_changed_original_source_are_not_recovery_capabilities(self):
        await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        with self.assertRaises(GameLearningError) as error:
            await authoring.edit(self.owner._scope("foreign", "foreign@example.test"), self.project_id, self.body, preview=False)
        self.assertEqual(error.exception.status, 404)
        with self.assertRaises(GameLearningError) as error:
            await authoring.edit(self.scope, self.project_id, {**self.body, "expected_sha256": "a" * 64}, preview=False)
        self.assertEqual(error.exception.code, "idempotency_conflict")

    async def test_passive_prepared_read_does_not_complete_and_explicit_retry_uses_one_original_revision(self):
        prepared = await self.prepare_only()
        admissions = len(self.admissions)
        observed = await self.owner.editor_origin_receipt(self.scope, self.project_id,
                                                         self.body["idempotency_key"], prepared["_editor_origin"]["request_digest"])
        self.assertFalse(observed["committed"])
        self.assertEqual((await authoring.document(self.scope, self.project_id))["expected_version"], self.body["expected_version"])
        self.assertEqual(len(self.admissions), admissions)
        with patch.object(authoring, "apply_authoring_batch", side_effect=AssertionError("Resume only the sealed original candidate")):
            completed = await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        self.assertTrue(completed["replayed"])
        self.assertEqual(completed["expected_version"], self.body["expected_version"] + 1)
        self.assertEqual(await self.owner.revisions.count_documents({}), self.original_rows + 1)
        self.assertEqual((await self.record())["created_at"], prepared["created_at"])
        writes = [item for item in self.admissions if item["resource"] == "game-learning-revision"]
        self.assertEqual({item["key"] for item in writes}, {prepared["_id"]})

    async def test_original_fenced_resume_respects_live_lease_then_reuses_the_same_input_epoch(self):
        original_fence = self.owner._fence_jobs

        async def stop_after_fence(*args, **kwargs):
            await original_fence(*args, **kwargs)
            raise GameLearningError("fixture_fenced_stop", "Stopped after original fence.", 503)

        with patch.object(self.owner, "_fence_jobs", side_effect=stop_after_fence):
            with self.assertRaises(GameLearningError):
                await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        fenced = await self.head()
        with patch.object(authoring, "apply_authoring_batch", side_effect=AssertionError("Never rerun a prepared operation")):
            with self.assertRaises(GameLearningError) as error:
                await authoring.edit(self.scope, self.project_id, self.body, preview=False)
            self.assertEqual(error.exception.code, "editor_write_busy")
            await self.owner.projects.update_one({"_id": self.project_id, **self.scope},
                {"$set": {"_editor_write_until": _now() - timedelta(seconds=1)}})
            completed = await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        head = await self.head()
        self.assertEqual(head["version"], completed["expected_version"])
        self.assertEqual(head["_input_epoch"], fenced["_input_epoch"])
        self.assertEqual(head["revision_ids"].count((await self.record())["_id"]), 1)

    async def test_other_editor_lease_and_stale_prepared_head_never_allow_original_reapplication(self):
        prepared = await self.prepare_only()
        await self.owner.projects.update_one({"_id": self.project_id, **self.scope}, {"$set": {
            "_editor_write_operation_id": "different-original-operation", "_editor_write_token": "fixture-token",
            "_editor_write_phase": "fenced", "_editor_write_until": _now() + timedelta(minutes=1)}})
        with self.assertRaises(GameLearningError) as error:
            await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        self.assertEqual(error.exception.code, "editor_write_busy")
        await self.owner.projects.update_one({"_id": self.project_id, **self.scope}, {"$unset": self.owner._editor_claim_fields()})
        peer = {**deepcopy(self.body), "idempotency_key": "peer-editor", "steps": [{"action": "tile_set", "parameters": {
            "layer": "ground", "x": 0, "y": 1, "tile": 1}}]}
        await authoring.edit(self.scope, self.project_id, peer, preview=False)
        head = await self.head()
        self.assertNotIn(prepared["_id"], head["revision_ids"])
        admissions = len(self.admissions)
        with patch.object(authoring, "apply_authoring_batch", side_effect=AssertionError("A stale original cannot be reapplied")):
            with self.assertRaises(GameLearningError) as error:
                await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        self.assertEqual(error.exception.code, "editor_origin_stale")
        self.assertEqual((await self.head())["version"], head["version"])
        self.assertEqual(len(self.admissions), admissions)

    async def test_corrupt_or_ambiguous_receipts_never_become_success(self):
        await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        original = await self.record()
        for mutate in (lambda row: row.pop("_editor_origin"),
                       lambda row: row["_editor_origin"]["batch_receipt"].update(receipt_sha256="f" * 64),
                       lambda row: row["_editor_request_meta"].update(entrypoint="different/path.py"),
                       lambda row: row["files"][-1].update(content="{}")):
            row = deepcopy(original)
            mutate(row)
            await self.owner.revisions.replace_one({"_id": original["_id"], **self.scope}, row)
            with self.assertRaises(GameLearningError) as error:
                await authoring.edit(self.scope, self.project_id, self.body, preview=False)
            self.assertIn(error.exception.code, {"editor_origin_ambiguous", "editor_origin_corrupt"})
        await self.owner.revisions.replace_one({"_id": original["_id"], **self.scope}, original)
        self.assertEqual((await self.head())["version"], original["version"])

    async def test_legacy_editor_digest_admission_and_exact_retry_are_unchanged(self):
        project = await self.owner.get_project(self.scope, self.project_id)
        files = [{"path": item["path"], "content": item["content"]} for item in project["files"]]
        files[0]["content"] += "\n"
        legacy = {"expected_version": project["version"], "idempotency_key": "legacy-editor",
                  "entrypoint": project["entrypoint"], "files": files}
        await self.owner.save_editor(self.scope, self.project_id, legacy)
        stored = await self.record("legacy-editor")
        self.assertEqual(stored["request_digest"], _digest(legacy))
        self.assertNotIn("_editor_origin", stored)
        self.assertNotIn("_editor_request_meta", stored)
        self.assertEqual(self.admissions[-1]["bytes"], len(_json({"files": stored["files"]})))
        admissions = len(self.admissions)
        await self.owner.save_editor(self.scope, self.project_id, legacy)
        self.assertEqual(len(self.admissions), admissions)
        with self.assertRaises(GameLearningError) as error:
            await authoring.edit(self.scope, self.project_id, {**self.body, "idempotency_key": "legacy-editor"}, preview=False)
        self.assertEqual(error.exception.code, "editor_origin_ambiguous")

    async def test_origin_and_scalar_metadata_bytes_are_admitted_before_source_publication(self):
        await authoring.edit(self.scope, self.project_id, self.body, preview=False)
        stored = await self.record()
        expected = len(_json({"files": stored["files"], "_editor_origin": stored["_editor_origin"],
                              "_editor_request_meta": stored["_editor_request_meta"]}))
        write = next(item for item in self.admissions if item["key"] == stored["_id"])
        self.assertEqual(write["bytes"], expected)
        self.assertGreater(expected, len(_json({"files": stored["files"]})))

    async def test_internal_origin_cannot_attest_different_candidate_files_before_admission(self):
        intended = apply_authoring_batch(self.source_before, self.body["steps"])
        other = apply_authoring_batch(self.source_before, [{"action": "tile_set", "parameters": {
            "layer": "ground", "x": 2, "y": 3, "tile": 1}}])["project"]
        files = [{"path": item["path"], "content": item["content"]} for item in self.owner_before["files"]]
        files.append({"path": authoring.SOURCE_PATH, "content": authored_document(other)})
        origin = {"kind": "frontier_authoring.v1", "request_digest": _digest({"schema": "skeleton.forge.authoring-edit-request.v1",
                  "project_id": self.project_id, "request": self.body}), "source_sha256": self.body["expected_sha256"],
                  "candidate_sha256": project_digest(intended["project"]), "batch_receipt": intended["receipt"]}
        admissions = len(self.admissions)
        with self.assertRaises(GameLearningError) as error:
            await self.owner.save_editor(self.scope, self.project_id, {
                "expected_version": self.body["expected_version"], "idempotency_key": self.body["idempotency_key"],
                "files": files, "entrypoint": self.owner_before["entrypoint"]}, origin=origin)
        self.assertEqual(error.exception.code, "editor_origin_invalid")
        self.assertEqual(len(self.admissions), admissions)
        self.assertEqual((await self.head())["version"], self.body["expected_version"])
        self.assertEqual(await self.owner.revisions.count_documents({}), self.original_rows)


class ClosedPublicEditorInputs(unittest.TestCase):
    def test_internal_origin_is_not_a_public_editor_or_authoring_field(self):
        from pydantic import ValidationError
        from routes.game_learning import EditorRequest
        from routes.game_frontier_authoring import EditorMutation

        with self.assertRaises(ValidationError):
            EditorRequest.model_validate({"expected_version": 1, "idempotency_key": "key", "files": [], "origin": {}})
        with self.assertRaises(ValidationError):
            EditorMutation.model_validate({"expected_version": 1, "idempotency_key": "key", "expected_sha256": "a" * 64,
                                           "steps": [{"action": "tile_set", "parameters": {}}], "origin": {}})
