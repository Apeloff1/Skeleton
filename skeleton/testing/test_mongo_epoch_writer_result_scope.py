"""Writer admission and completion must authenticate returned Mongo document scope."""
from __future__ import annotations

import unittest
from contextvars import ContextVar

from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch, MongoSourceEpochError
from skeleton.testing.test_mongo_epoch_revocation import FakeMajorityCollection


class WriterResultScopeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.collection = FakeMajorityCollection()
        self.epoch = object.__new__(MongoCanonicalSourceEpoch)
        self.epoch._collection = self.collection
        self.epoch._active = ContextVar("scope-test-writer", default=None)

    async def test_admission_rejects_forged_actor_scope(self):
        original = self.collection.find_one_and_update
        async def forged(*args, **kwargs):
            result = await original(*args, **kwargs)
            result["actor_id"] = "other-actor"
            return result
        self.collection.find_one_and_update = forged
        with self.assertRaisesRegex(MongoSourceEpochError, "not owned"):
            async with self.epoch.writer(tenant_id="tenant", actor_id="owner"):
                self.fail("forged actor admitted")
        self.assertEqual(self.collection.doc["phase"], "writing")

    async def test_completion_rejects_forged_tenant_scope(self):
        original = self.collection.find_one_and_update
        async def forged(*args, **kwargs):
            result = await original(*args, **kwargs)
            if result["phase"] == "stable":
                result["tenant_id"] = "other-tenant"
            return result
        self.collection.find_one_and_update = forged
        with self.assertRaisesRegex(MongoSourceEpochError, "quarantined"):
            async with self.epoch.writer(tenant_id="tenant", actor_id="owner"):
                self.epoch.require_actor_writer(tenant_id="tenant", actor_id="owner")

    async def test_phase_subclass_cannot_fake_admission(self):
        original = self.collection.find_one_and_update
        class ForgedPhase(str):
            pass
        async def forged(*args, **kwargs):
            result = await original(*args, **kwargs)
            result["phase"] = ForgedPhase("writing")
            return result
        self.collection.find_one_and_update = forged
        with self.assertRaisesRegex(MongoSourceEpochError, "not owned"):
            async with self.epoch.writer(tenant_id="tenant", actor_id="owner"):
                self.fail("subclass admitted")


if __name__ == "__main__":
    unittest.main()
