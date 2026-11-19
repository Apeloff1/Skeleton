"""Fail-closed tombstone scope validation before canonical writer acquisition."""
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

from skeleton.persistence.mongo_source_epoch import (
    MongoSourceEpochError, fence_memory_tombstone,
)


class ForgedString(str):
    def __eq__(self, other):
        return True


class Epoch:
    def __init__(self):
        self.acquisitions = []

    @asynccontextmanager
    async def writer(self, *, tenant_id, actor_id):
        self.acquisitions.append((tenant_id, actor_id))
        yield


class Store:
    def __init__(self, record):
        self.canonical_source_epoch = Epoch()
        self.get = AsyncMock(return_value=record)
        self.writes = 0

    @fence_memory_tombstone
    async def tombstone(self, memory_id, **kwargs):
        self.writes += 1


class TombstoneScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_scope_acquires_writer(self):
        store = Store(SimpleNamespace(tenant_id="tenant", namespace="memory", subject_id="actor"))
        await store.tombstone("memory-id", tenant_id="tenant", namespace="memory")
        self.assertEqual(store.canonical_source_epoch.acquisitions, [("tenant", "actor")])
        self.assertEqual(store.writes, 1)

    async def test_missing_or_forged_lookup_never_acquires_writer(self):
        valid = dict(tenant_id="tenant", namespace="memory", subject_id="actor")
        cases = [None] + [SimpleNamespace(**{**valid, field: ForgedString(value)})
                          for field, value in valid.items()]
        for record in cases:
            with self.subTest(record=record):
                store = Store(record)
                with self.assertRaises(MongoSourceEpochError):
                    await store.tombstone("memory-id", tenant_id="tenant", namespace="memory")
                self.assertEqual(store.canonical_source_epoch.acquisitions, [])
                self.assertEqual(store.writes, 0)

    async def test_forged_caller_scope_never_acquires_writer(self):
        for field in ("tenant_id", "namespace"):
            with self.subTest(field=field):
                store = Store(SimpleNamespace(tenant_id="tenant", namespace="memory", subject_id="actor"))
                args = dict(tenant_id="tenant", namespace="memory")
                args[field] = ForgedString(args[field])
                with self.assertRaises(MongoSourceEpochError):
                    await store.tombstone("memory-id", **args)
                self.assertEqual(store.canonical_source_epoch.acquisitions, [])
                self.assertEqual(store.writes, 0)


if __name__ == "__main__":
    unittest.main()
