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
        self.auth = {"authInfo": {"authenticatedUsers": [{"user": "ci", "db": "admin"}]}}
        self.calls = 0
        self.error = None

    async def command(self, name):
        self.calls += 1
        if self.error:
            raise self.error
        return self.auth if name == "connectionStatus" else self.hello


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

    async def test_cli_exit_fails_closed_on_epoch_only_observation(self):
        from skeleton.app.compose_guarded_preflight import main
        from contextlib import redirect_stdout
        from io import StringIO
        import json

        for observed, expected_exit in (
            ({"canonical_actor_epoch_stable_observed": True,
              "guarded_local_ai_ready": False}, 2),
            ({"canonical_actor_epoch_stable_observed": False,
              "guarded_local_ai_ready": False}, 2),
        ):
            with self.subTest(observed=observed):
                output = StringIO()
                with patch("skeleton.app.compose_guarded_preflight.asyncio.run",
                           return_value=observed), \
                     redirect_stdout(output):
                    exit_code = main()
                self.assertEqual(exit_code, expected_exit)
                self.assertEqual(json.loads(output.getvalue()), observed)

    async def test_primary_and_stable_epoch_only_prove_mongo_preflight(self):
        result = await self.inspect()
        self.assertEqual(result["schema_version"], SCHEMA)
        self.assertEqual(result["code"], "mongo_epoch_observed_only")
        self.assertTrue(result["mongo_replica_set_primary_observed"])
        self.assertTrue(result["mongo_authenticated_session_observed"])
        self.assertTrue(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertFalse(result["activated_model_tokenizer_verified"])
        self.assertFalse(result["independent_reviewer_verified"])
        self.assertFalse(result["canonical_writer_inventory_verified"])
        self.assertFalse(result["writes_performed"])
        self.assertEqual(FakeEpoch.instances[0].calls, 2)
        self.assertEqual(self.db.calls, 6)

    async def test_unbounded_replica_set_generation_denied_before_epoch(self):
        # BSON int64 is the maximum representable generation. An arbitrary
        # Python integer must not be treated as a Mongo election witness.
        for invalid in (-1, True, 1 << 63, 1 << 128):
            with self.subTest(value=repr(invalid)):
                self.db.hello["setVersion"] = invalid
                result = await self.inspect()
                self.assertEqual(result["code"], "mongo_replica_set_primary_required")
                self.assertFalse(result["guarded_local_ai_ready"])
                self.assertEqual(FakeEpoch.instances, [])
        self.db.hello.pop("setVersion")

    async def test_unbounded_actor_epoch_is_not_a_readiness_observation(self):
        class UnboundedEpoch(FakeEpoch):
            async def read_epoch(self, **kwargs):
                self.calls += 1
                return 1 << 128

        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch",
                   UnboundedEpoch):
            result = await self.inspect()
        self.assertEqual(result["code"], "canonical_actor_epoch_changed_during_preflight")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_conflicting_primary_endpoints_denied_before_epoch(self):
        self.db.hello.update({"me": "mongo-a:27017", "primary": "mongo-b:27017"})
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_replica_set_primary_required")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertEqual(FakeEpoch.instances, [])
        self.assertEqual(self.db.calls, 1)

    async def test_primary_absent_from_advertised_hosts_denied(self):
        self.db.hello.update({
            "me": "mongo-a:27017", "primary": "mongo-a:27017",
            "hosts": ["mongo-b:27017", "mongo-c:27017"],
        })
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_replica_set_primary_required")
        self.assertEqual(FakeEpoch.instances, [])

    async def test_malformed_membership_denied_before_epoch(self):
        class HostileHost(str):
            def __hash__(self):
                raise AssertionError("untrusted host hash executed")

        invalid = (
            ["mongo-a:27017", "mongo-a:27017"],
            ["mongo-a:27017", HostileHost("mongo-b:27017")],
            ["mongo-a:27017", "bad\\nnode"],
            ["mongo-a:27017"] * 65,
            ["mongo-a:27017", 123],
        )
        for hosts in invalid:
            with self.subTest(hosts=repr(hosts)):
                self.db.hello["hosts"] = hosts
                result = await self.inspect()
                self.assertEqual(result["code"], "mongo_replica_set_primary_required")
                self.assertFalse(result["guarded_local_ai_ready"])
                self.assertEqual(FakeEpoch.instances, [])
        self.db.hello.pop("hosts")


    async def test_conflicting_primary_role_flags_fail_before_epoch(self):\n        for role in ("secondary", "arbiterOnly"):\n            for value in (True, 1, "false", [], {}):\n                with self.subTest(role=role, value=repr(value)):\n                    self.db.hello[role] = value\n                    result = await self.inspect()\n                    self.assertEqual(result["code"], "mongo_replica_set_primary_required")\n                    self.assertFalse(result["guarded_local_ai_ready"])\n                    self.assertEqual(FakeEpoch.instances, [])\n                    self.db.hello.pop(role)\n\n    async def test_explicit_false_role_flags_remain_observation_only(self):\n        self.db.hello.update({"secondary": False, "arbiterOnly": False})\n        result = await self.inspect()\n        self.assertEqual(result["code"], "mongo_epoch_observed_only")\n        self.assertFalse(result["guarded_local_ai_ready"])\n\n    async def test_primary_cannot_claim_passive_or_arbiter_role(self):
        for field in ("passives", "arbiters"):
            for endpoint_field in ("me", "primary"):
                with self.subTest(role=field, endpoint=endpoint_field):
                    self.db.hello.update({
                        "me": "mongo-a:27017", "primary": "mongo-a:27017",
                        field: ["mongo-a:27017"],
                    })
                    result = await self.inspect()
                    self.assertEqual(result["code"], "mongo_replica_set_primary_required")
                    self.assertFalse(result["canonical_actor_epoch_stable_observed"])
                    self.assertFalse(result["guarded_local_ai_ready"])
                    self.assertEqual(FakeEpoch.instances, [])
                    self.db.hello.pop(field)

    async def test_combined_replica_membership_budget_denied(self):
        # Each advertised class is individually below the bound, but the
        # aggregate topology exceeds the fixed custody inspection budget.
        self.db.hello.update({
            "me": "mongo-a:27017", "primary": "mongo-a:27017",
            "hosts": ["mongo-a:27017"] + [f"mongo-h{i}:27017" for i in range(39)],
            "passives": [f"mongo-p{i}:27017" for i in range(24)],
            "arbiters": ["mongo-extra:27017"],
        })
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_replica_set_primary_required")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertEqual(FakeEpoch.instances, [])
        self.assertEqual(self.db.calls, 1)

    async def test_exact_membership_budget_is_observation_only(self):
        self.db.hello.update({
            "me": "mongo-a:27017", "primary": "mongo-a:27017",
            "hosts": ["mongo-a:27017"] + [f"mongo-h{i}:27017" for i in range(39)],
            "passives": [f"mongo-p{i}:27017" for i in range(24)],
        })
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_epoch_observed_only")
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_membership_rotation_during_epoch_denied(self):
        class RotatingMembers(FakeDB):
            async def command(self, name):
                result = await super().command(name)
                if name == "hello" and self.calls == 3:
                    return {**result, "hosts": ["mongo-a:27017", "mongo-c:27017"]}
                return result

        self.db = RotatingMembers()
        self.db.hello.update({
            "me": "mongo-a:27017", "primary": "mongo-a:27017",
            "hosts": ["mongo-a:27017", "mongo-b:27017"],
        })
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_primary_changed_during_preflight")
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_valid_membership_remains_observation_only(self):
        self.db.hello.update({
            "me": "mongo-a:27017", "primary": "mongo-a:27017",
            "hosts": ["mongo-b:27017", "mongo-a:27017"],
            "arbiters": ["mongo-c:27017"],
        })
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_epoch_observed_only")
        self.assertFalse(result["canonical_cluster_identity_verified"])
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_matching_primary_endpoints_are_observation_only(self):
        self.db.hello.update({"me": "mongo-a:27017", "primary": "mongo-a:27017"})
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_epoch_observed_only")
        self.assertTrue(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["canonical_cluster_identity_verified"])
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_primary_election_between_reads_denies_stable_epoch(self):
        class RotatingDB(FakeDB):
            async def command(self, name):
                result = await super().command(name)
                if name == "hello" and self.calls == 3:
                    return {"setName": "rs0", "isWritablePrimary": True,
                            "electionId": "new-election"}
                return result
        self.db = RotatingDB()
        self.db.hello["electionId"] = "old-election"
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_primary_changed_during_preflight")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertEqual(FakeEpoch.instances[0].calls, 1)

    async def test_topology_generation_rotation_denies(self):
        from bson.objectid import ObjectId
        process = ObjectId()

        class RotatingTopology(FakeDB):
            async def command(self, name):
                result = await super().command(name)
                if name == "hello" and self.calls == 3:
                    return {**result, "topologyVersion": {
                        "processId": process, "counter": 9}}
                return result

        self.db = RotatingTopology()
        self.db.hello["topologyVersion"] = {
            "processId": process, "counter": 8}
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_primary_changed_during_preflight")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_untrusted_topology_fields_denied_before_epoch(self):
        from bson.objectid import ObjectId

        class ForgedCounter(int):
            def __eq__(self, other):
                raise AssertionError("untrusted counter equality executed")

        for bad in (
            {"processId": ObjectId(), "counter": True},
            {"processId": ObjectId(), "counter": ForgedCounter(1)},
            {"processId": "forged", "counter": 1},
            {"processId": ObjectId(), "counter": -1},
            {"processId": ObjectId(), "counter": 1 << 63},
            {"processId": ObjectId(), "counter": 1, "extra": 2},
        ):
            with self.subTest(value=repr(bad)):
                self.db.hello["topologyVersion"] = bad
                result = await self.inspect()
                self.assertEqual(result["code"], "mongo_replica_set_primary_required")
                self.assertFalse(result["guarded_local_ai_ready"])
                self.assertEqual(FakeEpoch.instances, [])

    async def test_primary_loss_between_reads_denies(self):
        class LostPrimary(FakeDB):
            async def command(self, name):
                result = await super().command(name)
                if name == "hello" and self.calls == 3:
                    return {"setName": "rs0", "isWritablePrimary": False}
                return result
        self.db = LostPrimary()
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_primary_changed_during_preflight")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])

    async def test_principal_rotation_between_epoch_reads_denies(self):
        class RotatingPrincipal(FakeDB):
            async def command(self, name):
                result = await super().command(name)
                if name == "connectionStatus" and self.calls == 4:
                    return {"authInfo": {"authenticatedUsers": [{"user": "other", "db": "admin"}]}}
                return result
        self.db = RotatingPrincipal()
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_principal_changed_during_preflight")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertEqual(FakeEpoch.instances[0].calls, 1)

    async def test_principal_loss_between_epoch_reads_denies(self):
        class LostPrincipal(FakeDB):
            async def command(self, name):
                result = await super().command(name)
                if name == "connectionStatus" and self.calls == 4:
                    return {"authInfo": {"authenticatedUsers": []}}
                return result
        self.db = LostPrincipal()
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_principal_changed_during_preflight")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])

    async def test_election_during_final_epoch_read_denies(self):
        class ElectionAfterEpoch(FakeDB):
            async def command(self, name):
                result = await super().command(name)
                if name == "hello" and self.calls == 5:
                    return {"setName": "rs0", "isWritablePrimary": True,
                            "electionId": "rotated"}
                return result
        self.db = ElectionAfterEpoch()
        self.db.hello["electionId"] = "original"
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_primary_changed_during_final_epoch_read")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertEqual(FakeEpoch.instances[0].calls, 2)

    async def test_principal_rotation_during_final_epoch_read_denies(self):
        class PrincipalAfterEpoch(FakeDB):
            async def command(self, name):
                result = await super().command(name)
                if name == "connectionStatus" and self.calls == 6:
                    return {"authInfo": {"authenticatedUsers": [
                        {"user": "rotated", "db": "admin"}]}}
                return result
        self.db = PrincipalAfterEpoch()
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_principal_changed_during_final_epoch_read")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertEqual(FakeEpoch.instances[0].calls, 2)

    async def test_epoch_advance_between_reads_denies(self):
        class AdvancingEpoch(FakeEpoch):
            async def read_epoch(self, **kwargs):
                self.calls += 1
                return 2 if self.calls == 1 else 4
        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch",
                   AdvancingEpoch):
            result = await self.inspect()
        self.assertEqual(result["code"], "canonical_actor_epoch_changed_during_preflight")
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_invalid_epoch_type_denies(self):
        class BooleanEpoch(FakeEpoch):
            async def read_epoch(self, **kwargs):
                self.calls += 1
                return True
        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch",
                   BooleanEpoch):
            result = await self.inspect()
        self.assertEqual(result["code"], "canonical_actor_epoch_changed_during_preflight")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])

    async def test_final_epoch_subclass_equality_never_executes(self):
        class HostileEpoch(int):
            def __eq__(self, other):
                raise AssertionError("untrusted epoch equality executed")

        class HostileFinalEpoch(FakeEpoch):
            async def read_epoch(self, **kwargs):
                self.calls += 1
                return 2 if self.calls == 1 else HostileEpoch(2)

        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch",
                   HostileFinalEpoch):
            result = await self.inspect()
        self.assertEqual(result["code"], "canonical_actor_epoch_changed_during_preflight")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_mutable_scope_subclass_rejected_before_mongo(self):
        class UntrustedScope(str):
            def __eq__(self, other):
                raise AssertionError("subclass equality executed")
        result = await self.inspect(tenant_id=UntrustedScope("tenant"))
        self.assertEqual(result["code"], "operator_actor_scope_required")
        self.assertEqual(self.db.calls, 0)
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_malformed_replica_set_name_rejected_before_epoch(self):
        for name in ("", "rs\\n0", "rs\\x7f0", "r" * 129, "\\ud800"):
            with self.subTest(name=repr(name)):
                self.db.hello["setName"] = name
                result = await self.inspect()
                self.assertEqual(result["code"], "mongo_replica_set_primary_required")
                self.assertFalse(result["canonical_actor_epoch_stable_observed"])
                self.assertEqual(FakeEpoch.instances, [])

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

    async def test_unauthenticated_mongo_denied_before_epoch(self):
        self.db.auth = {"authInfo": {"authenticatedUsers": []}}
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_authenticated_session_required")
        self.assertFalse(result["mongo_authenticated_session_observed"])
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertEqual(FakeEpoch.instances, [])

    async def test_malformed_authenticated_identity_denied(self):
        for bad in (None, {}, {"authInfo": {}},
                    {"authInfo": {"authenticatedUsers": [1]}},
                    {"authInfo": {"authenticatedUsers": [{"user": "", "db": "admin"}]}}):
            with self.subTest(value=repr(bad)):
                self.db.auth = bad
                result = await self.inspect()
                self.assertEqual(result["code"], "mongo_authenticated_session_required")
                self.assertFalse(result["guarded_local_ai_ready"])

    async def test_duplicate_authenticated_principal_denied_before_epoch(self):
        user = {"user": "ci", "db": "admin"}
        self.db.auth = {"authInfo": {"authenticatedUsers": [user, dict(user)]}}
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_authenticated_session_required")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertEqual(FakeEpoch.instances, [])

    async def test_duplicate_principal_during_final_read_denied(self):
        class DuplicatedFinal(FakeDB):
            async def command(self, name):
                result = await super().command(name)
                if name == "connectionStatus" and self.calls == 6:
                    user = {"user": "ci", "db": "admin"}
                    return {"authInfo": {"authenticatedUsers": [user, dict(user)]}}
                return result
        self.db = DuplicatedFinal()
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_principal_changed_during_final_epoch_read")
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_oversized_authentication_identity_denied_before_epoch(self):
        for bad in ("a" * 257, "user\\nname", " user", "\\ud800"):
            with self.subTest(value=repr(bad)):
                self.db.auth = {"authInfo": {"authenticatedUsers": [
                    {"user": bad, "db": "admin"}]}}
                result = await self.inspect()
                self.assertEqual(result["code"], "mongo_authenticated_session_required")
                self.assertFalse(result["guarded_local_ai_ready"])
        self.assertEqual(FakeEpoch.instances, [])

    async def test_surrogate_principal_rejected_without_exception_or_epoch_read(self):
        self.db.auth = {"authInfo": {"authenticatedUsers": [
            {"user": chr(0xD800), "db": "admin"}]}}
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_authenticated_session_required")
        self.assertEqual(FakeEpoch.instances, [])
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_observation_cli_never_exits_success_on_injected_ready_flag(self):
        from skeleton.app.compose_guarded_preflight import main
        from contextlib import redirect_stdout
        from io import StringIO
        with patch("skeleton.app.compose_guarded_preflight.asyncio.run",
                   return_value={"guarded_local_ai_ready": True}), \
             redirect_stdout(StringIO()):
            self.assertEqual(main(), 2)

    async def test_unbounded_authenticated_user_list_denied(self):
        self.db.auth = {"authInfo": {"authenticatedUsers": [
            {"user": f"user{i}", "db": "admin"} for i in range(17)]}}
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_authenticated_session_required")
        self.assertEqual(FakeEpoch.instances, [])

    async def test_authentication_probe_failure_redacts_credentials(self):
        class AuthFailureDB(FakeDB):
            async def command(self, name):
                if name == "connectionStatus":
                    raise RuntimeError("mongodb://user:password@private")
                return await super().command(name)
        self.db = AuthFailureDB()
        result = await self.inspect()
        self.assertEqual(result["code"], "mongo_authenticated_session_unavailable")
        self.assertNotIn("password", str(result))

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

    async def test_total_deadline_fails_closed_and_closes_client(self):
        from unittest.mock import AsyncMock, MagicMock
        with patch.dict("os.environ", {
            "MONGO_URL": "mongodb://secret:secret@mongo:27017",
            "DB_NAME": "skeleton",
            "SKL_CANONICAL_MONGO_DATABASE": "skeleton",
            "SKL_CANONICAL_TENANT_ID": "tenant",
            "SKL_CANONICAL_ACTOR_ID": "owner",
            "SKL_CANONICAL_CONTEXT_ID": "context",
        }):
            client = MagicMock()
            with patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=client), \
                 patch("skeleton.app.compose_guarded_preflight.inspect_compose_mongo_epoch",
                       new_callable=AsyncMock) as inspect, \
                 patch("skeleton.app.compose_guarded_preflight.asyncio.wait_for",
                       new_callable=AsyncMock, side_effect=TimeoutError):
                result = await _run_from_environment()
                inspect.assert_called_once()
                client.close.assert_called_once()
        self.assertEqual(result["code"], "mongo_preflight_deadline_exceeded")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertFalse(result["writes_performed"])
        self.assertNotIn("secret", str(result))

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
