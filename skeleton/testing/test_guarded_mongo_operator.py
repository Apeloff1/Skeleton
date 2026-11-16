"""Deployed-source preflight: separate DBs, explicit witness, private scope."""
from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
import unittest

from bson.int64 import Int64
from bson.objectid import ObjectId

from skeleton.app.compose_guarded_preflight import (
    _authenticated_principals, _read_private_scope, _result, _run_from_environment,
    _trusted_topology,
)
from skeleton.app.compose_mongo_first_run_status import summarize_observation


class OperatorScopeTests(unittest.TestCase):
    def test_exact_scope(self):
        self.assertEqual(_read_private_scope(BytesIO(
            b'{"tenant_id":"t","actor_id":"a","context_id":"c"}')), ("t", "a", "c"))

    def test_denial_never_emits_scope_content(self):
        for bad in (
            b"", b"x" * 4097, b"\xff", b"[]", b"{}",
            b'{"tenant_id":"t","tenant_id":"x","actor_id":"a","context_id":"c"}',
            b'{"tenant_id":"t","actor_id":"a","context_id":"c","password":"secret"}',
            b'{"tenant_id":"t","actor_id":"a","context_id":true}',
            b'{"tenant_id":"t","actor_id":"a","context_id":"\\ud800"}',
        ):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError) as error:
                _read_private_scope(BytesIO(bad))
            self.assertNotIn("secret", str(error.exception))

    def test_driver_int64_topology_values_are_not_false_negatives(self):
        process = ObjectId()
        hello = {"setName": "rs0", "isWritablePrimary": True,
                 "setVersion": Int64(9),
                 "topologyVersion": {"processId": process, "counter": Int64(10)}}
        expected = _trusted_topology(hello)
        self.assertIsNotNone(expected)
        self.assertEqual(expected, _trusted_topology({
            **hello, "setVersion": 9,
            "topologyVersion": {"processId": process, "counter": 10},
        }))
        self.assertIsNone(_trusted_topology({**hello, "setVersion": Int64(-1)}))

    def test_hostile_keys_denied_before_equality(self):
        class BadKey:
            def __hash__(self):
                return hash("authInfo")
            def __eq__(self, other):
                raise AssertionError("untrusted equality")
        self.assertIsNone(_authenticated_principals({BadKey(): 1}))
        self.assertIsNone(_trusted_topology({BadKey(): 1}))


class SharedWitnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_distinct_source_databases_observe_same_explicit_name_separately(self):
        env = {"MONGO_URL": "mongodb://backend:private@mongo:27017",
               "DB_NAME": "tutolage", "SKL_MONGO_URI": "mongodb://engine:private@mongo:27017",
               "SKL_MONGO_DATABASE": "skeleton"}
        for source, uri_key in (("backend", "MONGO_URL"), ("engine", "SKL_MONGO_URI")):
            with self.subTest(source=source), patch.dict("os.environ", env, clear=True):
                client = MagicMock()
                observer = AsyncMock(return_value=_result(
                    "mongo_epoch_observed_only", replica_set=True, epoch=True, authenticated=True))
                with patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=client) as factory, \
                     patch("skeleton.app.compose_guarded_preflight.inspect_compose_mongo_epoch", observer):
                    report = await _run_from_environment(source=source,
                        shared_epoch_database="canonical_witness", scope=("t", "a", "c"))
                self.assertEqual(factory.call_args.args, (env[uri_key],))
                client.__getitem__.assert_called_once_with("canonical_witness")
                observer.assert_awaited_once()
                client.close.assert_called_once()
                self.assertTrue(report["shared_epoch_database_selected"])
                self.assertFalse(report["canonical_database_name_aligned_observed"])
                self.assertFalse(report["canonical_cluster_identity_verified"])
                self.assertFalse(report["guarded_local_ai_ready"])
                summary = summarize_observation(report)
                self.assertTrue(summary["single_source_shared_epoch_observed"])
                self.assertFalse(summary["mongo_observation_complete"])
                self.assertFalse(summary["cross_service_authority_verified"])
                self.assertFalse(summary["activation_permitted"])
                self.assertNotIn("private", str(report))

    async def test_invalid_witness_names_fail_before_connection(self):
        env = {"MONGO_URL": "mongodb://backend:private@mongo:27017", "DB_NAME": "tutolage"}
        with patch.dict("os.environ", env, clear=True), \
             patch("motor.motor_asyncio.AsyncIOMotorClient") as factory:
            for name in ("", "x/y", "x" * 64, " x", "x:27017"):
                report = await _run_from_environment(shared_epoch_database=name, scope=("t", "a", "c"))
                self.assertEqual(report["code"], "canonical_shared_epoch_database_identity_required")
                self.assertFalse(report["guarded_local_ai_ready"])
            factory.assert_not_called()

    def test_summary_rejects_false_authority(self):
        report = _result("mongo_epoch_observed_only", replica_set=True, epoch=True, authenticated=True)
        report["shared_epoch_database_selected"] = True
        for field in ("canonical_cluster_identity_verified", "consumer_or_device_qualified",
                      "canonical_database_name_aligned_observed"):
            bad = {**report, field: True}
            summary = summarize_observation(bad)
            self.assertFalse(summary["observation_valid"])
            self.assertFalse(summary["activation_permitted"])


if __name__ == "__main__":
    unittest.main()
