"""Sanctuary projection must obey live owner, version and source-use fences."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.dragon_checkpoint_replica import checkpoint_fields
from core.dragon_crawler import CrawlerError, DragonCrawlerApplication

from test_ai_webcrawler_dragon_adaptive_instruction_guard import (
    BASE, ROBOTS, ScriptedFetcher, make_run, step,
)

SCOPE = {"tenant_id": "tenant", "owner_id": "owner"}
BODY = ("Orbital mechanics uses eccentricity, angular momentum and gravitational constants "
        "to calculate trajectories. Measurements include velocity vectors, inclination, "
        "periapsis coordinates, observation uncertainties and numerical integration.")


def fixture():
    transport = ScriptedFetcher({
        BASE+"/robots.txt": (200, "text/plain", ROBOTS, {}),
        BASE+"/first": (200, "text/html", ("<html><p>"+BODY+"</p></html>").encode(), {}),
    })
    run, at = make_run(transport, strategy="companion")
    step(run, at+1)
    step(run, at+4)
    snapshot = run.snapshot()
    assert len(snapshot["sources"]) == 1
    binding = snapshot["binding"]
    row = {"_id": "session", **SCOPE, "status": "completed", "version": 7,
           "consent_expires_at": datetime.fromtimestamp(binding["consent"]["expires_at"], timezone.utc),
           "consent": binding["consent"], "request": binding["request"],
           "request_digest": binding["request_digest"], **checkpoint_fields(snapshot)}
    return row, datetime.fromtimestamp(at+5, timezone.utc)


def application(row, *, fence=True):
    app = object.__new__(DragonCrawlerApplication)
    app.sessions = Mock()
    cursor = app.sessions.find.return_value
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.max_time_ms.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[{"_id": row["_id"], "version": row["version"]}])
    app.sessions.find_one = AsyncMock(side_effect=[row, {"_id": row["_id"]} if fence else None])
    app.sessions.update_one = AsyncMock()
    return app


class SanctuaryBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_capture_is_qualified_without_any_storage_write(self):
        row, now = fixture()
        app = application(row)
        with patch("core.dragon_crawler._now", return_value=now):
            result = await app.companion_sanctuary(SCOPE)
        self.assertEqual(result["eligible_expeditions"], 1)
        self.assertEqual(result["credited_sources"], 1)
        self.assertEqual(result["contributing_expeditions"], 1)
        self.assertTrue(result["current_consent_only"])
        self.assertNotIn(BODY, str(result))
        app.sessions.update_one.assert_not_awaited()
        for call in app.sessions.find_one.await_args_list:
            self.assertEqual(call.args[0]["tenant_id"], SCOPE["tenant_id"])
            self.assertEqual(call.args[0]["owner_id"], SCOPE["owner_id"])
            self.assertEqual(call.args[0]["version"], 7)

    async def test_withdrawn_source_cannot_contribute(self):
        row, now = fixture()
        source_id = next(iter(row["snapshot"]["sources"]))
        row["source_use_policies"] = {source_id: {
            "version": 1, "enabled": False, "max_age_seconds": 86400, "changed_at": now.isoformat()}}
        app = application(row)
        with patch("core.dragon_crawler._now", return_value=now):
            result = await app.companion_sanctuary(SCOPE)
        self.assertEqual(result["candidate_sources"], 0)
        self.assertEqual(result["collection_index"], 0)
        self.assertEqual(result["source_refs"], [])

    async def test_concurrent_revision_disallows_return_of_old_collection(self):
        row, now = fixture()
        app = application(row, fence=False)
        with patch("core.dragon_crawler._now", return_value=now):
            with self.assertRaises(CrawlerError) as caught:
                await app.companion_sanctuary(SCOPE)
        self.assertEqual(caught.exception.code, "crawler_sanctuary_changed")
        self.assertEqual(caught.exception.status, 409)
        app.sessions.update_one.assert_not_awaited()

    async def test_wrong_snapshot_scope_is_excluded_not_promoted(self):
        row, now = fixture()
        row = copy.deepcopy(row)
        row["request_digest"] = "0" * 64
        app = application(row)
        with patch("core.dragon_crawler._now", return_value=now):
            result = await app.companion_sanctuary(SCOPE)
        self.assertEqual(result["unqualified_expeditions"], 1)
        self.assertEqual(result["credited_sources"], 0)
        app.sessions.update_one.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
