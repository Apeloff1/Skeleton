"""Opt-in real Mongo replica-set custody drills; never a fake Mongo pass.

Requires a separately provisioned test replica set. No automatic migration,
production database cleanup, or fallback to standalone is permitted.
Run only with SKL_TEST_MONGO_URI and SKL_TEST_MONGO_ALLOW_DROP=1.
Each test uses a unique newly named skeleton_ci_guard_* database.
"""
from __future__ import annotations

import asyncio
import os
import unittest
from uuid import uuid4

from skeleton.persistence.mongo_source_epoch import (
    MongoCanonicalSourceEpoch, MongoSourceEpochError,
)


class LiveReplicaEpochTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        uri = os.environ.get("SKL_TEST_MONGO_URI", "")
        allow = os.environ.get("SKL_TEST_MONGO_ALLOW_DROP", "")
        if not uri or allow != "1":
            self.skipTest("live replica-set test authority not configured")
        if len(uri) > 8192:
            self.skipTest("invalid live test Mongo configuration")
        from motor.motor_asyncio import AsyncIOMotorClient
        self.client = AsyncIOMotorClient(
            uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000,
            socketTimeoutMS=3000, retryWrites=False, retryReads=False,
            appname="skeleton-guarded-epoch-live-test",
        )
        self.database_name = "skeleton_ci_guard_" + uuid4().hex
        self.database = self.client[self.database_name]
        try:
            async with asyncio.timeout(5):
                hello = await self.database.command("hello")
            if (type(hello) is not dict
                    or not hello.get("setName")
                    or hello.get("isWritablePrimary") is not True):
                self.skipTest("authenticated replica-set primary not available")
        except Exception:
            self.client.close()
            self.skipTest("authenticated test replica-set primary unavailable")

        self.migration_calls = 0
        self.revocation_calls = 0

        async def authorize_migration(**kwargs):
            self.migration_calls += 1
            return (
                kwargs == {
                    "tenant_id": "ci-tenant", "actor_id": "ci-owner",
                    "database_name": self.database_name,
                    "purpose": "quiescent-initial-epoch-v1",
                }
            )

        async def authorize_revocation(**kwargs):
            self.revocation_calls += 1
            return (
                kwargs["tenant_id"] == "ci-tenant"
                and kwargs["actor_id"] == "ci-owner"
                and kwargs["reason_code"] == "operator-revoke"
                and type(kwargs["expected_epoch"]) is int
            )

        self.epoch = MongoCanonicalSourceEpoch(
            self.database, migration_authorizer=authorize_migration,
            revocation_authorizer=authorize_revocation,
        )
        self.scope = {
            "tenant_id": "ci-tenant", "actor_id": "ci-owner",
        }
        await self.epoch.provision_migration_epoch(**self.scope)

    async def asyncTearDown(self):
        client = getattr(self, "client", None)
        if client is None:
            return
        try:
            db_name = getattr(self, "database_name", "")
            if (db_name.startswith("skeleton_ci_guard_")
                    and len(db_name) == len("skeleton_ci_guard_") + 32
                    and os.environ.get("SKL_TEST_MONGO_ALLOW_DROP") == "1"):
                await client.drop_database(db_name)
        finally:
            client.close()

    async def read(self, epoch=None):
        return await (epoch or self.epoch).read_epoch(
            **self.scope, context_id="ci-context",
        )

    async def test_initial_epoch_is_linearizable_and_majority_durable(self):
        self.assertEqual(await self.read(), 2)
        self.assertEqual(self.migration_calls, 1)
        restarted = MongoCanonicalSourceEpoch(self.database)
        self.assertEqual(await self.read(restarted), 2)

    async def test_writer_phase_blocks_reader_and_stable_epoch_advances(self):
        self.assertEqual(await self.read(), 2)
        async with self.epoch.writer(**self.scope):
            with self.assertRaises(MongoSourceEpochError):
                await self.read()
            await self.database.get_collection("test_payload").insert_one(
                {"_id": "written", "value": 1}
            )
        self.assertEqual(await self.read(), 4)
        restarted = MongoCanonicalSourceEpoch(self.database)
        self.assertEqual(await self.read(restarted), 4)

    async def test_second_process_style_writer_is_rejected(self):
        other = MongoCanonicalSourceEpoch(self.database)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def hold_writer():
            async with self.epoch.writer(**self.scope):
                entered.set()
                await release.wait()

        first = asyncio.create_task(hold_writer())
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            with self.assertRaises(MongoSourceEpochError):
                async with other.writer(**self.scope):
                    self.fail("concurrent canonical writer admitted")
        finally:
            release.set()
            await asyncio.wait_for(first, timeout=5)
        self.assertEqual(await self.read(), 4)

    async def test_failed_writer_remains_quarantined_across_restart(self):
        with self.assertRaisesRegex(RuntimeError, "simulated crash"):
            async with self.epoch.writer(**self.scope):
                await self.database.get_collection("test_payload").insert_one(
                    {"_id": "partial", "value": 1}
                )
                raise RuntimeError("simulated crash")
        with self.assertRaises(MongoSourceEpochError):
            await self.read()
        restarted = MongoCanonicalSourceEpoch(self.database)
        with self.assertRaises(MongoSourceEpochError):
            await self.read(restarted)
        with self.assertRaises(MongoSourceEpochError):
            async with restarted.writer(**self.scope):
                self.fail("writer recovered odd epoch automatically")

    async def test_operator_revocation_is_terminal_across_restart(self):
        self.assertEqual(await self.read(), 2)
        self.assertEqual(await self.epoch.revoke_actor(
            **self.scope, expected_epoch=2, reason_code="operator-revoke",
        ), 3)
        self.assertEqual(self.revocation_calls, 1)
        with self.assertRaises(MongoSourceEpochError):
            await self.read()
        restarted = MongoCanonicalSourceEpoch(self.database)
        with self.assertRaises(MongoSourceEpochError):
            await self.read(restarted)
        with self.assertRaises(MongoSourceEpochError):
            async with restarted.writer(**self.scope):
                self.fail("revoked actor admitted a writer")


if __name__ == "__main__":
    unittest.main()
