"""Guarded Compose must not confuse a mongos router or ghost with a writer.

These deterministic tests validate parsing and preflight denial only; they do
not qualify Mongo fencing, independent review, models, or a consumer device.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.app.compose_guarded_preflight import (
    _trusted_topology,
    inspect_compose_mongo_epoch,
)


class _Database:
    def __init__(self, hello):
        self.hello = hello
        self.calls = []

    async def command(self, name):
        self.calls.append(name)
        if name == "hello":
            return self.hello
        if name == "connectionStatus":
            return {"authInfo": {"authenticatedUsers": [{"user": "ci", "db": "admin"}]}}
        raise AssertionError("unexpected command")


class _NoEpoch:
    def __init__(self, database):
        raise AssertionError("untrusted topology must never reach epoch read")


class RouterGhostTopologyFencing(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hello = {
            "setName": "rs0",
            "isWritablePrimary": True,
            "me": "mongo-a:27017",
            "primary": "mongo-a:27017",
            "hosts": ["mongo-a:27017", "mongo-b:27017"],
        }

    async def _assert_denied_before_epoch(self, hello):
        db = _Database(hello)
        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch", _NoEpoch):
            result = await inspect_compose_mongo_epoch(
                db, tenant_id="tenant", actor_id="owner", context_id="context",
            )
        self.assertEqual(result["code"], "mongo_replica_set_primary_required")
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["writes_performed"])
        self.assertEqual(db.calls, ["hello"])

    async def test_router_claims_never_reach_epoch(self):
        for msg in ("isdbgrid", 1, True, [], {}, object()):
            with self.subTest(msg=repr(msg)):
                hello = dict(self.hello, msg=msg)
                self.assertIsNone(_trusted_topology(hello))
                await self._assert_denied_before_epoch(hello)

    async def test_ghost_claims_never_reach_epoch(self):
        for flag in (True, 1, "true", [], {}, object()):
            with self.subTest(flag=repr(flag)):
                hello = dict(self.hello, isreplicaset=flag)
                self.assertIsNone(_trusted_topology(hello))
                await self._assert_denied_before_epoch(hello)

    def test_explicit_non_ghost_and_non_router_remain_observation_only(self):
        baseline = _trusted_topology(self.hello)
        self.assertIsNotNone(baseline)
        self.assertEqual(
            baseline,
            _trusted_topology(dict(self.hello, isreplicaset=False, msg="")),
        )

    async def test_mongos_with_ghost_false_is_still_denied(self):
        hello = dict(self.hello, msg="isdbgrid", isreplicaset=False)
        await self._assert_denied_before_epoch(hello)


if __name__ == "__main__":
    unittest.main()
