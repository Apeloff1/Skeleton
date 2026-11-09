"""Real guarded PDF text extraction and canonical replay qualification."""
from __future__ import annotations

import io
import time
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from skeleton.ai.webcrawler.pdf_documents import (
    extract_pdf_document, PDFDocumentError,
)
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun


def pdf_fixture(pages=1, encrypted=False):
    writer = PdfWriter()
    writer.add_metadata({"/Title": "Original Flight Manual"})
    for index in range(pages):
        page = writer.add_blank_page(width=500, height=400)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        ref = writer._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): ref,
            }),
        })
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 14 Tf 20 350 Td (Flight mechanics archive {index}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("private")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class BoundedPDFTests(unittest.TestCase):
    def test_extract_real_pdf_page_text(self):
        record = extract_pdf_document(pdf_fixture())
        self.assertIn("Flight mechanics archive", record.text)
        self.assertEqual(record.title, "Original Flight Manual")
        self.assertFalse(record.body_executed)
        self.assertFalse(record.network_used)
        self.assertFalse(record.reference_trusted)
        self.assertEqual(record.links, ())

    def test_multpage_pdf_extracts_separate_page_records(self):
        result = extract_pdf_document(pdf_fixture(pages=2))
        self.assertIn("Page 1:", result.text)
        self.assertIn("Page 2:", result.text)

    def test_encrypted_pdf_rejected(self):
        with self.assertRaises(PDFDocumentError):
            extract_pdf_document(pdf_fixture(encrypted=True))

    def test_oversized_page_count_rejected(self):
        with self.assertRaises(PDFDocumentError):
            extract_pdf_document(pdf_fixture(pages=65))

    def test_pdf_magic_and_resource_bounds(self):
        for payload in (b"notpdf", b"%PDF-bad", b""):
            with self.subTest(payload=payload), self.assertRaises(PDFDocumentError):
                extract_pdf_document(payload)
        with self.assertRaises(PDFDocumentError):
            extract_pdf_document(pdf_fixture(), max_chars=10)
        with self.assertRaises(PDFDocumentError):
            extract_pdf_document(pdf_fixture(), deadline_seconds=30)


class PDFTransport:
    timeout_seconds = 5
    transport_mode = "scripted_guarded_pdf"
    def __init__(self, body):
        self.body = body
        self.calls = []
    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResponse(url, 200, {"content-type":"text/plain"}, b"User-agent: *\nAllow: /\n", time.time())
        if url != "https://example.com/flight.pdf" or len(self.body) > max_bytes:
            raise AssertionError("unexpected or unbounded transport")
        return FetchResponse(url, 200, {"content-type":"application/pdf"}, self.body, time.time())


class CanonicalPDFTests(unittest.TestCase):
    def create(self, data):
        at = time.time()
        fetcher = PDFTransport(data)
        run = CrawlRun.create(CrawlRequest(
            seed_urls=("https://example.com/flight.pdf",), allowed_hosts=("example.com",),
            max_depth=0, max_requests=4, max_documents=2,
            max_response_bytes=16384, max_total_bytes=32768,
            min_host_delay_seconds=.25,
        ), scope={"tenant_id":"t","owner_id":"o"}, consent={
            "consent_id":"pdf-capture-consent",
            "capture_acknowledged":True, "source_rights_acknowledged":True,
            "expires_at":at+3600,
        }, now=at, fetcher=fetcher)
        return run, fetcher, at

    def tick(self, run, at):
        with patch("skeleton.ai.webcrawler.operations.time.time", return_value=at):
            run.run_slice(max_steps=1,max_seconds=8,authorize=lambda:None,
                cancelled=lambda:False,on_checkpoint=lambda snapshot,event:None)

    def test_pdf_is_searchable_source_and_replays_identically(self):
        run, fetcher, at = self.create(pdf_fixture())
        self.tick(run, at+1)
        self.tick(run, at+3)
        snap=run.snapshot()
        self.assertEqual(snap["usage"]["documents"],1)
        source=next(iter(snap["sources"].values()))
        self.assertEqual(source["content_type"],"application/pdf")
        self.assertEqual(source["review_state"],"unreviewed")
        self.assertFalse(source["provenance"]["training_permission"])
        self.assertTrue(run.search("flight")["hits"])
        self.assertEqual(CrawlRun.from_snapshot(snap,fetcher=fetcher).snapshot(),snap)

    def test_encrypted_pdf_never_retained(self):
        run, fetcher, at = self.create(pdf_fixture(encrypted=True))
        self.tick(run,at+1)
        self.tick(run,at+3)
        self.assertEqual(run.snapshot()["usage"]["documents"],0)


if __name__=="__main__":
    unittest.main()
