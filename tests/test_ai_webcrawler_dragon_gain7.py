"""Wave 7: real bounded Markdown/CSV/JSON capture, header pagination and scheduling.

The complete tests drive canonical CrawlRun.run_slice, its request/byte
pre-network reservation, robots, provenance and snapshot source custody.
Scripted transport has no network, Mongo or model side effects.
"""
from __future__ import annotations

from dataclasses import replace
import json
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import (
    CrawlPolicy, FetchResponse, extract_document,
)
from skeleton.ai.webcrawler.document_formats import (
    DocumentFormatError, extract_markdown, extract_csv,
    extract_json, extract_additional_format, extract_source_code, extract_ndjson,
)
from skeleton.ai.webcrawler.bound_http import _coalesce_bounded_link_headers
from skeleton.ai.webcrawler.frontier_scheduler import choose_frontier
from skeleton.ai.webcrawler.link_header_discovery import parse_link_headers
from skeleton.ai.webcrawler.operations import (
    CrawlRequest, CrawlRun, CrawlOperationError,
)


MD = b"""# Flight Mechanics

This is a real detailed research document about archive capture and flight
mechanics for an original game engine.

[Movement chapter](/movement)
[Archive methods](https://example.com/methods)
![remote image](https://outside.example.net/image.png)
```md
[malicious ignored code](https://outside.example.net/hidden)
```
Here is `[ignored inline](https://outside.example.net/inline)` text.
"""
CSV = b"""title,category,notes
Pilot,archive,Verified by a human later
Wings,physics,Model is not permitted to trust this source
"""
JSON = json.dumps({
    "title": "Original Engine API",
    "collection": [
        {"id": 1, "topic": "archive capture and aircraft"},
        {"id": 2, "topic": "motion design"},
    ],
    "access_token": "THIS_SHOULD_NEVER_BE_IN_EVIDENCE",
    "url": "https://outside.example.net/forbidden",
}).encode()
SOURCE_CODE = b"def simulate_flight(speed):\n    return speed * 2  # archive velocity rules\n"
NDJSON = b'{"id":1,"topic":"archive capture"}\n{"id":2,"topic":"flight dynamics"}\n'
HTML = b"<html><title>Next chapter</title><body>Archive capture and moving aircraft are described here.</body></html>"
PAGE = b"<html><head><title>Index</title></head><body>Introduction and archive capture.</body></html>"
GOOD_ROBOTS = b"User-agent: *\nAllow: /\n"


class RealScriptedFetcher:
    timeout_seconds = 10.0
    transport_mode = "strict_scripted_canonical_test"

    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append((url, max_bytes))
        if url not in self.replies:
            raise AssertionError("unexpected network destination")
        status, headers, body = self.replies[url]
        if len(body) > max_bytes:
            raise AssertionError("test exceeded persisted response byte cap")
        return FetchResponse(url, status, headers, body, time.time())


def reply(media: str, data: bytes, *, link: str | None = None):
    headers = {"content-type": media}
    if link is not None:
        headers["link"] = link
    return (200, headers, data)


class Gain7ParserTest(unittest.TestCase):
    def setUp(self):
        self.policy = CrawlPolicy(
            allowed_hosts=frozenset({"example.com", "example.org"}),
        )

    def document(self, body, media):
        return extract_document(
            FetchResponse(
                "https://example.com/a", 200,
                {"content-type": media}, body, time.time(),
            ),
            "https://example.com/a",
            max_links=12, max_text_chars=25000,
        )

    def test_markdown_extracts_headline_and_navigational_links(self):
        result = self.document(MD, "text/markdown")
        self.assertEqual(result.title, "Flight Mechanics")
        self.assertIn("archive capture", result.text)
        self.assertIn("https://example.com/movement", result.links)
        self.assertIn("https://example.com/methods", result.links)
        self.assertNotIn("https://outside.example.net/image.png", result.links)
        self.assertNotIn("https://outside.example.net/hidden", result.links)

    def test_x_markdown_alias_retains_source_identity(self):
        result = self.document(MD, "text/x-markdown")
        self.assertEqual(result.content_type, "text/x-markdown")
        self.assertEqual(result.title, "Flight Mechanics")

    def test_markdown_reference_links_resolve_and_dedupe(self):
        raw = "# Guide\n[One][part]\n[Two][part]\n[part]: /details\n"
        result = extract_markdown(raw)
        self.assertEqual(result.links, ("/details",))

    def test_markdown_autolinks_are_discoverable(self):
        result = extract_markdown("See <https://example.com/autolink>.")
        self.assertEqual(result.links, ("https://example.com/autolink",))

    def test_markdown_fenced_links_do_not_enqueue(self):
        result = extract_markdown("```\n[a](https://example.com/evil)\n```")
        self.assertEqual(result.links, ())

    def test_markdown_link_budget_and_truncation(self):
        raw = "\n".join(f"[L{i}](/a{i})" for i in range(50))
        result = extract_markdown(raw, max_links=3)
        self.assertEqual(len(result.links), 3)
        self.assertTrue(result.truncated)

    def test_markdown_rejects_nul(self):
        with self.assertRaises(DocumentFormatError):
            extract_markdown("Valid\x00garbage")

    def test_csv_capture_has_labeled_retrievable_rows(self):
        result = self.document(CSV, "text/csv")
        self.assertEqual(result.content_type, "text/csv")
        self.assertIn("category: archive", result.text)
        self.assertIn("Row 2:", result.text)
        self.assertEqual(result.links, ())

    def test_csv_application_csv_media_alias(self):
        result = self.document(CSV, "application/csv")
        self.assertIn("title: Pilot", result.text)

    def test_csv_quoted_commas_are_not_split(self):
        result = extract_csv('name,summary\nAlice,"flight, motion"')
        self.assertIn("summary: flight, motion", result.text)

    def test_csv_formula_does_not_create_execution_or_link(self):
        result = extract_csv('name,expression\nCell,"=HYPERLINK(\'https://evil\')"')
        self.assertEqual(result.links, ())
        self.assertIn("HYPERLINK", result.text)
        self.assertFalse(result.body_executed)

    def test_csv_unbalanced_quote_rejected(self):
        with self.assertRaises(DocumentFormatError):
            extract_csv('name,data\nAlice,"unterminated')

    def test_csv_uneven_width_rejected(self):
        with self.assertRaises(DocumentFormatError):
            extract_csv("a,b,c\nvalue,missing")

    def test_csv_row_capacity_fail_closed(self):
        with self.assertRaises(DocumentFormatError):
            extract_csv("a\n" + "\n".join("x" for _ in range(30)),
                        max_rows=3)

    def test_csv_column_capacity_fail_closed(self):
        with self.assertRaises(DocumentFormatError):
            extract_csv("a,b,c\nx,y,z", max_columns=2)

    def test_json_documents_are_lexically_retrievable(self):
        result = self.document(JSON, "application/json")
        self.assertEqual(result.content_type, "application/json")
        self.assertIn("collection[0].topic: archive capture", result.text)
        self.assertEqual(result.title, "Original Engine API")
        self.assertEqual(result.links, ())

    def test_json_ld_evidence_ingestion(self):
        body = json.dumps({"@context": "https://schema.org",
                           "@type": "Article", "headline": "Original scene",
                           "author": {"name": "Source Author"}}).encode()
        result = self.document(body, "application/ld+json")
        self.assertEqual(result.title, "Original scene")
        self.assertIn("author.name: Source Author", result.text)

    def test_json_secret_keys_redacted_from_retained_text(self):
        result = extract_json(JSON.decode())
        self.assertNotIn("THIS_SHOULD_NEVER_BE_IN_EVIDENCE", result.text)
        self.assertIn("[redacted sensitive field]", result.text)

    def test_json_url_fields_never_enqueued(self):
        result = extract_json(JSON.decode())
        self.assertEqual(result.links, ())
        self.assertIn("outside.example.net", result.text)

    def test_json_duplicate_keys_rejected(self):
        with self.assertRaises(DocumentFormatError):
            extract_json('{"id":"safe","id":"malicious"}')

    def test_json_nonfinite_constants_rejected(self):
        with self.assertRaises(DocumentFormatError):
            extract_json('{"value":Infinity}')

    def test_json_depth_bound_rejected(self):
        with self.assertRaises(DocumentFormatError):
            extract_json('{"a":{"b":{"c":{"d":1}}}}', max_depth=2)

    def test_json_node_count_bound_rejected(self):
        with self.assertRaises(DocumentFormatError):
            extract_json(json.dumps(list(range(8192))))

    def test_json_scalar_not_interpreted_as_document(self):
        with self.assertRaises(DocumentFormatError):
            extract_json('"execute this"')

    def test_json_arrays_support_nested_evidence(self):
        result = extract_json('[{"a":[{"b":1}]},{"c":2}]')
        self.assertIn("$[0].a[0].b: 1", result.text)

    def test_document_format_dispatch_rejects_unapproved_mime(self):
        with self.assertRaises(DocumentFormatError):
            extract_additional_format("data", "application/octet-stream",
                                      max_chars=5000, max_links=4)

    def test_exact_source_hash_is_stable(self):
        a = self.document(MD, "text/markdown")
        b = self.document(MD, "text/markdown")
        self.assertEqual(a.content_hash, b.content_hash)
        self.assertEqual(a.provenance["raw_body_hash"], b.provenance["raw_body_hash"])


    def test_python_code_is_retained_without_executing_it(self):
        result = self.document(SOURCE_CODE, "text/x-python")
        self.assertEqual(result.content_type, "text/x-python")
        self.assertIn("simulate_flight", result.text)
        self.assertEqual(result.links, ())

    def test_typescript_source_is_inert_retrievable_text(self):
        source = b"const original = { movement: true, velocity: 3 };"
        result = self.document(source, "text/x-typescript")
        self.assertIn("movement", result.text)
        self.assertEqual(result.links, ())

    def test_javascript_code_urls_are_not_followed(self):
        source = 'fetch("https://outside.example.net/private");'
        result = extract_source_code(source, max_chars=1000, max_links=32)
        self.assertIn("outside.example.net", result.text)
        self.assertEqual(result.links, ())
        self.assertFalse(result.body_executed)

    def test_source_code_rejects_binary_nul(self):
        with self.assertRaises(DocumentFormatError):
            extract_source_code("class A:\x00bad", max_chars=1024, max_links=1)

    def test_source_code_rejects_terminal_escape(self):
        with self.assertRaises(DocumentFormatError):
            extract_source_code("code\x1b[31m", max_chars=1024, max_links=1)

    def test_source_code_rejects_invalid_decoder_replacement_density(self):
        with self.assertRaises(DocumentFormatError):
            extract_source_code("\ufffd" * 20, max_chars=1024, max_links=1)

    def test_yaml_config_preserves_content_without_interpreting_tags(self):
        source = "handler: !!python/object/apply:os.system [false]\nmode: research"
        result = self.document(source.encode(), "application/yaml")
        self.assertIn("!!python/object/apply", result.text)
        self.assertFalse(result.provenance["parser_text_truncated"])
        self.assertEqual(result.links, ())

    def test_toml_config_retains_inert_settings(self):
        result = self.document(b"[ai]\nmode = 'offline'\n", "application/toml")
        self.assertIn("offline", result.text)
        self.assertEqual(result.links, ())

    def test_rst_reference_docs_are_captured_as_plain_source(self):
        result = self.document(b"Original Heading\n===============\n", "text/x-rst")
        self.assertIn("Original Heading", result.text)

    def test_json_lines_extracts_multiple_records(self):
        result = self.document(NDJSON, "application/x-ndjson")
        self.assertIn("Record 1:", result.text)
        self.assertIn("topic: archive capture", result.text)
        self.assertIn("Record 2:", result.text)
        self.assertEqual(result.links, ())

    def test_json_lines_rejects_malformed_line(self):
        with self.assertRaises(DocumentFormatError):
            extract_ndjson('{"ok":true}\n{broken',
                           max_chars=1024, max_links=0)

    def test_json_lines_rejects_unbounded_record_count(self):
        with self.assertRaises(DocumentFormatError):
            extract_ndjson('{"item":1}\n'*6,
                           max_chars=1024, max_links=0, max_records=5)

    def test_json_lines_does_not_enqueue_url_fields(self):
        result = extract_ndjson(
            '{"url":"https://outside.example.net/private"}',
            max_chars=4096, max_links=0,
        )
        self.assertEqual(result.links, ())
        self.assertIn("outside.example.net", result.text)

    def test_source_code_projection_truncation_is_explicit(self):
        source = "safe code content " * 100
        parsed = extract_source_code(source, max_chars=200, max_links=0)
        self.assertTrue(parsed.truncated)
        self.assertEqual(len(parsed.text), 200)

    def test_ndjson_with_duplicate_object_fields_is_rejected(self):
        with self.assertRaises(DocumentFormatError):
            extract_ndjson('{"id":1,"id":2}',
                           max_chars=1024, max_links=0)

class LinkHeaderTest(unittest.TestCase):
    def setUp(self):
        self.policy = CrawlPolicy(allowed_hosts=frozenset({"example.com"}))

    def parse(self, value, **kwargs):
        return parse_link_headers(
            {"link": value}, base_url="https://example.com/current",
            policy=self.policy, **kwargs,
        )

    def test_next_pagination_and_typed_feed_alternates(self):
        result = self.parse(
            '<https://example.com/next>; rel="next",'
            '</feed.xml>; rel="alternate"; type="application/rss+xml"',
        )
        self.assertEqual(result.links, (
            "https://example.com/next", "https://example.com/feed.xml",
        ))
        self.assertTrue(result.link_header_did_not_grant_network_authority)

    def test_untyped_alternate_is_ignored(self):
        result = self.parse('</evil>; rel="alternate"')
        self.assertEqual(result.links, ())

    def test_link_related_prefetch_does_not_enqueue(self):
        result = self.parse('</prefetch>; rel="prefetch"')
        self.assertEqual(result.links, ())

    def test_link_header_cross_host_rejected(self):
        result = self.parse(
            '<https://outside.example.net/page>; rel=next,'
            '</next>; rel=next',
        )
        self.assertEqual(result.links, ("https://example.com/next",))

    def test_link_header_credentials_rejected(self):
        result = self.parse(
            '<https://admin:password@example.com/private>; rel=next',
        )
        self.assertEqual(result.links, ())

    def test_link_header_duplicate_targets_deduplicated(self):
        result = self.parse('</p>; rel=next, </p>; rel=next')
        self.assertEqual(result.links, ("https://example.com/p",))

    def test_link_header_malformed_syntax_fail_closed(self):
        with self.assertRaises(ValueError):
            self.parse('<https://example.com/a>; rel="next')
        with self.assertRaises(ValueError):
            self.parse('<<https://example.com/a>>; rel=next')

    def test_link_header_bounded_relations(self):
        value = ",".join(f"</a{i}>; rel=next" for i in range(10))
        result = self.parse(value, max_relations=3)
        self.assertEqual(len(result.links), 3)
        self.assertTrue(result.truncated)

    def test_link_header_bounded_links(self):
        value = ",".join(f"</a{i}>; rel=next" for i in range(10))
        result = self.parse(value, max_links=2)
        self.assertEqual(len(result.links), 2)
        self.assertTrue(result.truncated)

    def test_link_header_oversized_payload_rejected(self):
        with self.assertRaises(ValueError):
            self.parse("A" * 8193)

    def test_link_header_no_link_header_is_empty(self):
        result = parse_link_headers(
            {"content-type": "text/plain"},
            base_url="https://example.com/a", policy=self.policy,
        )
        self.assertEqual(result.links, ())

    def test_link_header_alternate_json_feed(self):
        result = self.parse('</feed.json>; rel=alternate; type="application/feed+json"')
        self.assertEqual(result.links, ("https://example.com/feed.json",))


class RepeatedLinkTransportTest(unittest.TestCase):
    def test_two_link_headers_survive_finite_transport_normalization(self):
        pairs = [
            ("Link", "</part-2>; rel=next"),
            ("LINK", "</feed.json>; rel=alternate; type=application/feed+json"),
        ]
        normalized = {k.lower(): v for k, v in pairs}
        _coalesce_bounded_link_headers(pairs, normalized)
        self.assertIn("</part-2>", normalized["link"])
        self.assertIn("</feed.json>", normalized["link"])
        report = parse_link_headers(
            normalized, base_url="https://example.com/current",
            policy=CrawlPolicy(allowed_hosts=frozenset({"example.com"})),
        )
        self.assertEqual(report.links, (
            "https://example.com/part-2", "https://example.com/feed.json",
        ))

    def test_oversized_link_header_is_discarded_not_dispatched(self):
        pairs = [("Link", "</x>; rel=next") for _ in range(18)]
        normalized = {"link": "</unsafe>; rel=next"}
        _coalesce_bounded_link_headers(pairs, normalized)
        self.assertNotIn("link", normalized)

    def test_oversized_single_link_header_is_discarded(self):
        pairs = [("Link", "A" * 9000)]
        normalized = {"link": "A" * 9000}
        _coalesce_bounded_link_headers(pairs, normalized)
        self.assertNotIn("link", normalized)

    def test_unrelated_response_framing_fields_are_not_modified(self):
        pairs = [
            ("Content-Length", "42"),
            ("Link", "</next>; rel=next"),
        ]
        headers = {"content-length": "42", "link": "</next>; rel=next"}
        _coalesce_bounded_link_headers(pairs, headers)
        self.assertEqual(headers["content-length"], "42")


class FrontierSchedulingTest(unittest.TestCase):
    def row(self, url, *, depth=0, attempts=0, ready_at=0):
        return {"url": url, "depth": depth, "attempts": attempts,
                "ready_at": ready_at, "original_url": url,
                "parent_url": None, "redirects": []}

    def choose(self, rows, *, strategy="balanced", query="",
               captured=None, host_ready=None, now=100):
        return choose_frontier(
            rows, sources=(captured or {}), host_ready=(host_ready or {}),
            query=query, now=now, strategy=strategy,
        )

    def test_fifo_preserves_existing_frontier_order(self):
        rows = [
            self.row("https://example.com/general"),
            self.row("https://example.com/archive-capture"),
        ]
        chosen, result = self.choose(rows, strategy="fifo", query="archive")
        self.assertEqual(chosen["url"], rows[0]["url"])
        self.assertEqual(result.algorithm, "fifo")

    def test_balanced_priority_uses_operator_query_path(self):
        rows = [
            self.row("https://example.com/general"),
            self.row("https://example.com/archive-capture"),
        ]
        chosen, receipt = self.choose(rows, query="archive capture")
        self.assertEqual(chosen["url"], rows[1]["url"])
        self.assertEqual(receipt.objective_url_affinity, 1.0)
        self.assertFalse(receipt.actual_dispatch_authorized)

    def test_balanced_avoids_overserved_hosts(self):
        rows = [
            self.row("https://example.com/archive"),
            self.row("https://example.org/general"),
        ]
        captured = {
            str(i): {"canonical_url": "https://example.com/old"+str(i)}
            for i in range(12)
        }
        selected, receipt = self.choose(
            rows, query="archive", captured=captured,
        )
        self.assertEqual(selected["url"], rows[1]["url"])
        self.assertEqual(receipt.host_captured_documents, 0)

    def test_balanced_prioritizes_lower_retry_pressure(self):
        rows = [
            self.row("https://example.com/fault", attempts=3),
            self.row("https://example.com/fresh"),
        ]
        chosen, receipt = self.choose(rows)
        self.assertEqual(chosen["url"], rows[1]["url"])
        self.assertLessEqual(receipt.fairness_score, 1)

    def test_balanced_prioritizes_breadth_first_at_equal_affinity(self):
        rows = [
            self.row("https://example.com/deep", depth=3),
            self.row("https://example.com/root", depth=0),
        ]
        chosen, _ = self.choose(rows)
        self.assertEqual(chosen["url"], rows[1]["url"])

    def test_host_cooldown_blocks_even_high_affinity_page(self):
        rows = [
            self.row("https://example.com/archive"),
            self.row("https://example.org/other"),
        ]
        chosen, receipt = self.choose(
            rows, query="archive",
            host_ready={"example.com": 150}, now=100,
        )
        self.assertEqual(chosen["url"], rows[1]["url"])
        self.assertEqual(receipt.eligible_urls, 1)

    def test_all_delayed_returns_no_dispatched_work(self):
        rows = [self.row("https://example.com/later", ready_at=200)]
        self.assertEqual(self.choose(rows, now=100), (None, None))

    def test_balanced_choice_is_deterministic(self):
        rows = [
            self.row("https://example.com/a"),
            self.row("https://example.com/b"),
        ]
        self.assertEqual(self.choose(rows), self.choose(rows))

    def test_balanced_never_creates_new_frontier_url(self):
        rows = [self.row("https://example.com/archive")]
        chosen, _ = self.choose(rows, query="archive")
        self.assertIs(chosen, rows[0])

    def test_unsupported_strategy_is_rejected(self):
        with self.assertRaises(ValueError):
            self.choose([], strategy="unbounded")

    def test_nan_scheduler_clock_rejected(self):
        with self.assertRaises(ValueError):
            self.choose([], now=float("nan"))

    def test_balanced_request_mode_is_strict(self):
        req = CrawlRequest(
            seed_urls=("https://example.com/",),
            allowed_hosts=("example.com",),
            frontier_strategy="balanced",
        )
        self.assertEqual(req.frontier_strategy, "balanced")
        with self.assertRaises(CrawlOperationError):
            replace(req, frontier_strategy="autonomous")


class CanonicalGain7Test(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self.transport = RealScriptedFetcher({
            "https://example.com/robots.txt": reply("text/plain", GOOD_ROBOTS),
            "https://example.org/robots.txt": reply("text/plain", GOOD_ROBOTS),
            "https://example.com/doc.md": reply("text/markdown", MD),
            "https://example.com/table.csv": reply("text/csv", CSV),
            "https://example.com/data.json": reply("application/json", JSON),
            "https://example.com/code.py": reply("text/x-python", SOURCE_CODE),
            "https://example.com/log.jsonl": reply("application/x-ndjson", NDJSON),
            "https://example.com/pagination": reply(
                "text/html", PAGE,
                link='</page-two>; rel="next", </feed.json>; rel="alternate"; type="application/feed+json"',
            ),
            "https://example.com/page-two": reply("text/html", HTML),
            "https://example.com/general": reply("text/html", PAGE),
            "https://example.com/archive-capture": reply("text/html", HTML),
            "https://example.com/movement": reply("text/html", HTML),
            "https://example.com/methods": reply("text/html", PAGE),
        })

    def make_run(self, *seeds, strategy="fifo", max_depth=1, query="archive"):
        req = CrawlRequest(
            seed_urls=tuple(seeds), allowed_hosts=("example.com",),
            max_depth=max_depth, query=query, max_requests=14,
            max_documents=10, max_response_bytes=4096,
            max_total_bytes=32768, min_host_delay_seconds=.25,
            frontier_strategy=strategy,
        )
        return CrawlRun.create(req, scope={
            "tenant_id": "tenant", "owner_id": "account",
        }, consent={
            "consent_id": "consent-gain7",
            "capture_acknowledged": True,
            "source_rights_acknowledged": True,
            "expires_at": self.now+3600,
        }, now=self.now, fetcher=self.transport)

    def tick(self, run: CrawlRun, offset):
        with patch("skeleton.ai.webcrawler.operations.time.time",
                   return_value=self.now + offset):
            return run.run_slice(
                max_steps=1, max_seconds=1,
                authorize=lambda: None,
                cancelled=lambda: False,
                on_checkpoint=lambda snapshot, event: None,
            )

    def test_live_python_code_is_captured_but_not_executed(self):
        run = self.make_run("https://example.com/code.py")
        self.tick(run, 1)
        self.tick(run, 3)
        snap = run.snapshot()
        self.assertEqual(snap["usage"]["documents"], 1)
        source = next(iter(snap["sources"].values()))
        self.assertEqual(source["content_type"], "text/x-python")
        self.assertIn("simulate_flight", source["text"])
        self.assertEqual(snap["frontier"], [])
        self.assertFalse(source["provenance"]["training_permission"])

    def test_live_ndjson_is_captured_and_searchable(self):
        run = self.make_run("https://example.com/log.jsonl")
        self.tick(run, 1)
        self.tick(run, 3)
        snap = run.snapshot()
        self.assertEqual(snap["usage"]["documents"], 1)
        self.assertIn("Record 2", next(iter(snap["sources"].values()))["text"])
        self.assertTrue(run.search("archive")["hits"])

    def test_prestorage_truncation_is_bound_into_source_metadata(self):
        big = b'{"title":"large","records":["' + b"R" * 14000 + b'"]}'
        self.transport.replies["https://example.com/data.json"] = reply(
            "application/json", big,
        )
        req = CrawlRequest(
            seed_urls=("https://example.com/data.json",),
            allowed_hosts=("example.com",), query="records",
            max_response_bytes=24000, max_total_bytes=60000,
        )
        run = CrawlRun.create(req, scope={
            "tenant_id":"tenant", "owner_id":"account",
        }, consent={
            "consent_id":"c", "capture_acknowledged":True,
            "source_rights_acknowledged":True,
            "expires_at":self.now+3600,
        }, now=self.now, fetcher=self.transport)
        self.tick(run, 1)
        self.tick(run, 3)
        source = next(iter(run.snapshot()["sources"].values()))
        self.assertTrue(source["provenance"]["parser_text_truncated"]
                        or source["text_truncated"])
        self.assertEqual(source["review_state"], "unreviewed")
        CrawlRun.from_snapshot(run.snapshot(), fetcher=self.transport)

    def test_live_markdown_doc_is_captured_as_unreviewed_evidence(self):
        run = self.make_run("https://example.com/doc.md")
        self.tick(run, 1)
        self.tick(run, 3)
        snap = run.snapshot()
        self.assertEqual(snap["usage"]["documents"], 1)
        self.assertTrue(any(x["url"].endswith("/movement")
                            for x in snap["frontier"]))
        source = next(iter(snap["sources"].values()))
        self.assertEqual(source["content_type"], "text/markdown")
        self.assertFalse(source["provenance"]["training_permission"])
        CrawlRun.from_snapshot(snap, fetcher=self.transport)

    def test_live_markdown_relative_link_fetches_next_document(self):
        run = self.make_run("https://example.com/doc.md")
        self.tick(run, 1)
        self.tick(run, 3)
        self.tick(run, 5)
        self.assertEqual(run.snapshot()["usage"]["documents"], 2)
        self.assertEqual(len(self.transport.calls), 3)

    def test_live_csv_document_is_captured_and_searchable(self):
        run = self.make_run("https://example.com/table.csv")
        self.tick(run, 1)
        self.tick(run, 3)
        snap = run.snapshot()
        self.assertEqual(snap["usage"]["documents"], 1)
        self.assertIn("category: archive", next(iter(snap["sources"].values()))["text"])
        self.assertEqual(snap["frontier"], [])
        self.assertTrue(run.search("archive")["hits"])

    def test_live_json_api_document_retains_no_secret_key_value(self):
        run = self.make_run("https://example.com/data.json")
        self.tick(run, 1)
        self.tick(run, 3)
        snap = run.snapshot()
        self.assertEqual(snap["usage"]["documents"], 1)
        src = next(iter(snap["sources"].values()))
        self.assertIn("archive capture", src["text"])
        self.assertNotIn("THIS_SHOULD_NEVER_BE_IN_EVIDENCE", src["text"])
        self.assertEqual(snap["frontier"], [])

    def test_live_http_link_pagination_is_enqueued(self):
        run = self.make_run("https://example.com/pagination")
        self.tick(run, 1)
        self.tick(run, 3)
        snap = run.snapshot()
        self.assertEqual({row["url"] for row in snap["frontier"]},
                         {"https://example.com/page-two",
                          "https://example.com/feed.json"})
        self.assertEqual(snap["usage"]["documents"], 1)

    def test_live_link_pagination_can_capture_followup(self):
        run = self.make_run("https://example.com/pagination")
        self.tick(run, 1)
        self.tick(run, 3)
        self.tick(run, 5)
        self.assertEqual(run.snapshot()["usage"]["documents"], 2)

    def test_live_link_header_malicious_host_is_filtered(self):
        self.transport.replies["https://example.com/pagination"] = reply(
            "text/html", PAGE,
            link='<https://localhost/admin>; rel=next, </page-two>; rel=next',
        )
        run = self.make_run("https://example.com/pagination")
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual([x["url"] for x in run.snapshot()["frontier"]],
                         ["https://example.com/page-two"])

    def test_live_fifo_keeps_first_seed_first(self):
        run = self.make_run("https://example.com/general",
                       "https://example.com/archive-capture",
                       strategy="fifo")
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(self.transport.calls[1][0],
                         "https://example.com/general")

    def test_live_balanced_prioritizes_high_affinity_seed(self):
        run = self.make_run("https://example.com/general",
                       "https://example.com/archive-capture",
                       strategy="balanced", query="archive capture")
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(self.transport.calls[1][0],
                         "https://example.com/archive-capture")

    def test_live_balanced_still_obeys_robots(self):
        self.transport.replies["https://example.com/robots.txt"] = (
            200, {"content-type": "text/plain"},
            b"User-agent: *\nDisallow: /",
        )
        run = self.make_run("https://example.com/archive-capture",
                       strategy="balanced")
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)

    def test_live_balanced_snapshot_survives_reopen(self):
        run = self.make_run("https://example.com/archive-capture",
                       strategy="balanced")
        snap = run.snapshot()
        restored = CrawlRun.from_snapshot(snap, fetcher=self.transport)
        self.assertEqual(restored.request.frontier_strategy, "balanced")
        self.assertEqual(restored.snapshot(), snap)

    def test_response_budget_remains_bounded_for_json(self):
        run = self.make_run("https://example.com/data.json")
        self.tick(run, 1)
        self.tick(run, 3)
        snap = run.snapshot()
        self.assertEqual(snap["usage"]["requests"], 2)
        self.assertEqual(snap["usage"]["reserved_bytes"], 0)
        self.assertLessEqual(snap["usage"]["bytes"], run.request.max_total_bytes)

    def test_malformed_csv_yields_rejected_not_transient_retry(self):
        self.transport.replies["https://example.com/table.csv"] = reply(
            "text/csv", b"name,data\nAlice,\"unterminated",
        )
        run = self.make_run("https://example.com/table.csv")
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(run.snapshot()["usage"]["requests"], 2)
        self.assertEqual(run.snapshot()["usage"]["failures"], 0)
        self.assertEqual(run.snapshot()["events"][-1]["kind"], "rejected")

    def test_malformed_json_yields_rejected_not_evidence(self):
        self.transport.replies["https://example.com/data.json"] = reply(
            "application/json", b"{broken",
        )
        run = self.make_run("https://example.com/data.json")
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)
        self.assertEqual(run.snapshot()["events"][-1]["kind"], "rejected")

    def test_expired_consent_rejects_real_capture(self):
        run = self.make_run("https://example.com/doc.md")
        with patch("skeleton.ai.webcrawler.operations.time.time",
                   return_value=self.now + 3700):
            with self.assertRaises(CrawlOperationError):
                run.run_slice(max_steps=1, max_seconds=1)

    def test_unrecognized_binary_media_not_extracted(self):
        self.transport.replies["https://example.com/data.json"] = reply(
            "application/octet-stream", b"binary\x00payload",
        )
        run = self.make_run("https://example.com/data.json")
        self.tick(run, 1)
        self.tick(run, 3)
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)


if __name__ == "__main__":
    unittest.main()
