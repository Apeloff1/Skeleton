"""Explicit-null Mongo authority metadata must never reach canonical epoch reads."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.app.compose_guarded_preflight import inspect_compose_mongo_epoch


class _Database:
    def __init__(self, hello):
        self.hello = hello
        self.calls = []

    async def command(self, name):
        self.calls.append(name)
        if name == "hello":
            return self.hello
        raise AssertionError("null authority metadata must fail before auth")


class _ForbiddenEpoch:
    def __init__(self, database):
        raise AssertionError("null authority metadata must fail before epoch custody")


class NullTopologyAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_null_authority_fields_fail_closed_before_auth_and_epoch(self):
        for field in (
            "me", "primary", "hosts", "passives", "arbiters",
            "electionId", "setVersion", "topologyVersion",
        ):
            with self.subTest(field=field):
                db = _Database({"setName": "rs0", "isWritablePrimary": True, field: None})
                with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch", _ForbiddenEpoch):
                    result = await inspect_compose_mongo_epoch(
                        db, tenant_id="tenant", actor_id="actor", context_id="context",
                    )
                self.assertEqual(db.calls, ["hello"])
                self.assertEqual(result["code"], "mongo_replica_set_primary_required")
                self.assertFalse(result["guarded_local_ai_ready"])
                self.assertFalse(result["writes_performed"])
                self.assertFalse(result["canonical_actor_epoch_stable_observed"])

    async def test_absent_optional_fields_are_not_reclassified_as_null(self):
        db = _Database({"setName": "rs0", "isWritablePrimary": True})
        result = await inspect_compose_mongo_epoch(
            db, tenant_id="tenant", actor_id="actor", context_id="context",
        )
        self.assertEqual(db.calls, ["hello", "connectionStatus"])
        self.assertEqual(result["code"], "mongo_authenticated_session_unavailable")
        self.assertFalse(result["guarded_local_ai_ready"])


if __name__ == "__main__":
    unittest.main()
