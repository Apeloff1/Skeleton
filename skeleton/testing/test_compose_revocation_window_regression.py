"""Deterministic revocation races for read-only guarded Compose preflight.

These checks establish denial under simulated interleavings, not live Mongo
writer fencing, reviewer trust, model binding, or consumer qualification.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.app.compose_guarded_preflight import inspect_compose_mongo_epoch


class _Epoch:
    next_values = (2, 2)
    calls = 0

    def __init__(self, database):
        self.database = database

    async def read_epoch(self, **scope):
        type(self).calls += 1
        return type(self).next_values[type(self).calls - 1]


class _Mongo:
    def __init__(self, *, change_on=None, changed=None):
        self.calls = 0
        self.change_on = change_on
        self.changed = changed
        self.primary = {
            "isWritablePrimary": True,
            "setName": "rs0",
            "me": "mongo-a:27017",
            "primary": "mongo-a:27017",
            "hosts": ["mongo-a:27017"],
            "setVersion": 7,
        }
        self.auth = {"authInfo": {
            "authenticatedUsers": [{"db": "admin", "user": "writer"}],
            "authenticatedUserRoles": [{"db": "admin", "role": "readWrite"}],
        }}

    async def command(self, name):
        self.calls += 1
        if self.calls == self.change_on:
            return self.changed
        if name == "hello":
            return dict(self.primary)
        if name == "connectionStatus":
            return {"authInfo": {
                "authenticatedUsers": [dict(self.auth["authInfo"]["authenticatedUsers"][0])],
                "authenticatedUserRoles": [dict(self.auth["authInfo"]["authenticatedUserRoles"][0])],
            }}
        raise AssertionError("unexpected Mongo command")


class ComposeRevocationWindowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _Epoch.calls = 0
        _Epoch.next_values = (2, 2)

    async def _inspect(self, mongo):
        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch", _Epoch):
            return await inspect_compose_mongo_epoch(
                mongo, tenant_id="tenant", actor_id="actor", context_id="context",
            )

    async def test_epoch_revoked_between_reads(self):
        _Epoch.next_values = (2, 4)
        result = await self._inspect(_Mongo())
        self.assertEqual(result["code"], "canonical_actor_epoch_changed_during_preflight")
        self.assertEqual(_Epoch.calls, 2)
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_odd_epoch_denied_even_when_stable(self):
        _Epoch.next_values = (3, 3)
        result = await self._inspect(_Mongo())
        self.assertEqual(result["code"], "canonical_actor_epoch_changed_during_preflight")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])

    async def test_primary_revoked_after_second_epoch_read(self):
        changed = {
            "isWritablePrimary": False,
            "setName": "rs0",
            "me": "mongo-a:27017",
            "primary": "mongo-a:27017",
        }
        result = await self._inspect(_Mongo(change_on=5, changed=changed))
        self.assertEqual(result["code"], "mongo_primary_changed_during_final_epoch_read")
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_role_revoked_after_second_epoch_read(self):
        changed = {"authInfo": {
            "authenticatedUsers": [{"db": "admin", "user": "writer"}],
            "authenticatedUserRoles": [{"db": "admin", "role": "read"}],
        }}
        result = await self._inspect(_Mongo(change_on=6, changed=changed))
        self.assertEqual(result["code"], "mongo_principal_changed_during_final_epoch_read")
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_stable_observation_never_authorizes_activation(self):
        result = await self._inspect(_Mongo())
        self.assertEqual(result["code"], "mongo_epoch_observed_only")
        self.assertTrue(result["canonical_actor_epoch_stable_observed"])
        for field in (
            "canonical_writer_inventory_verified",
            "canonical_cluster_identity_verified",
            "independent_reviewer_verified",
            "activated_model_tokenizer_verified",
            "guarded_local_ai_ready",
            "consumer_or_device_qualified",
            "writes_performed",
        ):
            self.assertIs(result[field], False)


if __name__ == "__main__":
    unittest.main()
