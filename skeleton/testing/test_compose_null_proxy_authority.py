"""Explicit-null Mongo proxy and ghost authority must fail before epoch access."""
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
        if name != "hello":
            raise AssertionError("invalid topology reached authentication")
        return self.hello


class _ForbiddenEpoch:
    def __init__(self, database):
        raise AssertionError("invalid topology reached canonical epoch")


class ComposeNullProxyAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def test_present_null_proxy_and_ghost_claims_are_denied(self):
        for field in ("msg", "loadBalanced", "isreplicaset"):
            with self.subTest(field=field):
                db = _Database({
                    "setName": "rs0", "isWritablePrimary": True,
                    field: None,
                })
                with patch(
                    "skeleton.app.compose_guarded_preflight.MongoCanonicalSourceEpoch",
                    _ForbiddenEpoch,
                ):
                    result = await inspect_compose_mongo_epoch(
                        db, tenant_id="tenant", actor_id="actor", context_id="context",
                    )
                self.assertEqual(db.calls, ["hello"])
                self.assertEqual(result["code"], "mongo_replica_set_primary_required")
                self.assertFalse(result["canonical_actor_epoch_stable_observed"])
                self.assertFalse(result["guarded_local_ai_ready"])
                self.assertFalse(result["writes_performed"])

    async def test_missing_optional_proxy_flags_are_not_null(self):
        # A missing optional field is not itself a proxy identity. This
        # regression ensures the guard checks presence, not .get() alone.
        from skeleton.app.compose_guarded_preflight import _trusted_topology
        hello = {"setName": "rs0", "isWritablePrimary": True}
        self.assertIsNotNone(_trusted_topology(hello))
        for field, value in (
            ("msg", "standalone-compatible-observation"),
            ("loadBalanced", False),
            ("isreplicaset", False),
        ):
            with self.subTest(field=field):
                self.assertIsNotNone(_trusted_topology({**hello, field: value}))


if __name__ == "__main__":
    unittest.main()
