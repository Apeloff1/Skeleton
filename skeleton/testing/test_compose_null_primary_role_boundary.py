"""Present-but-null Mongo role claims must fail before epoch custody."""
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
        if name == "hello":
            return self.hello
        raise AssertionError("malformed primary roles must not reach authentication")


class _NoEpoch:
    def __init__(self, database):
        raise AssertionError("malformed role claims must not reach epoch custody")


class NullMongoRoleBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_null_primary_role_claims_denied_before_epoch(self):
        for role in ("ismaster", "secondary", "arbiterOnly"):
            with self.subTest(role=role):
                db = _Mongo({"setName": "rs0", "isWritablePrimary": True, role: None})
                with patch("skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch", _NoEpoch):
                    result = await inspect_compose_mongo_epoch(
                        db, tenant_id="tenant", actor_id="owner", context_id="context",
                    )
                self.assertEqual(db.calls, ["hello"])
                self.assertEqual(result["code"], "mongo_replica_set_primary_required")
                self.assertFalse(result["canonical_actor_epoch_stable_observed"])
                self.assertFalse(result["guarded_local_ai_ready"])
                self.assertFalse(result["writes_performed"])


if __name__ == "__main__":
    unittest.main()
