"""Proxy-identity denial is deterministic and never an activation certificate."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.app.compose_guarded_preflight import inspect_compose_mongo_epoch


class _Mongo:
    def __init__(self, hello):
        self.hello = hello
        self.calls = []

    async def command(self, name):
        self.calls.append(name)
        if name != "hello":
            raise AssertionError("proxy identity must be denied before auth/epoch")
        return self.hello


class _NoEpoch:
    def __init__(self, database):
        raise AssertionError("epoch access must not occur for a proxy")


class ComposeLoadBalancedAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def _inspect(self, hello):
        database = _Mongo(hello)
        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch", _NoEpoch):
            result = await inspect_compose_mongo_epoch(
                database, tenant_id="tenant", actor_id="owner", context_id="context",
            )
        return result, database.calls

    async def test_proxy_claims_never_reach_canonical_epoch(self):
        for extra in (
            {"loadBalanced": True},
            {"loadBalanced": 1},
            {"loadBalanced": "false"},
            {"loadBalanced": []},
            {"serviceId": "synthetic-service"},
            {"serviceId": None},
            {"loadBalanced": False, "serviceId": "synthetic-service"},
        ):
            with self.subTest(extra=extra):
                hello = {"setName": "rs0", "isWritablePrimary": True, **extra}
                result, calls = await self._inspect(hello)
                self.assertEqual(calls, ["hello"])
                self.assertEqual(result["code"], "mongo_replica_set_primary_required")
                self.assertFalse(result["canonical_actor_epoch_stable_observed"])
                self.assertFalse(result["guarded_local_ai_ready"])
                self.assertFalse(result["writes_performed"])

    async def test_explicit_non_proxy_flag_does_not_grant_readiness(self):
        class Epoch:
            def __init__(self, database):
                self.database = database

            async def read_epoch(self, **scope):
                return 2

        class AuthMongo(_Mongo):
            async def command(self, name):
                self.calls.append(name)
                if name == "connectionStatus":
                    return {"authInfo": {"authenticatedUsers": [
                        {"db": "admin", "user": "operator"}
                    ]}}
                return self.hello

        db = AuthMongo({"setName": "rs0", "isWritablePrimary": True, "loadBalanced": False})
        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch", Epoch):
            result = await inspect_compose_mongo_epoch(
                db, tenant_id="tenant", actor_id="owner", context_id="context",
            )
        self.assertEqual(result["code"], "mongo_epoch_observed_only")
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertFalse(result["independent_reviewer_verified"])
        self.assertFalse(result["canonical_writer_inventory_verified"])


if __name__ == "__main__":
    unittest.main()
