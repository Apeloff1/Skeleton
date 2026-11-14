"""Reject hostile string subclasses before canonical Mongo writer acquisition."""
import unittest
from unittest.mock import AsyncMock

from skeleton.persistence.mongo_source_epoch import (
    MongoSourceEpochError, fence_conversation_write, fence_memento_write,
)


class ForgedIdentity(str):
    def __eq__(self, other):
        return True

    def __hash__(self):
        return str.__hash__(self)


class Owner:
    def __init__(self):
        self.canonical_source_epoch = type("Epoch", (), {"writer": AsyncMock()})()
        self.conversation = type("Conversation", (), {
            "canonical_source_epoch": self.canonical_source_epoch,
        })()
        self.calls = 0

    @fence_conversation_write
    async def conversation_write(self, **kwargs):
        self.calls += 1

    @fence_memento_write
    async def retire(self, **kwargs):
        self.calls += 1


class ExactScalarBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_conversation_rejects_forged_tenant_and_owner(self):
        for field in ("tenant_id", "owner_id"):
            with self.subTest(field=field):
                owner = Owner()
                args = {"tenant_id": "tenant", "owner_id": "actor"}
                args[field] = ForgedIdentity(args[field])
                with self.assertRaises(MongoSourceEpochError):
                    await owner.conversation_write(**args)
                owner.canonical_source_epoch.writer.assert_not_called()
                self.assertEqual(owner.calls, 0)

    async def test_memento_rejects_forged_scope_and_thread(self):
        for field in ("tenant_id", "owner_id", "thread_id"):
            with self.subTest(field=field):
                owner = Owner()
                args = {"tenant_id": "tenant", "owner_id": "actor", "thread_id": "thread"}
                args[field] = ForgedIdentity(args[field])
                with self.assertRaises(MongoSourceEpochError):
                    await owner.retire(**args)
                owner.canonical_source_epoch.writer.assert_not_called()
                self.assertEqual(owner.calls, 0)


if __name__ == "__main__":
    unittest.main()
