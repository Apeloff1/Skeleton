"""Live canonical crawler compressed HTTP acquisition and malformed-stream regression.

No Internet, database, model execution or implicit permission. Exercises the
same pre-I/O request reservations, robots, source custody, search and replay.
"""
from __future__ import annotations

import gzip
import hashlib
import time
import unittest
import zlib
from unittest.mock import patch

from skeleton.ai.webcrawler.content_coding import (
    BoundedHTTPBody, ContentCodingError, normalize_content_coding,
)
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

ROBOTS = b"User-agent: *\nAllow: /\n"
HTML = b"<html><head><title>Compressed Archive</title></head><body>Archived flight mechanics with bounded capture.</body></html>"


def encode(payload, coding, level=6):
    if coding == "gzip":
        return gzip.compress(payload, compresslevel=level, mtime=0)
    if coding == "deflate":
        return zlib.compress(payload, level)
    return payload


def decode(raw, coding, cap=4096):
    reader = BoundedHTTPBody(coding, max_bytes=cap)
    for offset in range(0, len(raw), 17):
        reader.feed(raw[offset:offset + 17])
    return reader.finish(), reader


class EntityCodingContracts(unittest.TestCase):
    def test_identity_wire_hash_and_body(self):
        content, packet = decode(HTML, "identity")
        self.assertEqual(content, HTML)
        self.assertEqual(packet.wire_bytes, len(HTML))
        self.assertEqual(packet.decoded_bytes, len(HTML))
        self.assertEqual(packet.wire_hash, hashlib.sha256(HTML).hexdigest())

    def test_real_incremental_gzip_and_zlib_deflate(self):
        for coding in ("gzip", "deflate"):
            with self.subTest(coding=coding):
                raw = encode(HTML, coding)
                content, packet = decode(raw, coding)
                self.assertEqual(content, HTML)
                self.assertEqual(packet.wire_bytes, len(raw))
                self.assertEqual(packet.decoded_bytes, len(HTML))
                self.assertEqual(packet.wire_hash, hashlib.sha256(raw).hexdigest())

    def test_empty_gzip_is_complete_but_not_evidence(self):
        self.assertEqual(decode(gzip.compress(b"", mtime=0), "gzip")[0], b"")

    def test_compression_bomb_exceeds_decoded_budget(self):
        for coding in ("gzip", "deflate"):
            with self.subTest(coding=coding), self.assertRaises(ContentCodingError):
                decode(encode(b"Z" * 32_000, coding), coding, cap=2048)

    def test_wire_ceiling_is_independent(self):
        packet = BoundedHTTPBody("gzip", max_bytes=64)
        with self.assertRaisesRegex(ContentCodingError, "wire"):
            packet.feed(b"x" * 65)

    def test_crc_corruption_and_incomplete_stream(self):
        raw = bytearray(gzip.compress(HTML, mtime=0))
        raw[-7] ^= 0x7F
        with self.assertRaises(ContentCodingError):
            decode(bytes(raw), "gzip")
        for coding in ("gzip", "deflate"):
            with self.subTest(coding=coding), self.assertRaises(ContentCodingError):
                decode(encode(HTML, coding)[:-5], coding)

    def test_gzip_multimember_and_trailing_bytes_denied(self):
        with self.assertRaises(ContentCodingError):
            decode(gzip.compress(HTML, mtime=0) + gzip.compress(b"attack", mtime=0), "gzip")
        with self.assertRaises(ContentCodingError):
            decode(zlib.compress(HTML) + b"tail", "deflate")

    def test_raw_deflate_not_silently_accepted(self):
        compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        raw = compressor.compress(HTML) + compressor.flush()
        with self.assertRaises(ContentCodingError):
            decode(raw, "deflate")

    def test_header_normalization_is_strict(self):
        self.assertEqual(normalize_content_coding(" GZIP "), "gzip")
        self.assertEqual(normalize_content_coding(None), "identity")
        for value in ("br", "gzip, deflate", "identity,gzip", "gzip;foo=bar", "\n"):
            with self.subTest(value=value), self.assertRaises(ContentCodingError):
                normalize_content_coding(value)

    def test_invalid_bounds_and_reuse(self):
        for bound in (0, True, -1, 4_000_001):
            with self.assertRaises(ContentCodingError):
                BoundedHTTPBody("identity", max_bytes=bound)
        packet = BoundedHTTPBody("identity", max_bytes=50)
        with self.assertRaises(ContentCodingError):
            packet.feed("not bytes")
        packet.feed(b"ok")
        self.assertEqual(packet.finish(), b"ok")
        with self.assertRaises(ContentCodingError):
            packet.finish()
        with self.assertRaises(ContentCodingError):
            packet.feed(b"x")


class ScriptedCompressedTransport:
    timeout_seconds = 3.0
    transport_mode = "scripted_compressed_canonical_worker"

    def __init__(self, coding, level=6, spoof=False):
        self.coding, self.level, self.spoof = coding, level, spoof
        self.calls = []

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResponse(url, 200, {"content-type": "text/plain"}, ROBOTS, time.time())
        if url != "https://example.com/archive":
            raise AssertionError("unadmitted destination")
        raw = encode(HTML, self.coding, self.level)
        body, receipt = decode(raw, self.coding, cap=max_bytes)
        return FetchResponse(
            url, 200, {"content-type": "text/html", "content-encoding": self.coding},
            body, time.time(),
            wire_bytes=5 if self.spoof else receipt.wire_bytes,
            wire_hash="invalid" if self.spoof else receipt.wire_hash,
            content_encoding=self.coding,
        )


class CanonicalCompressedCrawler(unittest.TestCase):
    def make_run(self, transport):
        now = time.time()
        request = CrawlRequest(
            seed_urls=("https://example.com/archive",), allowed_hosts=("example.com",),
            max_depth=0, max_requests=4, max_documents=2,
            max_response_bytes=4096, max_total_bytes=16384,
            min_host_delay_seconds=.25,
        )
        run = CrawlRun.create(
            request, scope={"tenant_id": "tenant", "owner_id": "owner"},
            consent={
                "consent_id": "compressed-evidence-consent",
                "capture_acknowledged": True, "source_rights_acknowledged": True,
                "expires_at": now + 3600,
            }, now=now, fetcher=transport,
        )
        return run, now

    def tick(self, run, now):
        with patch("skeleton.ai.webcrawler.operations.time.time", return_value=now):
            run.run_slice(
                max_steps=1, max_seconds=1, authorize=lambda: None,
                cancelled=lambda: False, on_checkpoint=lambda snapshot, event: None,
            )

    def test_compressed_sources_reach_search_with_wire_integrity_and_replay(self):
        for coding in ("gzip", "deflate"):
            with self.subTest(coding=coding):
                transport = ScriptedCompressedTransport(coding)
                run, now = self.make_run(transport)
                self.tick(run, now + 1)
                self.tick(run, now + 3)
                state = run.snapshot()
                self.assertEqual(transport.calls, [
                    "https://example.com/robots.txt", "https://example.com/archive",
                ])
                self.assertEqual(state["usage"]["documents"], 1)
                source = next(iter(state["sources"].values()))
                raw = encode(HTML, coding)
                self.assertEqual(source["raw_body_hash"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(source["provenance"]["decoded_body_hash"], hashlib.sha256(HTML).hexdigest())
                self.assertEqual(source["provenance"]["wire_bytes"], len(raw))
                self.assertEqual(source["provenance"]["content_encoding"], coding)
                self.assertEqual(source["review_state"], "unreviewed")
                self.assertFalse(source["provenance"]["training_permission"])
                self.assertTrue(run.search("flight")["hits"])
                self.assertEqual(CrawlRun.from_snapshot(state, fetcher=transport).snapshot(), state)

    def test_incompressible_wire_overhead_is_charged(self):
        transport = ScriptedCompressedTransport("gzip", level=0)
        run, now = self.make_run(transport)
        self.tick(run, now + 1)
        self.tick(run, now + 3)
        raw = encode(HTML, "gzip", level=0)
        self.assertGreater(len(raw), len(HTML))
        self.assertEqual(run.snapshot()["usage"]["bytes"], len(ROBOTS) + len(raw))

    def test_forged_coding_receipt_rejected_before_source_capture(self):
        transport = ScriptedCompressedTransport("gzip", spoof=True)
        run, now = self.make_run(transport)
        self.tick(run, now + 1)
        self.tick(run, now + 3)
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)
        self.assertEqual(run.snapshot()["usage"]["failures"], 1)



class SocketBoundCodingTransportTests(unittest.TestCase):
    """Verify the actual socket-bound entrypoint with a strictly synthetic socket."""

    def scripted(self, raw, coding="gzip", duplicated=False):
        from unittest.mock import MagicMock, patch
        from skeleton.ai.webcrawler.bound_http import SocketBoundFetcher
        from skeleton.ai.webcrawler.dns_binding import ResolvedTarget

        class Response:
            status = 200
            length = 0
            fp = None

            def __init__(self):
                self.chunks = [
                    raw[index:index + 9] for index in range(0, len(raw), 9)
                ]

            def getheaders(self):
                rows = [
                    ("Content-Type", "text/html"),
                    ("Content-Encoding", coding),
                    ("Content-Length", str(len(raw))),
                ]
                if duplicated:
                    rows.append(("CONTENT-ENCODING", coding))
                return rows

            def read1(self, requested):
                if not self.chunks:
                    return b""
                value = self.chunks.pop(0)
                if len(value) > requested:
                    self.chunks.insert(0, value[requested:])
                    return value[:requested]
                return value

        connection = MagicMock()
        connection.getresponse.return_value = Response()
        target = ResolvedTarget(
            "http://example.com/archive", "example.com", 80, ("93.184.215.14",),
        )
        with patch("skeleton.ai.webcrawler.bound_http.resolve_target", return_value=target), patch(
            "skeleton.ai.webcrawler.bound_http._PinnedHTTPConnection", return_value=connection,
        ):
            fetcher = SocketBoundFetcher(
                timeout_seconds=3, allowed_hosts=frozenset({"example.com"}),
            )
            result = fetcher.fetch_once(
                target.url, user_agent="Dragon-Crawler-Test", max_bytes=4096,
            )
        return result, connection

    def test_production_transport_decodes_gzip_and_deflate(self):
        for coding in ("gzip", "deflate"):
            with self.subTest(coding=coding):
                raw = encode(HTML, coding)
                result, connection = self.scripted(raw, coding)
                self.assertEqual(result.body, HTML)
                self.assertEqual(result.wire_bytes, len(raw))
                self.assertEqual(result.wire_hash, hashlib.sha256(raw).hexdigest())
                self.assertEqual(result.content_encoding, coding)
                self.assertEqual(
                    connection.request.call_args.kwargs["headers"]["Accept-Encoding"],
                    "gzip, deflate, identity",
                )
                connection.close.assert_called_once()

    def test_actual_transport_rejects_duplicate_content_encoding(self):
        with self.assertRaisesRegex(ValueError, "ambiguous Content-Encoding"):
            self.scripted(encode(HTML, "gzip"), duplicated=True)

    def test_actual_transport_rejects_decompression_bomb(self):
        with self.assertRaises(ContentCodingError):
            self.scripted(encode(b"B" * 20000, "gzip"))

    def test_actual_transport_rejects_truncated_compressed_body(self):
        with self.assertRaises(ContentCodingError):
            self.scripted(encode(HTML, "gzip")[:-4])


if __name__ == "__main__":
    unittest.main()
