"""Initial epoch provisioning is operator-only, never implicit on startup."""
from __future__ import annotations

import asyncio
import unittest

from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, MongoSourceEpochError,
)


class FakeEpochCollection:
    def __init__(self):
        self.docs = {}
        self.calls = 0
        self.failure = None

    async def insert_one(self, doc):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        if doc["_id"] in self.docs:
            raise ValueError("duplicate epoch")
        self.docs[doc["_id"]] = dict(doc)


class FakeDatabase:
    name = "canonical"

    def __init__(self):
        self.hello = {"setName": "rs0", "isWritablePrimary": True}
        self.error = None
        self.probes = 0

    async def command(self, name):
        assert name == "hello"
        self.probes += 1
        if self.error is not None:
            raise self.error
        return self.hello


class MigrationCustodyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.collection = FakeEpochCollection()
        self.authorized = True
        self.calls = []
        self.failure = None
        self.wait = None

        async def authorize(**kwargs):
            self.calls.append(kwargs)
            if self.failure is not None:
                raise self.failure
            if self.wait is not None:
                await self.wait.wait()
            return self.authorized

        self.epoch = object.__new__(MongoCanonicalSourceEpoch)
        self.database = FakeDatabase()
        self.epoch._database = self.database
        self.epoch._collection = self.collection
        self.epoch._migration_authorizer = authorize

    async def provision(self):
        await self.epoch.provision_migration_epoch(
            tenant_id="tenant", actor_id="owner",
        )

    async def test_explicit_operator_authority_and_initial_epoch(self):
        await self.provision()
        self.assertEqual(self.calls, [{
            "tenant_id": "tenant", "actor_id": "owner",
            "database_name": "canonical",
            "purpose": "quiescent-initial-epoch-v1",
        }])
        doc = next(iter(self.collection.docs.values()))
        self.assertEqual(doc["epoch"], 2)
        self.assertEqual(doc["phase"], "stable")
        self.assertIsNone(doc["writer_token"])

    async def test_standalone_or_secondary_denied_before_operator_callback(self):
        for hello in (
            {"isWritablePrimary": True},
            {"setName": "rs0", "isWritablePrimary": False},
            {"setName": "rs0", "isWritablePrimary": 1},
        ):
            with self.subTest(hello=hello):
                self.database.hello = hello
                with self.assertRaisesRegex(MongoSourceEpochError, "replica-set primary"):
                    await self.provision()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.collection.calls, 0)

    async def test_untrusted_replica_set_name_rejected_before_operator_authority(self):
        class ForgedName(str):
            def __bool__(self):
                return True

        for set_name in (ForgedName("rs0"), "rs\\x00evil", "rs\\nother",
                         "r" * 129, "rs\\ud800", ""):
            with self.subTest(repr=repr(set_name)):
                self.database.hello = {
                    "setName": set_name, "isWritablePrimary": True,
                }
                with self.assertRaises(MongoSourceEpochError):
                    await self.provision()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.collection.calls, 0)

    async def test_primary_probe_error_redacted(self):
        self.database.error = RuntimeError("secret mongo credentials")
        with self.assertRaises(MongoSourceEpochError) as caught:
            await self.provision()
        self.assertNotIn("secret", str(caught.exception))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.collection.calls, 0)

    async def test_unconfigured_denied_without_writes(self):
        self.epoch._migration_authorizer = None
        with self.assertRaisesRegex(MongoSourceEpochError, "authority required"):
            await self.provision()
        self.assertEqual(self.collection.calls, 0)

    async def test_denied_or_truthy_nonboolean_denied(self):
        for decision in (False, None, 1, "yes"):
            with self.subTest(decision=decision):
                self.authorized = decision
                with self.assertRaises(MongoSourceEpochError):
                    await self.provision()
        self.assertEqual(self.collection.calls, 0)

    async def test_operator_error_redacted(self):
        self.failure = RuntimeError("private migration key")
        with self.assertRaises(MongoSourceEpochError) as caught:
            await self.provision()
        self.assertNotIn("private", str(caught.exception))
        self.assertEqual(self.collection.calls, 0)

    async def test_duplicate_cannot_reset_existing_epoch(self):
        await self.provision()
        with self.assertRaises(MongoSourceEpochError):
            await self.provision()
        self.assertEqual(self.collection.calls, 2)
        self.assertEqual(len(self.collection.docs), 1)

    async def test_uncertain_write_does_not_retry(self):
        self.collection.failure = TimeoutError("possibly committed")
        with self.assertRaises(MongoSourceEpochError):
            await self.provision()
        self.assertEqual(self.collection.calls, 1)

    async def test_bad_actor_scope_denied_before_authority(self):
        with self.assertRaises(MongoSourceEpochError):
            await self.epoch.provision_migration_epoch(
                tenant_id="tenant", actor_id="bad\x00owner",
            )
        self.assertEqual(self.calls, [])
        self.assertEqual(self.collection.calls, 0)

    async def test_authorizer_timeout_is_bounded(self):
        self.wait = asyncio.Event()
        task = asyncio.create_task(self.provision())
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.collection.calls, 0)


if __name__ == "__main__":
    unittest.main()
