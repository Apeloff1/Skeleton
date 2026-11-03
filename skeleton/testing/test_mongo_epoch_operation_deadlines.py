"""Bounded majority-CAS mutation drills: timeout is never a successful write.

No real database, provisioning, or network access is performed by these tests.
Real replica-set durability must still be qualified separately.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
import unittest
from unittest.mock import patch

from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, MongoSourceEpochError,
)


class StalledCollection:
    def __init__(self):
        self.phase = "stable"
        self.epoch = 2
        self.writer_token = None
        self.stall = False
        self.stall_on = ""
        self.calls = []
        self.release = asyncio.Event()

    async def _wait(self, name):
        self.calls.append(name)
        if self.stall and self.stall_on == name:
            await self.release.wait()

    async def insert_one(self, document):
        await self._wait("insert")
        self.phase = document["phase"]
        self.epoch = document["epoch"]
        return object()

    async def find_one_and_update(self, query, update, *, return_document):
        operation = "complete" if query.get("phase") == "writing" else (
            "revoke" if update.get("$set", {}).get("phase") == "revoked" else "admit"
        )
        await self._wait(operation)
        if query.get("phase") != self.phase:
            return None
        if "epoch" in query and query["epoch"] != self.epoch:
            return None
        if "writer_token" in query and query["writer_token"] != self.writer_token:
            return None
        self.epoch += update.get("$inc", {}).get("epoch", 0)
        self.phase = update.get("$set", {}).get("phase", self.phase)
        self.writer_token = update.get("$set", {}).get("writer_token", self.writer_token)
        return {
            "phase": self.phase, "epoch": self.epoch,
            "writer_token": self.writer_token,
            "revoked_reason": update.get("$set", {}).get("revoked_reason"),
        }


class MutationDeadlineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.collection = StalledCollection()
        self.epoch = object.__new__(MongoCanonicalSourceEpoch)
        self.epoch._collection = self.collection
        self.epoch._active = ContextVar("test_mongo_writer", default=None)
        self.epoch._revocation_authorizer = self._authorize
        self.epoch._migration_authorizer = self._authorize
        self.epoch._database = type("DB", (), {
            "name": "test", "command": self._hello,
        })()
        self.limit = patch(
            "skeleton.persistence.mongo_source_epoch."
            "_EPOCH_MUTATION_DEADLINE_SECONDS", 0.02
        )
        self.limit.start()
        self.addCleanup(self.limit.stop)

    async def _hello(self, command):
        return {"setName": "test-rs", "isWritablePrimary": True}

    async def _authorize(self, **kwargs):
        return True

    async def test_admission_timeout_is_denied_without_body_execution(self):
        self.collection.stall = True
        self.collection.stall_on = "admit"
        entered = False
        with self.assertRaises(MongoSourceEpochError):
            async with self.epoch.writer(tenant_id="tenant", actor_id="actor"):
                entered = True
        self.assertFalse(entered)
        self.assertEqual(self.collection.calls, ["admit"])
        self.assertEqual(self.collection.phase, "stable")

    async def test_completion_timeout_never_reports_success(self):
        self.collection.stall = True
        self.collection.stall_on = "complete"
        with self.assertRaisesRegex(MongoSourceEpochError, "quarantined"):
            async with self.epoch.writer(tenant_id="tenant", actor_id="actor"):
                self.epoch.require_actor_writer(tenant_id="tenant", actor_id="actor")
        self.assertEqual(self.collection.phase, "writing")
        self.assertEqual(self.collection.epoch, 3)
        with self.assertRaises(MongoSourceEpochError):
            self.epoch.require_actor_writer(tenant_id="tenant", actor_id="actor")

    async def test_revocation_timeout_is_uncertain_and_not_retried(self):
        self.collection.stall = True
        self.collection.stall_on = "revoke"
        with self.assertRaisesRegex(MongoSourceEpochError, "uncertain"):
            await self.epoch.revoke_actor(
                tenant_id="tenant", actor_id="actor", expected_epoch=2,
                reason_code="operator-revoke",
            )
        self.assertEqual(self.collection.calls, ["revoke"])
        self.assertEqual(self.collection.phase, "stable")

    async def test_provision_timeout_never_retries_or_claims_success(self):
        self.collection.stall = True
        self.collection.stall_on = "insert"
        with self.assertRaisesRegex(MongoSourceEpochError, "migration unavailable"):
            await self.epoch.provision_migration_epoch(
                tenant_id="tenant", actor_id="actor",
            )
        self.assertEqual(self.collection.calls, ["insert"])

    async def test_normal_writer_still_advances_odd_to_even(self):
        async with self.epoch.writer(tenant_id="tenant", actor_id="actor"):
            self.assertEqual(self.collection.phase, "writing")
            self.assertEqual(self.collection.epoch, 3)
        self.assertEqual(self.collection.phase, "stable")
        self.assertEqual(self.collection.epoch, 4)
        self.assertEqual(self.collection.calls, ["admit", "complete"])

    async def test_operator_revocation_is_terminal_after_normal_cas(self):
        result = await self.epoch.revoke_actor(
            tenant_id="tenant", actor_id="actor", expected_epoch=2,
            reason_code="operator-revoke",
        )
        self.assertEqual(result, 3)
        self.assertEqual(self.collection.phase, "revoked")
        with self.assertRaises(MongoSourceEpochError):
            async with self.epoch.writer(tenant_id="tenant", actor_id="actor"):
                self.fail("revoked actor was admitted")

    async def test_cancelled_writer_leaves_quarantine(self):
        entered = asyncio.Event()
        async def cancelled():
            async with self.epoch.writer(tenant_id="tenant", actor_id="actor"):
                entered.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(cancelled())
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.collection.phase, "writing")
        self.assertEqual(self.collection.epoch, 3)


if __name__ == "__main__":
    unittest.main()
