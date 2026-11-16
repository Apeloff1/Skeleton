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


class PeerAcquisitionGateTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, *, holds=(), excluded=0, capped=False):
        app = object.__new__(DragonCrawlerApplication)
        app.acquisition_hold_catalog = AsyncMock(return_value={
            "capacity_reached": capped, "excluded_sessions": excluded,
            "holds": [{"host": host} for host in holds]})
        return app, {"_id": "current", "request": {"allowed_hosts": ["example.com"]}}

    async def test_overlapping_peer_hold_stops_dispatch(self):
        app, row = self.fixture(holds=("example.com",))
        with self.assertRaises(CrawlerError) as caught:
            await app._guard_peer_acquisition(SCOPE, row)
        self.assertEqual(caught.exception.code, "crawler_peer_acquisition_held")
        app.acquisition_hold_catalog.assert_awaited_once_with(
            SCOPE, peer_hosts=("example.com",), exclude_session="current")

    async def test_independent_host_does_not_create_a_hold(self):
        app, row = self.fixture(holds=("example.org",))
        await app._guard_peer_acquisition(SCOPE, row)

    async def test_incomplete_or_unavailable_peer_audit_fails_closed(self):
        for options in ({"excluded": 1}, {"capped": True}):
            app, row = self.fixture(**options)
            with self.assertRaises(CrawlerError) as caught:
                await app._guard_peer_acquisition(SCOPE, row)
            self.assertEqual(caught.exception.code, "crawler_peer_acquisition_unavailable")
        app, row = self.fixture()
        app.acquisition_hold_catalog.side_effect = TimeoutError()
        with self.assertRaises(CrawlerError) as caught:
            await app._guard_peer_acquisition(SCOPE, row)
        self.assertEqual(caught.exception.status, 503)

    async def test_cancelled_peer_retains_observed_active_hold(self):
        fixture = AcquisitionHoldCatalogTests()
        row, now = fixture.hold_fixture()
        row["status"] = "cancelled"
        app = fixture.app_for([row])
        with patch("core.dragon_crawler._now", return_value=now):
            report = await app.acquisition_hold_catalog(
                SCOPE, peer_hosts=("example.com",), exclude_session="current")
        self.assertEqual(report["qualified_sessions"], 1)
        self.assertEqual(report["holds"][0]["host"], "example.com")
        self.assertEqual(app.sessions.find.call_args.args[0]["status"], {"$ne": "deleted"})

    async def test_peer_catalogue_queries_are_owner_and_host_scoped(self):
        fixture = AcquisitionHoldCatalogTests()
        row, now = fixture.hold_fixture()
        app = fixture.app_for([row])
        with patch("core.dragon_crawler._now", return_value=now):
            await app.acquisition_hold_catalog(SCOPE, peer_hosts=("example.com",),
                                               exclude_session="current")
        for call in app.sessions.find.call_args_list:
            query = call.args[0]
            self.assertEqual(query["tenant_id"], SCOPE["tenant_id"])
            self.assertEqual(query["owner_id"], SCOPE["owner_id"])
            self.assertEqual(query["request.allowed_hosts"], {"$in": ["example.com"]})
            self.assertEqual(query["_id"], {"$ne": "current"})


class PublisherIntentCustodyTests(unittest.IsolatedAsyncioTestCase):
    async def witnessed_row(self):
        from core.dragon_crawler import (
            _digest, _operation, _publisher_creation_body,
        )
        from skeleton.ai.webcrawler.operations import CrawlRequest

        fixture = PublisherIntakeTests()
        app, body = fixture.setup_intake()
        await app.create_publisher_intake(SCOPE, body)
        request_body = app.create.await_args.args[1]
        normalized = _publisher_creation_body(request_body, _operation(body["idempotency_key"]))
        digest = _digest(normalized)
        identifier = "publisher-session"
        row = {
            "_id": identifier, **SCOPE, "creation_digest": digest,
            "request": CrawlRequest(
                seed_urls=tuple(normalized["seeds"]),
                allowed_hosts=("example.com",), max_depth=0, max_requests=8,
                max_documents=1, max_response_bytes=524288,
                max_total_bytes=2 * 1024 * 1024).as_dict(),
            "consent": {"consent_id": _digest([SCOPE, identifier, digest])},
            "publisher_creation": {"schema": "skeleton.dragon.publisher-intent.v1",
                                   "body": normalized, "digest": digest},
        }
        return row

    async def test_receipt_is_bound_and_does_not_disclose_operation_key(self):
        from core.dragon_crawler import _publisher_intent_projection
        row = await self.witnessed_row()
        result = _publisher_intent_projection(SCOPE, row)
        self.assertTrue(result["operator_acknowledged"])
        self.assertFalse(result["publisher_verified"])
        self.assertFalse(result["license_verified"])
        self.assertNotIn("approved-intake", str(row["publisher_creation"]))
        self.assertNotIn("idempotency_key", result)
        self.assertNotIn("seeds", result)

    async def test_tampered_intent_scope_consent_or_budget_is_rejected(self):
        from copy import deepcopy
        from core.dragon_crawler import _publisher_intent_projection
        row = await self.witnessed_row()
        for path, value in (
            (("publisher_creation", "digest"), "0"*64),
            (("publisher_creation", "body", "max_requests"), 128),
            (("request", "max_depth"), 1),
            (("consent", "consent_id"), "0"*64),
        ):
            broken = deepcopy(row)
            target = broken
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
            with self.assertRaises(CrawlerError) as caught:
                _publisher_intent_projection(SCOPE, broken)
            self.assertEqual(caught.exception.code, "crawler_publisher_intent_invalid")
        with self.assertRaises(CrawlerError):
            _publisher_intent_projection({**SCOPE, "owner_id": "other"}, row)

    async def test_legacy_session_is_not_qualified_as_publisher_intent(self):
        from core.dragon_crawler import _publisher_intent_projection
        row = await self.witnessed_row()
        del row["publisher_creation"]
        self.assertIsNone(_publisher_intent_projection(SCOPE, row))


class PublisherCaptureReviewTests(unittest.TestCase):
    def snapshot(self, *, mime=None, inferred=False, observations=(), expiry=200):
        sources = {}
        if mime is not None:
            sources["fixture"] = {"content_type": mime, "provenance": {
                "declared_content_type": mime, "mime_inferred": inferred},
                "text": "fixture_private_text"}
        return {"binding": {"consent": {"expires_at": expiry}},
                "sources": sources, "acquisition_measurements": list(observations)}

    def test_declared_matches_are_not_protocol_or_rights_verification(self):
        from core.dragon_crawler import _publisher_capture_review
        cases = (("public_api", "application/json"), ("publisher_feed", "application/rss+xml"),
                 ("open_dataset_manifest", "text/csv"), ("licensed_public_export", "application/pdf"))
        for method, mime in cases:
            with self.subTest(method=method):
                r = _publisher_capture_review({"method": method}, self.snapshot(mime=mime), now=100)
                self.assertEqual(r["state"], "declared_type_match_only")
                self.assertEqual(r["declared_type_matches"], 1)
                for field in ("protocol_verified", "publisher_verified", "license_verified",
                              "source_use_authorized", "network_executed"):
                    self.assertIs(r[field], False)
                self.assertNotIn("fixture_private_text", str(r))

    def test_inferred_and_mismatched_representations_require_review(self):
        from core.dragon_crawler import _publisher_capture_review
        for mime, inferred in (("text/html", False), ("application/json", True)):
            r = _publisher_capture_review({"method": "public_api"},
                                          self.snapshot(mime=mime, inferred=inferred), now=100)
            self.assertEqual(r["state"], "representation_review_required")
            self.assertEqual(r["declared_type_matches"], 0)
            self.assertEqual(r["other_declared_types"] + r["inferred_or_unknown_types"], 1)

    def test_discovery_only_and_restriction_precedence(self):
        from core.dragon_crawler import _publisher_capture_review
        intent = {"method": "publisher_feed"}
        snap = self.snapshot(observations=[{"kind": "discovered", "status": 200}])
        self.assertEqual(_publisher_capture_review(intent, snap, now=100)["state"],
                         "discovery_metadata_only")
        snap["acquisition_measurements"].append({"kind": "rejected", "status": 403})
        self.assertEqual(_publisher_capture_review(intent, snap, now=100)["state"],
                         "restriction_observed")
        self.assertEqual(_publisher_capture_review(intent, snap, now=200)["state"],
                         "consent_expired")

    def test_empty_review_has_no_implied_permission(self):
        from core.dragon_crawler import _publisher_capture_review
        r = _publisher_capture_review({"method": "public_api"}, self.snapshot(), now=100)
        self.assertEqual(r["state"], "no_reviewable_capture")
        self.assertFalse(r["source_use_authorized"])


class PublisherArchivePreflightTests(unittest.TestCase):
    def fixture(self):
        source = {"source_id": "a"*64, "title": "Dataset inventory",
                  "text": "A catalog of astronomical observations and measurement dates.",
                  "content_type": "application/json",
                  "provenance": {"declared_content_type": "application/json",
                    "mime_inferred": False, "source_status": "unreviewed_external_capture",
                    "training_permission": False, "http_freshness": {
                        "private": False, "no_store": False, "sensitive_vary": False}}}
        return {"snapshot_digest": "b"*64, "state": "completed",
                "binding": {"consent": {"expires_at": 200}},
                "sources": {source["source_id"]: source}, "acquisition_measurements": []}

    def project(self, snapshot, *, status="completed", witnessed=True, policies=None):
        from core.dragon_crawler import _publisher_archive_preflight
        return _publisher_archive_preflight({"method": "public_api"}, snapshot, policies or {},
                                            status=status, now=300, witnessed=witnessed)

    def test_retained_terminal_metadata_cannot_issue_archive_or_dataset_rights(self):
        result = self.project(self.fixture())
        self.assertEqual(result["state"], "explicit_archive_grant_required")
        self.assertEqual(result["archive_policy_candidates"], 1)
        for flag in ("archive_grant_issued", "raw_dataset_verified",
                     "source_use_authorized", "network_executed"):
            self.assertIs(result[flag], False)

    def test_checkpoint_and_terminal_requirements_take_precedence(self):
        self.assertEqual(self.project(self.fixture(), witnessed=False)["state"],
                         "checkpoint_unwitnessed")
        self.assertEqual(self.project(self.fixture(), status="interrupted")["state"],
                         "terminal_capture_required")

    def test_capture_expiry_does_not_hide_prior_restriction(self):
        snapshot = self.fixture()
        snapshot["acquisition_measurements"] = [{"kind": "rejected", "status": 403}]
        self.assertEqual(self.project(snapshot)["state"], "restriction_review_required")

    def test_wrong_representation_and_missing_capture_stay_held(self):
        snapshot = self.fixture()
        snapshot["sources"]["a"*64]["provenance"]["mime_inferred"] = True
        self.assertEqual(self.project(snapshot)["state"], "representation_review_required")
        snapshot["sources"] = {}
        self.assertEqual(self.project(snapshot)["state"], "no_retained_capture")

    def test_archive_predicate_excludes_private_no_store_or_withdrawn(self):
        for field in ("private", "no_store", "sensitive_vary"):
            snapshot = self.fixture()
            snapshot["sources"]["a"*64]["provenance"]["http_freshness"][field] = True
            result = self.project(snapshot)
            self.assertEqual(result["state"], "archive_policy_held")
            self.assertEqual(result["archive_policy_candidates"], 0)
        result = self.project(self.fixture(), policies={"a"*64: {"version": 2, "enabled": False}})
        self.assertEqual(result["state"], "archive_policy_held")


class PublisherErasureTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_tombstone_removes_endpoint_bearing_receipt(self):
        app = object.__new__(DragonCrawlerApplication)
        app.sessions = Mock()
        app.sessions.find_one = AsyncMock(return_value={
            "_id": "publisher", **SCOPE, "version": 7,
            "publisher_creation": {"body": {"seeds": ["https://example.com/private-metadata"]}},
        })
        app.sessions.update_one = AsyncMock(return_value=Mock(modified_count=1))
        app.limits = Mock()
        app.limits.update_one = AsyncMock(return_value=Mock(matched_count=1))
        app._drain = AsyncMock(return_value={"active": False})
        result = await app.delete(SCOPE, "publisher", {
            "idempotency_key": "erase-publisher-fixture", "expected_version": 7,
        })
        self.assertEqual(result["status"], "deleted")
        predicate, mutation = app.sessions.update_one.await_args.args
        self.assertEqual(predicate, {"_id": "publisher", **SCOPE, "version": 7})
        self.assertEqual(mutation["$unset"]["publisher_creation"], "")
        self.assertEqual(mutation["$unset"]["snapshot"], "")
        self.assertNotIn("private-metadata", str(mutation))


class SharedAcquisitionStripeTests(unittest.IsolatedAsyncioTestCase):
    def make_app(self):
        app = object.__new__(DragonCrawlerApplication)
        app._workers = {}
        app.limits = Mock()
        app.limits.update_one = AsyncMock()
        app.limits.find_one = AsyncMock(return_value={})
        app.limits.find_one_and_update = AsyncMock(return_value={"worker_token": "token"})
        app.limits.count_documents = AsyncMock(return_value=1)
        return app

    def row(self, *hosts):
        return {"_id": "session", **SCOPE, "request": {"allowed_hosts": list(hosts)}}

    def test_canonical_stripe_identity_is_bounded_and_owner_independent(self):
        from core.dragon_crawler import _acquisition_stripes, ACQUISITION_STRIPES
        a = _acquisition_stripes(["example.com", "example.org"])
        b = _acquisition_stripes(["example.org", "example.com", "example.org"])
        self.assertEqual(a, b)
        self.assertEqual(a, tuple(sorted(set(a))))
        self.assertTrue(set(_acquisition_stripes(["example.com"])).issubset(a))
        for value in a:
            self.assertTrue(value.startswith("crawler-acquisition-v1:"))
            self.assertLess(int(value.rsplit(":", 1)[1], 16), ACQUISITION_STRIPES)
            self.assertNotIn("example", value)
        for bad in ([], ["UPPER.example"], ["a..example"], ["https://example.com"], ["x"]*17):
            with self.assertRaises(ValueError):
                _acquisition_stripes(bad)

    async def test_shared_leases_use_database_clock_and_all_admitted_stripes(self):
        from core.dragon_crawler import _acquisition_stripes, ACQUISITION_STRIPE_KIND, LEASE_SECONDS
        app = self.make_app()
        row = self.row("example.com", "example.org")
        slots = _acquisition_stripes(row["request"]["allowed_hosts"])
        await app._claim_acquisition_stripes(row, "token")
        self.assertEqual(app.limits.find_one_and_update.await_count, len(slots))
        for slot, call in zip(slots, app.limits.find_one_and_update.await_args_list, strict=True):
            query, mutation = call.args
            self.assertEqual(query["_id"], slot)
            self.assertEqual(query["kind"], ACQUISITION_STRIPE_KIND)
            self.assertIn({"$expr": {"$lte": ["$lease_until", "$$NOW"]}}, query["$or"])
            self.assertEqual(mutation[0]["$set"]["lease_until"], {"$add": ["$$NOW", LEASE_SECONDS*1000]})
            self.assertEqual(mutation[0]["$set"]["worker_token"], {"$literal": "token"})
            self.assertNotIn("owner_id", query)
            self.assertNotIn("example", str(mutation))
        app.limits.count_documents.return_value = len(slots)
        await app._assert_acquisition_stripes(row, "token")
        query = app.limits.count_documents.await_args.args[0]
        self.assertEqual(query["_id"], {"$in": list(slots)})
        self.assertEqual(query["worker_token"], "token")
        self.assertEqual(query["$expr"], {"$gt": ["$lease_until", {"$add": ["$$NOW", 15000]}]})

    async def test_shared_contention_denies_entire_slice(self):
        app = self.make_app()
        app.limits.find_one_and_update.return_value = None
        with self.assertRaises(CrawlerError) as caught:
            await app._claim_acquisition_stripes(self.row("example.com", "example.org"), "token")
        self.assertEqual(caught.exception.code, "crawler_acquisition_capacity")
        self.assertEqual(caught.exception.status, 429)
        app.limits.find_one_and_update.assert_awaited_once()

    async def test_local_undrained_worker_is_not_displaced_even_if_database_lease_expired(self):
        app = self.make_app()
        app.limits.find_one.return_value = {"worker_token": "old"}
        app._workers["old"] = (Mock(), Mock(done=Mock(return_value=False)))
        with self.assertRaises(CrawlerError) as caught:
            await app._claim_acquisition_stripes(self.row("example.com"), "token")
        self.assertEqual(caught.exception.code, "crawler_acquisition_capacity")
        app.limits.find_one_and_update.assert_not_awaited()

    async def test_missing_or_foreign_coordination_record_fails_closed(self):
        app = self.make_app()
        app.limits.find_one.return_value = None
        with self.assertRaises(CrawlerError) as caught:
            await app._claim_acquisition_stripes(self.row("example.com"), "token")
        self.assertEqual(caught.exception.status, 503)
        app.limits.find_one_and_update.assert_not_awaited()

    async def test_missing_or_expiring_stripe_prevents_transport_authority(self):
        app = self.make_app()
        app.limits.count_documents.return_value = 0
        with self.assertRaises(CrawlerError) as caught:
            await app._assert_acquisition_stripes(self.row("example.com"), "token")
        self.assertEqual(caught.exception.code, "crawler_acquisition_fenced")

    async def test_backend_fences_foreign_or_wrong_claim_receipt(self):
        app = self.make_app()
        app.limits.find_one_and_update.return_value = {"worker_token": "foreign"}
        with self.assertRaises(CrawlerError):
            await app._claim_acquisition_stripes(self.row("example.com"), "token")


class PinnedAcquisitionAuthorityTests(unittest.IsolatedAsyncioTestCase):
    def harness(self):
        source = SharedAcquisitionStripeTests().make_app().limits
        target = SharedAcquisitionStripeTests().make_app().limits
        source.update_many = AsyncMock()
        target.update_many = AsyncMock()
        app = object.__new__(DragonCrawlerApplication)
        app._workers = {}
        app.limits = target
        app._coordination_limits = source
        row = {"request": {"allowed_hosts": ["example.com"]}}
        return app, row, source, target

    async def test_distinct_storage_never_creates_second_origin_pool(self):
        app, row, source, target = self.harness()
        await app._claim_acquisition_stripes(row, "token")
        await app._assert_acquisition_stripes(row, "token")
        source.find_one_and_update.assert_awaited_once()
        source.count_documents.assert_awaited_once()
        target.update_one.assert_not_awaited()
        target.find_one_and_update.assert_not_awaited()
        target.count_documents.assert_not_awaited()

    async def test_unavailable_pinned_authority_never_falls_back(self):
        from pymongo.errors import AutoReconnect
        app, row, source, target = self.harness()
        source.update_one.side_effect = AutoReconnect("fixture")
        with self.assertRaises(AutoReconnect):
            await app._claim_acquisition_stripes(row, "token")
        target.update_one.assert_not_awaited()
        source.count_documents.side_effect = AutoReconnect("fixture")
        with self.assertRaises(AutoReconnect):
            await app._assert_acquisition_stripes(row, "token")
        target.count_documents.assert_not_awaited()

    async def test_split_store_release_discharges_only_owned_stripes(self):
        from core.dragon_crawler import ACQUISITION_STRIPE_KIND
        app, _, source, target = self.harness()
        await app._release_worker_credits("token")
        expected = {"$unset": {"worker_token": "", "active_session_id": "", "lease_until": ""}}
        source.update_many.assert_awaited_once_with(
            {"kind": ACQUISITION_STRIPE_KIND, "worker_token": "token"}, expected)
        target.update_many.assert_awaited_once_with({"worker_token": "token"}, expected)

    async def test_source_release_failure_still_releases_local_token(self):
        from pymongo.errors import AutoReconnect
        app, _, source, target = self.harness()
        source.update_many.side_effect = AutoReconnect("fixture")
        with self.assertRaises(AutoReconnect):
            await app._release_worker_credits("token")
        target.update_many.assert_awaited_once()
        self.assertEqual(target.update_many.await_args.args[0], {"worker_token": "token"})

    async def test_single_store_release_preserves_original_cleanup(self):
        app, _, source, _ = self.harness()
        app.limits = source
        await app._release_worker_credits("token")
        source.update_many.assert_awaited_once()
        self.assertEqual(source.update_many.await_args.args[0], {"worker_token": "token"})

    def test_constructor_binds_original_or_explicit_shared_authority(self):
        database = {"dragon_crawler_sessions": Mock(), "dragon_crawler_commands": Mock()}
        coordination = {"dragon_crawler_commands": Mock()}
        with patch("core.dragon_crawler.EngineClient.from_env"):
            app = DragonCrawlerApplication(database)
            self.assertIs(app._acquisition_store(), database["dragon_crawler_commands"])
            app.limits = Mock()
            self.assertIs(app._acquisition_store(), database["dragon_crawler_commands"])
            app = DragonCrawlerApplication(database, coordination_database=coordination)
            self.assertIs(app._acquisition_store(), coordination["dragon_crawler_commands"])


if __name__ == "__main__":
    unittest.main()
