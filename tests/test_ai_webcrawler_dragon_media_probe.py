"""Strict octet-stream MIME recovery through canonical real capture receipts."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.media_probe import inspect_download_media
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

class MediaProbeTests(unittest.TestCase):
    def test_docx_odt_epub_magic_probes(self):
        for path, mime in (
            ("doc.docx", DOCX),
            ("doc.odt", "application/vnd.oasis.opendocument.text"),
            ("doc.epub", "application/epub+zip"),
        ):
            with self.subTest(path=path):
                row = inspect_download_media(
                    "https://example.com/" + path,
                    "application/octet-stream", b"PK\x03\x04safe-zip-data",
                )
                self.assertTrue(row.inferred)
                self.assertEqual(row.effective_type, mime)
                self.assertFalse(row.external_network_authority)
                self.assertFalse(row.executable_content_admitted)

    def test_xml_gpx_kml_prefixes(self):
        for path, mime in (
            ("doc.xml", "application/xml"),
            ("track.gpx", "application/gpx+xml"),
            ("track.kml", "application/vnd.google-earth.kml+xml"),
        ):
            with self.subTest(path=path):
                row = inspect_download_media(
                    "https://example.com/" + path,
                    "application/octet-stream", b"<?xml version='1.0'?><root/>",
                )
                self.assertTrue(row.inferred)
                self.assertEqual(row.effective_type, mime)

    def test_arbitrary_binary_is_not_misclassified(self):
        for suffix, body in (
            ("manual.docx", b"MZexecutable"),
            ("map.kml", b"\x00binary\x00"),
            ("api.json", b'{"token":"sensitive"}'),
            ("unknown.exe", b"PK\x03\x04fakezip"),
        ):
            with self.subTest(suffix=suffix):
                row = inspect_download_media(
                    "https://example.com/" + suffix,
                    "application/octet-stream", body,
                )
                self.assertFalse(row.inferred)
                self.assertEqual(row.effective_type, "application/octet-stream")

    def test_declared_safe_type_is_not_overridden(self):
        row = inspect_download_media(
            "https://example.com/file.docx", "text/plain", b"PK\x03\x04fakezip",
        )
        self.assertFalse(row.inferred)
        self.assertEqual(row.effective_type, "text/plain")

    def test_url_with_query_recovers_exact_extension(self):
        row = inspect_download_media(
            "https://example.com/manual.odt?download=1",
            "application/zip", b"PK\x03\x04data",
        )
        self.assertTrue(row.inferred)

    def test_download_filename_recovers_real_docx_format(self):
        row=inspect_download_media(
            "https://example.com/download?id=1",
            "application/octet-stream",b"PK\x03\x04zip",
            'attachment; filename="flight_manual.docx"',
        )
        self.assertTrue(row.inferred)
        self.assertEqual(row.effective_type,DOCX)

    def test_download_filename_does_not_enable_executables_or_traversal(self):
        for hint in (
            'attachment; filename="../../escape.docx"',
            'attachment; filename="evil.exe"',
            'attachment; filename="a.docx"; x=y',
        ):
            with self.subTest(hint=hint):
                row=inspect_download_media(
                    "https://example.com/download",
                    "application/octet-stream",b"PK\x03\x04zip",hint,
                )
                self.assertFalse(row.inferred)

    def test_bad_contracts_raise(self):
        for value in (None, 1, b"binary"):
            with self.assertRaises(ValueError):
                inspect_download_media(value, "application/octet-stream", b"data")


class OctetScriptedFetcher:
    timeout_seconds = 3
    transport_mode = "scripted_octet_media_identity"

    def __init__(self, data, mime="application/octet-stream"):
        self.data, self.mime, self.calls = data, mime, []

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResponse(url, 200, {"content-type":"text/plain"}, b"User-agent: *\nAllow: /\n", time.time())
        if url != "https://example.com/track.gpx":
            raise AssertionError("unadmitted network target")
        return FetchResponse(url, 200, {"content-type":self.mime}, self.data, time.time())


class RealMediaRecoveryTests(unittest.TestCase):
    def test_xml_octet_stream_is_captured_as_inert_unreviewed_gpx(self):
        at = time.time()
        fetcher = OctetScriptedFetcher(b"<gpx><trk><name>Archived flight telemetry</name></trk></gpx>")
        run = CrawlRun.create(CrawlRequest(
            seed_urls=("https://example.com/track.gpx",), allowed_hosts=("example.com",),
            max_requests=4, max_documents=2, max_depth=0,
            max_response_bytes=4096, max_total_bytes=12288,
        ), scope={"tenant_id":"tenant","owner_id":"owner"}, consent={
            "consent_id":"octet-media-optin","capture_acknowledged":True,
            "source_rights_acknowledged":True,"expires_at":at+3600,
        }, now=at, fetcher=fetcher)
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=at+offset):
                run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                    cancelled=lambda:False,on_checkpoint=lambda snapshot,event:None)
        snap=run.snapshot()
        self.assertEqual(snap["usage"]["documents"],1)
        self.assertEqual(next(iter(snap["sources"].values()))["content_type"],"application/gpx+xml")
        provenance = next(iter(snap["sources"].values()))["provenance"]
        self.assertEqual(provenance["declared_content_type"], "application/octet-stream")
        self.assertTrue(provenance["mime_inferred"])
        self.assertEqual(provenance["mime_inference_reason"], "finite_xml_prefix_and_extension")
        self.assertTrue(run.search("telemetry")["hits"])
        self.assertFalse(next(iter(snap["sources"].values()))["provenance"]["training_permission"])
        self.assertEqual(CrawlRun.from_snapshot(snap,fetcher=fetcher).snapshot(),snap)

    def test_executable_octet_stream_is_denied_even_with_gpx_suffix(self):
        at=time.time()
        fetcher=OctetScriptedFetcher(b"MZ\x00\x00exe")
        run=CrawlRun.create(CrawlRequest(
            seed_urls=("https://example.com/track.gpx",),
            allowed_hosts=("example.com",),max_depth=0,
            max_requests=4,max_documents=2,max_response_bytes=4096,max_total_bytes=12288,
        ),scope={"tenant_id":"t","owner_id":"o"},consent={
            "consent_id":"octet-media-optin","capture_acknowledged":True,
            "source_rights_acknowledged":True,"expires_at":at+3600,
        },now=at,fetcher=fetcher)
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=at+offset):
                run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                    cancelled=lambda:False,on_checkpoint=lambda snapshot,event:None)
        self.assertEqual(run.snapshot()["usage"]["documents"],0)


if __name__=="__main__":
    unittest.main()
