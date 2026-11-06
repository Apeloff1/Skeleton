"""Reject explicit-null authenticated role metadata before epoch custody."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.app.compose_guarded_preflight import inspect_compose_mongo_epoch


class _Mongo:
    def __init__(self, roles):
        self.roles = roles
        self.calls = []

    async def command(self, name):
        self.calls.append(name)
        if name == "hello":
            return {"setName": "rs0", "isWritablePrimary": True}
        if name == "connectionStatus":
            return {"authInfo": {"authenticatedUsers": [
                {"db": "admin", "user": "operator"}
            ], "authenticatedUserRoles": self.roles}}
        raise AssertionError("unexpected Mongo command")


class _NoEpoch:
    def __init__(self, database):
        raise AssertionError("malformed roles must not reach epoch custody")


class ExplicitNullRoleBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_null_roles_denied_before_epoch(self):
        db = _Mongo(None)
        with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch", _NoEpoch):
            result = await inspect_compose_mongo_epoch(
                db, tenant_id="tenant", actor_id="owner", context_id="context",
            )
        self.assertEqual(db.calls, ["hello", "connectionStatus"])
        self.assertEqual(result["code"], "mongo_authenticated_session_required")
        self.assertFalse(result["canonical_actor_epoch_stable_observed"])
        self.assertFalse(result["guarded_local_ai_ready"])
        self.assertFalse(result["writes_performed"])


if __name__ == "__main__":
    unittest.main()
