"""Mongo hello message claims are bounded before canonical epoch reads."""
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
    def __init__(self, message):
        self.message = message
        self.calls = []

    async def command(self, name):
        self.calls.append(name)
        if name == "hello":
            return {
                "setName": "rs0",
                "isWritablePrimary": True,
                "msg": self.message,
            }
        if name == "connectionStatus":
            return {"authInfo": {"authenticatedUsers": [
                {"db": "admin", "user": "operator"}
            ]}}
        raise AssertionError("unexpected Mongo command")


class MongoMessageBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_untrusted_message_claims_never_read_epoch(self):
        invalid = (
            "isdbgrid", "", "x" * 129, "bad\nclaim", "nonascii-\u00e9",
            17, True, [], {}, None,
        )
        for message in invalid:
            with self.subTest(message=repr(message)[:32]):
                db = _Database(message)
                with patch(
                    "skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch",
                    _Epoch,
                ):
                    result = await inspect_compose_mongo_epoch(
                        db, tenant_id="tenant", actor_id="actor",
                        context_id="context",
                    )
                self.assertEqual(result["code"], "mongo_replica_set_primary_required")
                self.assertEqual(db.calls, ["hello"])
                self.assertFalse(result["guarded_local_ai_ready"])
                self.assertFalse(result["writes_performed"])

    async def test_bounded_message_is_observation_only(self):
        db = _Database("replica-member")
        with patch(
            "skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch",
            _Epoch,
        ):
            result = await inspect_compose_mongo_epoch(
                db, tenant_id="tenant", actor_id="actor",
                context_id="context",
            )
        self.assertEqual(result["code"], "mongo_epoch_observed_only")
        self.assertEqual(db.calls.count("epoch"), 2)
        self.assertFalse(result["canonical_writer_inventory_verified"])
        self.assertFalse(result["guarded_local_ai_ready"])


if __name__ == "__main__":
    unittest.main()
