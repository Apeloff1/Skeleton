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



class AcquisitionHoldCatalogTests(unittest.IsolatedAsyncioTestCase):
    def hold_fixture(self):
        transport = ScriptedFetcher({
            BASE+"/robots.txt": (200, "text/plain", ROBOTS, {}),
            BASE+"/first": (403, "text/html", b"", {}),
        })
        run, at = make_run(transport, strategy="companion")
        step(run, at+1)
        step(run, at+4)
        snapshot = run.snapshot()
        binding = snapshot["binding"]
        row = {"_id": "hold", **SCOPE, "status": "ready", "version": 3,
               "consent_expires_at": datetime.fromtimestamp(binding["consent"]["expires_at"], timezone.utc),
               "consent": binding["consent"], "request": binding["request"],
               "request_digest": binding["request_digest"], **checkpoint_fields(snapshot)}
        return row, datetime.fromtimestamp(at+5, timezone.utc)

    def app_for(self, rows, changed=False):
        app = object.__new__(DragonCrawlerApplication)
        app.sessions = Mock()
        cursor = app.sessions.find.return_value
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.max_time_ms.return_value = cursor
        refs = [{"_id": r["_id"], "version": r["version"]} for r in rows]
        cursor.to_list = AsyncMock(side_effect=[refs, [] if changed else refs])
        app.sessions.find_one = AsyncMock(side_effect=rows)
        app.sessions.update_one = AsyncMock()
        return app

    async def test_two_witnessed_grants_aggregate_without_writes_or_urls(self):
        row, now = self.hold_fixture()
        duplicate = {**row, "_id": "hold2"}
        app = self.app_for([row, duplicate])
        with patch("core.dragon_crawler._now", return_value=now):
            result = await app.acquisition_hold_catalog(SCOPE)
        self.assertEqual(result["qualified_sessions"], 2)
        self.assertEqual(result["holds"][0]["observed_grants"], 2)
        self.assertEqual(result["holds"][0]["denial_statuses"], 2)
        self.assertFalse(result["dispatch_lock"])
        self.assertFalse(result["network_executed"])
        self.assertNotIn("/first", str(result))
        for call in app.sessions.find_one.await_args_list:
            self.assertEqual(call.args[0]["owner_id"], SCOPE["owner_id"])
            self.assertEqual(call.args[0]["tenant_id"], SCOPE["tenant_id"])
        app.sessions.update_one.assert_not_awaited()

    async def test_wrong_scope_binding_or_missing_witness_is_excluded(self):
        row, now = self.hold_fixture()
        bad = {**row, "request_digest": "0"*64}
        unwitnessed = {**row, "_id": "other", "checkpoint_identity": None}
        app = self.app_for([bad, unwitnessed])
        with patch("core.dragon_crawler._now", return_value=now):
            result = await app.acquisition_hold_catalog(SCOPE)
        self.assertEqual(result["excluded_sessions"], 2)
        self.assertEqual(result["holds"], [])
        app.sessions.update_one.assert_not_awaited()

    async def test_catalogue_change_fails_closed(self):
        row, now = self.hold_fixture()
        app = self.app_for([row], changed=True)
        with patch("core.dragon_crawler._now", return_value=now):
            with self.assertRaises(CrawlerError) as caught:
                await app.acquisition_hold_catalog(SCOPE)
        self.assertEqual(caught.exception.code, "crawler_hold_catalog_changed")
        app.sessions.update_one.assert_not_awaited()



class PublisherIntakeTests(unittest.IsolatedAsyncioTestCase):
    def setup_intake(self):
        app = object.__new__(DragonCrawlerApplication)
        app.acquisition_hold_catalog = AsyncMock(return_value={
            "capacity_reached": False, "excluded_sessions": 0, "holds": []})
        app.create = AsyncMock(return_value={"session_id": "publisher"})
        body = {"idempotency_key": "approved-intake", "endpoint": "https://example.com/dataset",
                "method": "public_api", "consent": True, "rights_acknowledged": True,
                "publisher_permission_acknowledged": True, "independent_resource_acknowledged": True}
        return app, body

    async def test_each_mode_queues_bounded_canonical_session(self):
        for method in ("public_api", "publisher_feed", "open_dataset_manifest", "licensed_public_export"):
            app, body = self.setup_intake()
            body["method"] = method
            result = await app.create_publisher_intake(SCOPE, body)
            self.assertEqual(result["session_id"], "publisher")
            scope, request = app.create.await_args.args
            self.assertEqual(scope, SCOPE)
            self.assertEqual(request["seeds"], [body["endpoint"]])
            self.assertEqual(request["max_depth"], 0)
            self.assertEqual(request["max_requests"], 8)
            self.assertEqual(request["max_documents"], 1)
            self.assertFalse(request["discover_sitemaps"])
            self.assertEqual(request["publisher_intake"]["method"], method)

    async def test_refuses_credentials_private_literal_and_missing_permissions(self):
        for endpoint in ("http://example.com/data", "https://user:password@example.com/data",
                         "https://127.0.0.1/data", "https://example.com/data?token=secret",
                         "https://example.com/data#fragment"):
            app, body = self.setup_intake()
            body["endpoint"] = endpoint
            with self.assertRaises(ValueError):
                await app.create_publisher_intake(SCOPE, body)
            app.create.assert_not_awaited()
        for field in ("consent", "rights_acknowledged", "publisher_permission_acknowledged",
                      "independent_resource_acknowledged"):
            app, body = self.setup_intake()
            body[field] = False
            with self.assertRaises(CrawlerError):
                await app.create_publisher_intake(SCOPE, body)
            app.create.assert_not_awaited()

    async def test_restriction_or_unqualified_audit_prevents_queue(self):
        for report in (
            {"capacity_reached": False, "excluded_sessions": 0,
             "holds": [{"host": "example.com"}]},
            {"capacity_reached": True, "excluded_sessions": 0, "holds": []},
            {"capacity_reached": False, "excluded_sessions": 1, "holds": []},
        ):
            app, body = self.setup_intake()
            app.acquisition_hold_catalog.return_value = report
            with self.assertRaises(CrawlerError) as caught:
                await app.create_publisher_intake(SCOPE, body)
            self.assertEqual(caught.exception.code, "crawler_publisher_intake_held")
            app.create.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
