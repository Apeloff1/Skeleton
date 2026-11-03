"""Compose preflight is read-only, bounded and never a readiness certificate."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.app.compose_guarded_preflight import (
    SCHEMA, inspect_compose_mongo_epoch, _run_from_environment,
)
from skeleton.persistence.mongo_source_epoch import MongoSourceEpochError


class FakeDB:
    def __init__(self):
        self.hello = {"setName": "rs0", "isWritablePrimary": True}
        self.calls = 0
        self.error = None

    async def command(self, name):
        self.calls += 1
        if self.error:
            raise self.error
        return self.hello


class FakeEpoch:
    instances = []

    def __init__(self, db):
        self.db = db
        self.calls = 0
        self.error = None
        self.__class__.instances.append(self)

    async def read_epoch(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return 2


class ComposePreflightTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeDB()
        FakeEpoch.instances.clear()
        self.patcher = patch(
            "skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch",
            FakeEpoch,
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    async def inspect(self, **changes):
        values = dict(tenant_id="tenant", actor_id="owner", context_id="context")
        values.update(changes)
        return await inspect_compose_mongo_epoch(self.db, **values)

    async def test_primary_and_stable_epoch_only_prove_mongo_preflight(self):
        result = await self.inspect()
        self.assertEqual(result["schema_version"], SCHEMA)
        self.assertEqual(result["code"], "mongo_epoch_observed_only")
        self.assertTrue(result["mongo_replica_set_primary_observed"])
        self.assertTrue(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertFalse(result["activated_model_tokenizer_verified"])
        self.assertFalse(result["independent_reviewer_verified"])
        self.assertFalse(result["canonical_writer_inventory_verified"])
        self.assertFalse(result["writes_performed"])
        self.assertEqual(FakeEpoch.instances[0].calls, 1)

    async def test_standalone_is_unavailable(self):
        self.db.hello = {"isWritablePrimary": True}
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_replica_set_primary_required")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertEqual(FakeEpoch.instances, [])

    async def test_secondary_is_unavailable(self):
        self.db.hello["isWritablePrimary"] = False
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_replica_set_primary_required")

    async def test_hello_boolean_spoof_denied(self):
        self.db.hello["isWritablePrimary"] = 1
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_replica_set_primary_required")

    async def test_primary_probe_error_redacted(self):
        self.db.error = RuntimeError("mongo://user:secret@private")
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_primary_probe_unavailable")
        self.assertNotIn("secret", str(result))

    async def test_missing_actor_scope_skips_mongo(self):
        result = await self.inspect(actor_id="")
        self.assertEqual(result["code"], "operator_actor_scope_required")
        self.assertEqual(self.db.calls, 0)

    async def test_malformed_actor_scope_skips_mongo(self):
        for bad in (" tenant", "x\x00y", "\ud800", "x" * 513):
            with self.subTest(bad=repr(bad)):
                result = await self.inspect(tenant_id=bad)
                self.assertEqual(result["code"], "operator_actor_scope_required")
        self.assertEqual(self.db.calls, 0)

    async def test_epoch_failure_does_not_claim_ai_ready(self):
        class UnavailableEpoch(FakeEpoch):
            async def read_epoch(self, **kwargs):
                raise MongoSourceEpochError("secret owner state")
        with patch(
            "skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch",
            UnavailableEpoch,
        ):
            result = await self.inspect()
        self.assertEqual(result["code"], "canonical_actor_epoch_unavailable")
        self.assertTrue(result["mongo_replica_set_primary_observed"])
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertNotIn("secret", str(result))

    async def test_database_mismatch_denied_before_any_mongo_connection(self):
        with patch.dict("os.environ", {
            "MONGO_URL": "mongodb://secret:secret@mongo:27017",
            "DB_NAME": "tutolage",
            "SKL_CANONICAL_MONGO_DATABASE": "skeleton",
            "SKL_CANONICAL_TENANT_ID": "tenant",
            "SKL_CANONICAL_ACTOR_ID": "owner",
            "SKL_CANONICAL_CONTEXT_ID": "context",
        }):
            with patch("motor.motor_asyncio.AsyncIOMotorClient") as client:
                result = await _run_from_environment()
                client.assert_not_called()
        self.assertEqual(result["code"], "canonical_database_identity_mismatch")
        self.assertFalse(result["canonical_database_name_aligned_observed"])
        self.assertFalse(result["canonical_cluster_identity_verified"])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertNotIn("secret", str(result))

    async def test_missing_engine_database_denied_without_mongo(self):
        with patch.dict("os.environ", {
            "MONGO_URL": "mongodb://secret:secret@mongo:27017",
            "DB_NAME": "tutolage",
            "SKL_CANONICAL_MONGO_DATABASE": "",
            "SKL_CANONICAL_TENANT_ID": "tenant",
            "SKL_CANONICAL_ACTOR_ID": "owner",
            "SKL_CANONICAL_CONTEXT_ID": "context",
        }):
            with patch("motor.motor_asyncio.AsyncIOMotorClient") as client:
                result = await _run_from_environment()
                client.assert_not_called()
        self.assertEqual(result["code"], "canonical_engine_database_identity_required")

    async def test_malformed_engine_database_denied(self):
        for bad in ("mongo/db", "mongo\\db", "mongo:27017", " x", "x" * 64):
            with self.subTest(value=bad):
                with patch.dict("os.environ", {
                    "MONGO_URL": "mongodb://private",
                    "DB_NAME": "tutolage",
                    "SKL_CANONICAL_MONGO_DATABASE": bad,
                    "SKL_CANONICAL_TENANT_ID": "tenant",
                    "SKL_CANONICAL_ACTOR_ID": "owner",
                    "SKL_CANONICAL_CONTEXT_ID": "context",
                }):
                    result = await _run_from_environment()
                self.assertEqual(result["code"], "canonical_engine_database_identity_required")

    async def test_no_connection_settings_denies_before_client(self):
        with patch.dict("os.environ", {
            "MONGO_URL": "", "DB_NAME": "tutolage",
            "SKL_CANONICAL_TENANT_ID": "tenant",
            "SKL_CANONICAL_ACTOR_ID": "owner",
            "SKL_CANONICAL_CONTEXT_ID": "context",
        }):
            result = await _run_from_environment()
        self.assertEqual(result["code"], "mongo_connection_configuration_required")


if __name__ == "__main__":
    unittest.main()
