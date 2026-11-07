"""Public ActivityStreams navigation through the existing canonical crawler."""
from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import CrawlPolicy, FetchResponse
from skeleton.ai.webcrawler.federated_activity import (
    ACTIVITY_MEDIA_TYPES, ActivityDiscoveryError, discover_activity_page,
)
from skeleton.ai.webcrawler.structured_discovery import parse_structured_discovery
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

URL = "https://example.com/community/collection"
PUBLIC = "https://www.w3.org/ns/activitystreams#Public"
CONTEXT = "https://www.w3.org/ns/activitystreams"
PRIVATE = "https://example.com/people/alice/followers"
OUTSIDE = "https://outside.example.net/hidden"
POLICY = CrawlPolicy(allowed_hosts=frozenset({"example.com", "outside.example.net"}))
PAGE = {
    "@context": CONTEXT,
    "type": "OrderedCollectionPage", "id": URL,
    "next": {"type": "Link", "href": "/community/collection?page=2"},
    "prev": "/community/collection?page=0",
    "orderedItems": [
        {"type": "Article", "id": "https://example.com/articles/wing",
         "to": [PUBLIC], "name": "Aviation research"},
        {"type": "Note", "url": "/notes/open", "to": PUBLIC},
        {"type": "Note", "url": "/notes/private", "to": [PRIVATE]},
        {"type": "Document", "url": OUTSIDE, "to": PUBLIC},
        {"type": "Create", "object": {"type": "Note", "url": OUTSIDE,
                                    "to": PUBLIC}, "to": PUBLIC},
        {"type": "Article", "url": "/users/alice/inbox", "to": PUBLIC},
        {"type": "Note", "url": "/notes/hidden", "to": PUBLIC,
         "bcc": ["https://example.com/private"]},
    ],
    "actor": OUTSIDE, "inbox": OUTSIDE, "outbox": OUTSIDE,
    "followers": OUTSIDE, "first": OUTSIDE, "last": OUTSIDE,
}


def direct(doc, *, mime="application/activity+json", max_links=32):
    return discover_activity_page(
        json.dumps(doc).encode(), media_type=mime,
        document_url=URL, policy=POLICY, max_links=max_links,
    )


class ActivityCollectionTests(unittest.TestCase):
    def test_unhashable_type_fields_are_rejected_or_ignored(self):
        bad = {**PAGE, "type": ["OrderedCollectionPage"]}
        with self.assertRaises(ActivityDiscoveryError):
            direct(bad)
        bad = {**PAGE, "orderedItems": [
            {"type": ["Article"], "url": "/notes/unsafe", "to": PUBLIC},
            {"type": "Article", "url": "/notes/safe", "to": PUBLIC},
        ]}
        self.assertEqual(direct(bad).links, (
            "https://example.com/community/collection?page=2",
            "https://example.com/community/collection?page=0",
            "https://example.com/notes/safe",
        ))

    def test_public_navigation_excludes_private_actor_and_cross_origin(self):
        result = direct(PAGE)
        self.assertEqual(result.links, (
            "https://example.com/community/collection?page=2",
            "https://example.com/community/collection?page=0",
            "https://example.com/articles/wing",
            "https://example.com/notes/open",
        ))
        self.assertEqual(result.public_items, 4)
        self.assertEqual(result.examined, 6)
        self.assertTrue(result.same_origin_only)
        self.assertFalse(result.network_executed)
        self.assertFalse(result.executes_activity)
        self.assertFalse(result.grants_authority)

    def test_collection_root_only_first_page_and_next(self):
        doc = {"@context": CONTEXT, "type": "OrderedCollection",
               "first": {"type": "Link", "href": "/community/collection?page=1"},
               "last": OUTSIDE, "items": []}
        self.assertEqual(direct(doc).links, (
            "https://example.com/community/collection?page=1",
        ))

    def test_item_capacity_fails_closed(self):
        doc = {"@context": CONTEXT, "type": "CollectionPage",
               "items": [{"type": "Note", "to": PUBLIC,
                          "url": f"/notes/{i}"} for i in range(129)]}
        with self.assertRaises(ActivityDiscoveryError):
            direct(doc)

    def test_external_jsonld_context_never_loaded(self):
        with self.assertRaises(ActivityDiscoveryError):
            direct({**PAGE, "@context": [
                CONTEXT, "https://outside.example.net/evil/context",
            ]})

    def test_noncollection_activities_never_executed(self):
        for kind in ("Person", "Actor", "Create", "Follow", "Outbox", "Inbox"):
            with self.subTest(kind=kind), self.assertRaises(ActivityDiscoveryError):
                direct({"@context": CONTEXT, "type": kind, "next": "/private"})

    def test_nonfinite_and_duplicate_json_fenced(self):
        for raw in (
            b'{"@context":"https://www.w3.org/ns/activitystreams",'
            b'"type":"Collection","type":"OrderedCollection"}',
            b'{"@context":"https://www.w3.org/ns/activitystreams",'
            b'"type":"Collection","totalItems":NaN}',
        ):
            with self.subTest(raw=raw), self.assertRaises(ActivityDiscoveryError):
                discover_activity_page(
                    raw, media_type="application/activity+json",
                    document_url=URL, policy=POLICY,
                )

    def test_explicit_mimes_only(self):
        mime = "application/vnd.activitystreams+json"
        self.assertIn(mime, ACTIVITY_MEDIA_TYPES)
        self.assertEqual(direct(PAGE, mime=mime).links, direct(PAGE).links)

    def test_capped_navigation_is_visible(self):
        row = direct(PAGE, max_links=2)
        self.assertTrue(row.capped)
        self.assertEqual(len(row.links), 2)

    def test_real_structured_dispatch_has_no_retained_body(self):
        row = parse_structured_discovery(
            json.dumps(PAGE).encode(), media_type="application/activity+json",
            document_url=URL, policy=POLICY,
        )
        self.assertEqual(row.links, direct(PAGE).links)
        self.assertFalse(row.new_authority_granted)
        self.assertFalse(row.source_text_retained)


class ScriptedFetcher:
    timeout_seconds = 4
    transport_mode = "scripted_activitystreams"
    def __init__(self):
        self.calls = []
    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url == "https://example.com/robots.txt":
            return FetchResponse(url, 200, {"content-type": "text/plain"},
                                 b"User-agent: *\nAllow: /\n", time.time())
        if url == URL:
            raw = json.dumps(PAGE).encode()
            if len(raw) > max_bytes:
                raise AssertionError("scripted ActivityStreams capacity")
            return FetchResponse(url, 200,
                                 {"content-type": "application/activity+json"},
                                 raw, time.time())
        raise AssertionError("private/foreign ActivityPub URL was fetched")


class CanonicalActivityTests(unittest.TestCase):
    def test_worker_only_queues_public_same_origin_links(self):
        now = time.time()
        transport = ScriptedFetcher()
        run = CrawlRun.create(
            CrawlRequest(
                seed_urls=(URL,),
                allowed_hosts=("example.com", "outside.example.net"),
                max_depth=1, max_requests=8, max_documents=3,
                max_response_bytes=65536, max_total_bytes=131072,
            ),
            scope={"tenant_id": "tenant", "owner_id": "owner"},
            consent={"consent_id": "public-feed-rights",
                     "capture_acknowledged": True,
                     "source_rights_acknowledged": True,
                     "expires_at": now + 3600},
            now=now, fetcher=transport,
        )
        for delta in (1, 3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=now+delta):
                run.run_slice(max_steps=1, max_seconds=1,
                              authorize=lambda: None, cancelled=lambda: False,
                              on_checkpoint=lambda snap,event: None)
        snap = run.snapshot()
        self.assertEqual(snap["usage"]["requests"], 2)
        self.assertEqual(snap["usage"]["documents"], 0)
        self.assertEqual({x["url"] for x in snap["frontier"]}, set(direct(PAGE).links))
        self.assertEqual(len(transport.calls), 2)
        self.assertFalse(any(OUTSIDE in x["url"] for x in snap["frontier"]))
        self.assertEqual(CrawlRun.from_snapshot(
            snap, fetcher=transport).snapshot(), snap)


if __name__ == "__main__":
    unittest.main()
