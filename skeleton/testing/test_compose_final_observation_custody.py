"""Regression custody tests for the final Mongo preflight observation window.

These tests never grant guarded inference readiness or contact MongoDB.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.app.compose_guarded_preflight import inspect_compose_mongo_epoch


class _Epoch:
    def __init__(self, database):
        self.database = database

    async def read_epoch(self, **scope):
        self.database.events.append("epoch")
        return self.database.epochs.pop(0)


class _Database:
    def __init__(self, *, epochs=(2, 2), roles=None, terminal_roles=None,
                 terminal_primary=True):
        self.events = []
        self.epochs = list(epochs)
        self.roles = roles if roles is not None else [{"db": "admin", "role": "read"}]
        self.terminal_roles = terminal_roles
        self.terminal_primary = terminal_primary
        self.auth_count = 0
        self.hello_count = 0

    async def command(self, command):
        self.events.append(command)
        if command == "hello":
            self.hello_count += 1
            primary = self.terminal_primary if self.hello_count == 4 else True
            return {"setName": "rs0", "isWritablePrimary": primary}
        if command == "connectionStatus":
            self.auth_count += 1
            roles = (self.terminal_roles if self.auth_count == 3
                     and self.terminal_roles is not None else self.roles)
            return {"authInfo": {
                "authenticatedUsers": [{"db": "admin", "user": "operator"}],
                "authenticatedUserRoles": roles,
            }}
        raise AssertionError("unexpected command")


class FinalObservationCustodyTests(unittest.IsolatedAsyncioTestCase):
    async def _inspect(self, database):
        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch",
                   _Epoch):
            return await inspect_compose_mongo_epoch(
                database, tenant_id="tenant", actor_id="actor",
                context_id="context",
            )

    async def test_stable_observation_is_never_activation(self):
        database = _Database()
        result = await self._inspect(database)
        self.assertEqual(result["code"], "mongo_epoch_observed_only")
        self.assertEqual(database.events, [
            "hello", "connectionStatus", "epoch", "hello",
            "connectionStatus", "epoch", "hello", "connectionStatus", "hello",
        ])
        self.assertTrue(result["canonical_actor_epoch_stable_observed"])
        for key in ("guarded_local_ai_ready", "canonical_writer_inventory_verified",
                    "independent_reviewer_verified", "activated_model_tokenizer_verified",
                    "consumer_or_device_qualified", "writes_performed"):
            self.assertIs(result[key], False, key)

    async def test_role_rotation_after_final_epoch_denies_observation(self):
        database = _Database(terminal_roles=[{"db": "admin", "role": "readWrite"}])
        result = await self._inspect(database)
        self.assertEqual(result["code"], "mongo_principal_changed_during_final_epoch_read")
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertEqual(database.epochs, [])

    async def test_primary_loss_after_final_auth_denies_observation(self):
        database = _Database(terminal_primary=False)
        result = await self._inspect(database)
        self.assertEqual(result["code"], "mongo_primary_changed_after_final_authentication")
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])

    async def test_odd_epoch_denies_observation(self):
        database = _Database(epochs=(3, 3))
        result = await self._inspect(database)
        self.assertEqual(result["code"], "canonical_actor_epoch_changed_during_preflight")
        self.assertFalse(result["guarded_local_ai_ready"])

    async def test_epoch_rotation_denies_observation(self):
        database = _Database(epochs=(2, 4))
        result = await self._inspect(database)
        self.assertEqual(result["code"], "canonical_actor_epoch_changed_during_preflight")
        self.assertFalse(result["guarded_local_ai_ready"])


if __name__ == "__main__":
    unittest.main()
