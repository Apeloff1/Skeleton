"""Final authentication await cannot conceal a Mongo primary transition."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.app.compose_guarded_preflight import inspect_compose_mongo_epoch


class _Epoch:
    def __init__(self, database):
        self.database = database

    async def read_epoch(self, **scope):
        self.database.calls.append("epoch")
        return 2


class _Database:
    def __init__(self, *, drift=False):
        self.calls = []
        self.drift = drift
        self.hello_count = 0

    async def command(self, name):
        self.calls.append(name)
        if name == "connectionStatus":
            return {"authInfo": {"authenticatedUsers": [
                {"db": "admin", "user": "operator"}
            ]}}
        if name != "hello":
            raise AssertionError("unexpected command")
        self.hello_count += 1
        election = "election-b" if self.drift and self.hello_count == 4 else "election-a"
        return {"setName": "rs0", "isWritablePrimary": True, "electionId": election}


class ComposeTerminalTopologyTests(unittest.IsolatedAsyncioTestCase):
    async def test_primary_changes_during_last_authentication_are_denied(self):
        db = _Database(drift=True)
        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch", _Epoch):
            result = await inspect_compose_mongo_epoch(
                db, tenant_id="tenant", actor_id="actor", context_id="context"
            )
        self.assertEqual(result["code"], "mongo_primary_changed_after_final_authentication")
        self.assertEqual(db.calls, [
            "hello", "connectionStatus", "epoch", "hello",
            "connectionStatus", "epoch", "hello", "connectionStatus", "hello",
        ])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertFalse(result["writes_performed"])

    async def test_stable_terminal_topology_is_still_observation_only(self):
        db = _Database()
        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch", _Epoch):
            result = await inspect_compose_mongo_epoch(
                db, tenant_id="tenant", actor_id="actor", context_id="context"
            )
        self.assertEqual(result["code"], "mongo_epoch_observed_only")
        self.assertEqual(db.hello_count, 4)
        self.assertFalse(result["canonical_writer_inventory_verified"])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertFalse(result["writes_performed"])


if __name__ == "__main__":
    unittest.main()
