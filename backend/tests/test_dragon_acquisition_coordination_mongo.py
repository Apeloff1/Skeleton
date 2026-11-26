"""Opt-in real Mongo qualification of shared Dragon acquisition leases.

Only disposable fixture namespaces are created and removed. No crawler
transport, network target, application database, or production data is used.
Set SKL_DRAGON_COORDINATION_TEST_MONGO_URL to a disposable Mongo fixture.
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient
from core.dragon_crawler import (
    ACQUISITION_STRIPE_KIND, CrawlerError, DragonCrawlerApplication,
    _acquisition_stripes,
)


@unittest.skipUnless(os.getenv("SKL_DRAGON_COORDINATION_TEST_MONGO_URL"),
                     "requires disposable Mongo coordination fixture")
class SharedMongoAcquisitionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        uri = os.environ["SKL_DRAGON_COORDINATION_TEST_MONGO_URL"]
        self.clients = [AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000,
                        socketTimeoutMS=10000, w="majority", journal=True)
                        for _ in range(2)]
        for client in self.clients:
            self.addCleanup(client.close)
        await self.clients[0].admin.command("ping")
        prefix = "dragon_coord_fixture_" + uuid4().hex
        self.names = [prefix + suffix for suffix in ("_authority", "_first", "_second")]
        for name in self.names:
            self.addAsyncCleanup(self.clients[0].drop_database, name)
        shared = [client[self.names[0]] for client in self.clients]
        self.apps = [DragonCrawlerApplication(client[self.names[i + 1]],
                     coordination_database=shared[i])
                     for i, client in enumerate(self.clients)]
        self.store = shared[0]["dragon_crawler_commands"]
        self.row = {"request": {"allowed_hosts": ["example.com"]}}
        self.slot = _acquisition_stripes(self.row["request"]["allowed_hosts"])[0]

    async def test_independent_connections_and_storage_databases_share_one_lease(self):
        first, second = self.apps
        outcomes = await asyncio.gather(
            first._claim_acquisition_stripes(self.row, "first"),
            second._claim_acquisition_stripes(self.row, "second"),
            return_exceptions=True,
        )
        self.assertEqual(sum(value is None for value in outcomes), 1)
        errors = [value for value in outcomes if value is not None]
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], CrawlerError)
        self.assertEqual(errors[0].code, "crawler_acquisition_capacity")
        winner = 0 if outcomes[0] is None else 1
        loser = 1 - winner
        tokens = ["first", "second"]
        await self.apps[winner]._assert_acquisition_stripes(self.row, tokens[winner])
        with self.assertRaises(CrawlerError):
            await self.apps[loser]._assert_acquisition_stripes(self.row, tokens[loser])
        await self.apps[loser]._release_worker_credits(tokens[loser])
        await self.apps[winner]._assert_acquisition_stripes(self.row, tokens[winner])
        row = await self.store.find_one({"_id": self.slot})
        self.assertEqual(row["kind"], ACQUISITION_STRIPE_KIND)
        self.assertEqual(row["worker_token"], tokens[winner])
        for app in self.apps:
            self.assertEqual(await app.limits.count_documents(
                {"kind": ACQUISITION_STRIPE_KIND}), 0)
        await self.apps[winner]._release_worker_credits(tokens[winner])
        await self.apps[loser]._claim_acquisition_stripes(self.row, tokens[loser])
        await self.apps[loser]._assert_acquisition_stripes(self.row, tokens[loser])

    async def test_server_expiry_fences_old_token_and_token_safe_reacquisition(self):
        first, second = self.apps
        await first._claim_acquisition_stripes(self.row, "first")
        # Explicit expiry in a disposable fixture avoids a real lease wait.
        await self.store.update_one(
            {"_id": self.slot, "worker_token": "first"},
            {"$set": {"lease_until": datetime.now(timezone.utc) - timedelta(days=1)}})
        with self.assertRaises(CrawlerError) as caught:
            await first._assert_acquisition_stripes(self.row, "first")
        self.assertEqual(caught.exception.code, "crawler_acquisition_fenced")
        await second._claim_acquisition_stripes(self.row, "second")
        await first._release_worker_credits("first")
        await second._assert_acquisition_stripes(self.row, "second")

    async def test_all_stripes_must_be_held_before_transport(self):
        first = self.apps[0]
        hosts = ["example.com", "example.org", "example.net"]
        row = {"request": {"allowed_hosts": hosts}}
        slots = _acquisition_stripes(hosts)
        self.assertGreater(len(slots), 1)
        await first._claim_acquisition_stripes(row, "first")
        await first._assert_acquisition_stripes(row, "first")
        await self.store.update_one({"_id": slots[-1]},
                                    {"$unset": {"worker_token": "", "lease_until": ""}})
        with self.assertRaises(CrawlerError) as caught:
            await first._assert_acquisition_stripes(row, "first")
        self.assertEqual(caught.exception.code, "crawler_acquisition_fenced")


if __name__ == "__main__":
    unittest.main()
