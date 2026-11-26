"""Exact-current same-row repair; corrupted or stale replicas never roll back."""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from core.dragon_checkpoint_replica import (
    CheckpointReplicaError, checkpoint_fields, decode_exact_replica, verify_primary,
)
from core.dragon_crawler import CrawlerError, DragonCrawlerApplication
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

SCOPE = {"tenant_id": "tenant", "owner_id": "owner"}


def fixture():
    now = datetime.now(timezone.utc)
    consent = {"consent_id": "replica-fixture", "capture_acknowledged": True,
               "source_rights_acknowledged": True, "expires_at": (now + timedelta(hours=1)).timestamp()}
    request = CrawlRequest(seed_urls=("https://example.com/orbital",),
                           allowed_hosts=("example.com",))
    run = CrawlRun.create(request, scope=SCOPE, consent=consent, now=now.timestamp())
    snapshot = run.snapshot()
    fields = checkpoint_fields(snapshot)
    row = {
        "_id": "session", **SCOPE, "status": "queued", "version": 7, "worker_epoch": 3,
        "request": request.as_dict(), "request_digest": snapshot["binding"]["request_digest"],
        "consent": consent, "consent_expires_at": now + timedelta(hours=1),
        "automation": {"enabled": False, "epoch": 2}, **fields,
    }
    return run, row


def app_for(rows, *, modified=1):
    app = object.__new__(DragonCrawlerApplication)
    app.sessions = Mock()
    app.sessions.find_one = AsyncMock(side_effect=rows)
    app.sessions.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=modified))
    app._admit = AsyncMock(return_value={"receipt_id": "fixture-admission"})
    return app


class ReplicaCodecTests(unittest.TestCase):
    def test_round_trip_is_exact_and_bounded(self):
        _, row = fixture()
        snapshot = row["snapshot"]
        self.assertTrue(row["checkpoint_identity"]["replica_available"])
        restored = decode_exact_replica(row["checkpoint_replica"], row["checkpoint_identity"])
        self.assertEqual(restored, snapshot)
        verify_primary(restored, row["checkpoint_identity"])
        self.assertEqual(CrawlRun.from_snapshot(restored).snapshot(), snapshot)

    def test_reconstruct_only_originally_admitted_duplicate(self):
        from core.dragon_checkpoint_replica import reconstruct_exact_replica
        _,row=fixture()
        witness=copy.deepcopy(row["checkpoint_identity"])
        encoded=reconstruct_exact_replica(row["snapshot"],witness)
        verify_primary(decode_exact_replica(encoded,witness),witness)
        no_replica={**witness,"replica_available":False,"reason":"replica_capacity"}
        with self.assertRaises(CheckpointReplicaError):
            reconstruct_exact_replica(row["snapshot"],no_replica)
        altered=copy.deepcopy(row["snapshot"])
        altered["sequence"]+=1
        with self.assertRaises(CheckpointReplicaError):
            reconstruct_exact_replica(altered,witness)

    def test_stale_or_trailing_replica_cannot_replace_current(self):
        run, row = fixture()
        run.pause()
        newer = checkpoint_fields(run.snapshot())
        with self.assertRaises(CheckpointReplicaError):
            decode_exact_replica(row["checkpoint_replica"], newer["checkpoint_identity"])
        altered = base64.b64encode(base64.b64decode(row["checkpoint_replica"]) + b"junk").decode()
        with self.assertRaises(CheckpointReplicaError):
            decode_exact_replica(altered, row["checkpoint_identity"])

    def test_redundancy_is_not_available_if_exact_write_envelope_is_exhausted(self):
        _, row = fixture()
        result = checkpoint_fields(row["snapshot"], accompanying={"extra": "x" * (4 * 1024 * 1024)})
        self.assertFalse(result["checkpoint_identity"]["replica_available"])
        self.assertIsNone(result["checkpoint_replica"])


class ExactCheckpointRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_corrupt_primary_repaired_under_exact_idle_cas(self):
        _, row = fixture()
        damaged = copy.deepcopy(row)
        damaged["snapshot"]["sequence"] += 1
        repaired = {**row, "version": 8}
        app = app_for([damaged, repaired])
        result = await app._owned(SCOPE, "session")
        self.assertEqual(result["snapshot"], row["snapshot"])
        self.assertEqual(result["version"], 8)
        predicate, update = app.sessions.update_one.await_args.args
        self.assertEqual(predicate["version"], 7)
        self.assertEqual(predicate["worker_epoch"], 3)
        self.assertIsNone(predicate["worker_token"])
        self.assertIsNone(predicate["lease_until"])
        self.assertEqual(predicate["checkpoint_identity"], row["checkpoint_identity"])
        self.assertEqual(update["$set"]["snapshot"], row["snapshot"])
        self.assertFalse(update["$set"]["checkpoint_repair"]["ancestor_rollback"])
        self.assertFalse(update["$set"]["checkpoint_repair"]["worker_restarted"])
        self.assertNotIn("automation", update["$set"])
        app._admit.assert_awaited_once()

    async def test_active_worker_and_expired_consent_are_never_repaired(self):
        _, row = fixture()
        for overrides in (
            {"status": "running", "worker_token": "worker"},
            {"consent_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)},
        ):
            damaged = {**copy.deepcopy(row), **overrides}
            damaged["snapshot"]["sequence"] += 1
            app = app_for([damaged])
            with self.assertRaises(CrawlerError) as ctx:
                await app._owned(SCOPE, "session")
            self.assertEqual(ctx.exception.code, "crawler_checkpoint_unrecoverable")
            app._admit.assert_not_awaited()
            app.sessions.update_one.assert_not_awaited()

    async def test_concurrent_change_wins_and_uncommitted_copy_not_returned(self):
        _, row = fixture()
        damaged = copy.deepcopy(row)
        damaged["snapshot"]["sequence"] += 1
        app = app_for([damaged], modified=0)
        with self.assertRaises(CrawlerError) as ctx:
            await app._owned(SCOPE, "session")
        self.assertEqual(ctx.exception.code, "crawler_conflict")
        self.assertEqual(app.sessions.find_one.await_count, 1)

    async def test_valid_primary_does_not_need_replica_or_storage_write(self):
        _, row = fixture()
        row["checkpoint_replica"] = "corrupt"
        app = app_for([row])
        self.assertEqual(await app._owned(SCOPE, "session"), row)
        app._admit.assert_not_awaited()
        app.sessions.update_one.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
