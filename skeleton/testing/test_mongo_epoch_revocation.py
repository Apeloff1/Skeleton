"""Revocation CAS is terminal and cannot bypass active Mongo writers."""
from __future__ import annotations

import unittest

from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, MongoSourceEpochError,
)


class FakeMajorityCollection:
    def __init__(self):
        self.doc = {
            "_id": MongoCanonicalSourceEpoch._key("tenant", "owner"),
            "tenant_id": "tenant", "actor_id": "owner",
            "phase": "stable", "writer_token": None, "epoch": 2,
        }
        self.calls = 0
        self.error = None

    async def find_one(self, filter, *, max_time_ms):
        if any(self.doc.get(key) != value for key, value in filter.items()):
            return None
        return dict(self.doc)

    async def find_one_and_update(self, filter, update, *, return_document):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if any(self.doc.get(key) != value for key, value in filter.items()):
            return None
        self.doc = dict(self.doc)
        for key, value in update.get("$inc", {}).items():
            self.doc[key] += value
        self.doc.update(update.get("$set", {}))
        return dict(self.doc)


class EpochRevocationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.collection = FakeMajorityCollection()
        self.calls = 0
        self.authorized = True

        async def authorize(**kwargs):
            self.calls += 1
            self.assertEqual(kwargs, {
                "tenant_id": "tenant", "actor_id": "owner",
                "expected_epoch": 2, "reason_code": "operator-revoke",
            })
            return self.authorized

        self.epoch = object.__new__(MongoCanonicalSourceEpoch)
        self.epoch._collection = self.collection
        self.epoch._revocation_authorizer = authorize

    async def revoke(self, **overrides):
        options = dict(
            tenant_id="tenant", actor_id="owner",
            expected_epoch=2, reason_code="operator-revoke",
        )
        options.update(overrides)
        return await self.epoch.revoke_actor(**options)

    async def test_terminal_revocation_cas(self):
        self.assertEqual(await self.revoke(), 3)
        self.assertEqual(self.collection.doc["phase"], "revoked")
        self.assertEqual(self.collection.doc["writer_token"], None)
        self.assertEqual(self.collection.doc["epoch"], 3)
        with self.assertRaises(MongoSourceEpochError):
            await self.revoke()
        self.assertEqual(self.collection.doc["phase"], "revoked")

    async def test_active_writer_cannot_be_preempted(self):
        self.collection.doc.update(
            {"phase": "writing", "epoch": 3, "writer_token": "writer"}
        )
        with self.assertRaises(MongoSourceEpochError):
            await self.revoke()
        self.assertEqual(self.collection.doc["phase"], "writing")
        self.assertEqual(self.collection.doc["writer_token"], "writer")

    async def test_stale_expected_epoch_cannot_revoke_new_writer(self):
        self.collection.doc["epoch"] = 4
        with self.assertRaises(MongoSourceEpochError):
            await self.revoke()
        self.assertEqual(self.collection.doc["epoch"], 4)

    async def test_missing_operator_authorizer_denies_before_mongo(self):
        self.epoch._revocation_authorizer = None
        with self.assertRaises(MongoSourceEpochError):
            await self.revoke()
        self.assertEqual(self.collection.calls, 0)

    async def test_denied_authorizer_denies_before_mongo(self):
        self.authorized = False
        with self.assertRaises(MongoSourceEpochError):
            await self.revoke()
        self.assertEqual(self.collection.calls, 0)

    async def test_invalid_reason_denies_before_authorizer(self):
        with self.assertRaises(MongoSourceEpochError):
            await self.revoke(reason_code="migration")
        self.assertEqual(self.calls, 0)

    async def test_invalid_epoch_denies_before_authorizer(self):
        for value in (0, 1, 3, True, None, -2):
            with self.subTest(value=value), self.assertRaises(MongoSourceEpochError):
                await self.revoke(expected_epoch=value)
        self.assertEqual(self.calls, 0)

    async def test_mongo_failure_is_ambiguous_and_not_retried(self):
        self.collection.error = RuntimeError("secret connection details")
        with self.assertRaises(MongoSourceEpochError) as caught:
            await self.revoke()
        self.assertNotIn("secret", str(caught.exception))
        self.assertEqual(self.collection.calls, 1)

    async def test_authorizer_exception_is_redacted(self):
        async def failing(**kwargs):
            raise RuntimeError("secret operator credential")
        self.epoch._revocation_authorizer = failing
        with self.assertRaises(MongoSourceEpochError) as caught:
            await self.revoke()
        self.assertNotIn("secret", str(caught.exception))
        self.assertEqual(self.collection.calls, 0)

    async def test_restart_reader_rejects_persisted_revocation(self):
        await self.revoke()
        restarted = object.__new__(MongoCanonicalSourceEpoch)
        restarted._reader = self.collection
        with self.assertRaises(MongoSourceEpochError):
            await restarted.read_epoch(
                tenant_id="tenant", actor_id="owner", context_id="context",
            )

    async def test_revocation_is_not_an_automatic_epoch_reset(self):
        await self.revoke()
        # The existing reader requires phase=stable and even epoch. A
        # revoked actor can never be silently re-admitted by writer().
        self.assertNotEqual(self.collection.doc["phase"], "stable")
        self.assertEqual(self.collection.doc["epoch"] % 2, 1)


if __name__ == "__main__":
    unittest.main()
