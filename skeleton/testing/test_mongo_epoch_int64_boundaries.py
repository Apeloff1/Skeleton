"""Fail-closed BSON int64 boundary contracts for canonical Mongo writer epochs."""
import unittest
from unittest.mock import AsyncMock

from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, MongoSourceEpochError,
)


class EpochBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def make_epoch(self, doc):
        # Construct only the read facade; no network or Mongo client required.
        epoch = object.__new__(MongoCanonicalSourceEpoch)
        epoch._reader = type("Reader", (), {})()
        epoch._reader.find_one = AsyncMock(return_value=doc)
        return epoch

    @staticmethod
    def document(value):
        key = MongoCanonicalSourceEpoch._key("tenant", "actor")
        return {
            "_id": key, "tenant_id": "tenant", "actor_id": "actor",
            "phase": "stable", "writer_token": None, "epoch": value,
        }

    async def test_linearizable_reader_rejects_out_of_range_epochs(self):
        for value in (True, -2, 0, 1, 3, (1 << 63), (1 << 64),
                      (1 << 128), "2", 2.0):
            with self.subTest(value=value):
                epoch = self.make_epoch(self.document(value))
                with self.assertRaises(MongoSourceEpochError):
                    await epoch.read_epoch(
                        tenant_id="tenant", actor_id="actor",
                        context_id="context",
                    )
                epoch._reader.find_one.assert_awaited_once()

    async def test_linearizable_reader_accepts_max_even_bson_epoch(self):
        value = (1 << 63) - 2
        epoch = self.make_epoch(self.document(value))
        self.assertEqual(
            await epoch.read_epoch(
                tenant_id="tenant", actor_id="actor", context_id="context",
            ), value,
        )

    async def test_linearizable_reader_rejects_poisoned_writer(self):
        for phase, token in (("writing", "lease"), ("revoked", None),
                             ("stable", "lease")):
            with self.subTest(phase=phase, token=token):
                doc = self.document(2)
                doc.update(phase=phase, writer_token=token)
                epoch = self.make_epoch(doc)
                with self.assertRaises(MongoSourceEpochError):
                    await epoch.read_epoch(
                        tenant_id="tenant", actor_id="actor",
                        context_id="context",
                    )

    async def test_revocation_rejects_overflow_before_authorization(self):
        epoch = object.__new__(MongoCanonicalSourceEpoch)
        epoch._revocation_authorizer = AsyncMock(return_value=True)
        for value in ((1 << 63) - 1, (1 << 63), (1 << 64),
                      (1 << 128), True, -2, 3):
            with self.subTest(value=value):
                with self.assertRaises(MongoSourceEpochError):
                    await epoch.revoke_actor(
                        tenant_id="tenant", actor_id="actor",
                        expected_epoch=value, reason_code="operator-revoke",
                    )
        epoch._revocation_authorizer.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
