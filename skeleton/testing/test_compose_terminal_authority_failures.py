"""Fail-closed regression for terminal Mongo authority probe failures.

These are deterministic in-memory protocol tests. They never establish actual
Mongo writer fencing, reviewer trust, or consumer activation readiness.
"""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from skeleton.app.compose_guarded_preflight import inspect_compose_mongo_epoch


class _Epoch:
    def __init__(self, database):
        self.database = database

    async def read_epoch(self, **scope):
        self.database.events.append("epoch")
        return 2


class _Database:
    def __init__(self, *, fail_at=None, malformed_at=None):
        self.fail_at = fail_at
        self.malformed_at = malformed_at
        self.events = []
        self.hello_count = 0
        self.auth_count = 0

    async def command(self, command):
        self.events.append(command)
        if command == "hello":
            self.hello_count += 1
            number = self.hello_count
            if self.fail_at == ("hello", number):
                raise ConnectionError("secret-bearing driver failure must be redacted")
            if self.malformed_at == ("hello", number):
                return {"setName": "rs0", "isWritablePrimary": False}
            return {"setName": "rs0", "isWritablePrimary": True}
        if command == "connectionStatus":
            self.auth_count += 1
            number = self.auth_count
            if self.fail_at == ("connectionStatus", number):
                raise ConnectionError("secret-bearing driver failure must be redacted")
            if self.malformed_at == ("connectionStatus", number):
                return {"authInfo": {"authenticatedUsers": None}}
            return {"authInfo": {
                "authenticatedUsers": [{"db": "admin", "user": "operator"}],
                "authenticatedUserRoles": [{"db": "admin", "role": "read"}],
            }}
        raise AssertionError("unexpected command")


class TerminalAuthorityFailureTests(unittest.IsolatedAsyncioTestCase):
    async def _inspect(self, database):
        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch", _Epoch):
            return await inspect_compose_mongo_epoch(
                database, tenant_id="tenant", actor_id="actor", context_id="context",
            )

    def _assert_closed(self, result):
        for key in (
            "guarded_local_ai_ready",
            "canonical_writer_inventory_verified",
            "independent_reviewer_verified",
            "activated_model_tokenizer_verified",
            "consumer_or_device_qualified",
            "writes_performed",
        ):
            self.assertIs(result[key], False, key)
        self.assertNotIn("secret-bearing", str(result))

    async def test_final_auth_driver_failure_is_not_a_successful_observation(self):
        database = _Database(fail_at=("connectionStatus", 3))
        result = await self._inspect(database)
        self.assertEqual(result["code"], "canonical_actor_epoch_unavailable")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertEqual(database.events.count("epoch"), 2)
        self._assert_closed(result)

    async def test_terminal_hello_driver_failure_is_not_a_successful_observation(self):
        database = _Database(fail_at=("hello", 4))
        result = await self._inspect(database)
        self.assertEqual(result["code"], "canonical_actor_epoch_unavailable")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertEqual(database.events.count("epoch"), 2)
        self._assert_closed(result)

    async def test_malformed_terminal_principal_denies_observation(self):
        database = _Database(malformed_at=("connectionStatus", 3))
        result = await self._inspect(database)
        self.assertEqual(result["code"], "mongo_principal_changed_during_final_epoch_read")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self._assert_closed(result)

    async def test_terminal_primary_demotion_denies_observation(self):
        database = _Database(malformed_at=("hello", 4))
        result = await self._inspect(database)
        self.assertEqual(result["code"], "mongo_primary_changed_after_final_authentication")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self._assert_closed(result)

    async def test_cancellation_propagates_without_readiness(self):
        class Cancelled(_Database):
            async def command(self, command):
                if command == "hello":
                    raise asyncio.CancelledError()
                return await super().command(command)

        with self.assertRaises(asyncio.CancelledError):
            await self._inspect(Cancelled())


if __name__ == "__main__":
    unittest.main()
