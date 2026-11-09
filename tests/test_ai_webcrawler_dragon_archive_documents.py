"""Real DOCX/ODT/EPUB acquisition, ZIP containment and replay tests."""
from __future__ import annotations

import io
import time
import unittest
import zipfile
from unittest.mock import patch

from skeleton.ai.webcrawler.archive_documents import (
    ARCHIVE_TYPES, ArchiveDocumentError, extract_archive_document,
)
from skeleton.ai.webcrawler.core import FetchResponse, extract_document
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ODT = "application/vnd.oasis.opendocument.text"
EPUB = "application/epub+zip"

def build_zip(entries, compression=zipfile.ZIP_DEFLATED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as writer:
        for name, content in entries.items():
            writer.writestr(name, content)
    return stream.getvalue()

def docx():
    return build_zip({
        "word/document.xml": (
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:body><w:p><w:r><w:t>Original aircraft archive</w:t></w:r></w:p>'
            b'<w:p><w:r><w:t>Flight simulations and research</w:t></w:r></w:p>'
            b'<w:p><w:r><w:instrText>not source code to execute</w:instrText></w:r></w:p>'
            b'</w:body></w:document>'
        ),
        "docProps/core.xml": b'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Flight Manual</dc:title></cp:coreProperties>',
    })

def odt():
    return build_zip({
        "content.xml": b'<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text><text:h>Original Aircraft</text:h><text:p>Flight physics archive.</text:p></office:text></office:body></office:document-content>',
    })

def epub():
    return build_zip({
        "META-INF/container.xml": b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/package.opf"/></rootfiles></container>',
        "OPS/package.opf": b'<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>Original Flight Handbook</dc:title></metadata><manifest><item id="chapter1" href="chapters/1.xhtml" media-type="application/xhtml+xml"/><item id="cover" href="images/cover.png" media-type="image/png"/></manifest><spine><itemref idref="chapter1"/></spine></package>',
        "OPS/chapters/1.xhtml": b'<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Flight mechanics</h1><p>Chapter one has documented physics and propulsion.</p><script>NOT EXECUTED</script></body></html>',
        "OPS/images/cover.png": b"not parsed as image",
    })

class DocumentArchiveParserTests(unittest.TestCase):
    def test_each_office_and_book_format_has_retrievable_text(self):
        for content_type, body, keyword in (
            (DOCX, docx(), "aircraft"), (ODT, odt(), "physics"),
            (EPUB, epub(), "propulsion"),
        ):
            with self.subTest(content_type=content_type):
                parsed = extract_archive_document(body, content_type)
                self.assertIn(keyword, parsed.text.casefold())
                self.assertFalse(parsed.body_executed)
                self.assertFalse(parsed.reference_trusted)
                self.assertEqual(parsed.links, ())

    def test_docx_excludes_instructional_metadata(self):
        parsed = extract_archive_document(docx(), DOCX)
        self.assertEqual(parsed.title, "Flight Manual")
        self.assertNotIn("not source code to execute", parsed.text)
        self.assertIn("Flight simulations", parsed.text)

    def test_epub_title_and_chapter_not_binary(self):
        parsed = extract_archive_document(epub(), EPUB)
        self.assertEqual(parsed.title, "Original Flight Handbook")
        self.assertNotIn("not parsed as image", parsed.text)

    def test_document_length_bound_is_explicit(self):
        parsed = extract_archive_document(docx(), DOCX, max_chars=20)
        self.assertTrue(parsed.truncated)
        self.assertEqual(len(parsed.text), 20)

    def test_nested_and_absolute_zip_paths_are_rejected(self):
        for name in ("../../word/document.xml", "/root/document.xml", "C:/drive.xml"):
            with self.subTest(name=name), self.assertRaises(ArchiveDocumentError):
                extract_archive_document(build_zip({name: b"a"}), DOCX)

    def test_encrypted_member_and_symlink_are_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as writer:
            link = zipfile.ZipInfo("word/document.xml")
            link.create_system = 3
            link.external_attr = (0o120777 << 16)
            writer.writestr(link, b"a")
        with self.assertRaises(ArchiveDocumentError):
            extract_archive_document(stream.getvalue(), DOCX)

    def test_duplicate_entries_are_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as writer:
            writer.writestr("word/document.xml", b"one")
            writer.writestr("word/document.xml", b"two")
        with self.assertRaises(ArchiveDocumentError):
            extract_archive_document(stream.getvalue(), DOCX)

    def test_bomb_ratio_is_rejected(self):
        data = build_zip({"word/document.xml": b"A" * 1_000_000})
        with self.assertRaises(ArchiveDocumentError):
            extract_archive_document(data, DOCX)

    def test_dtd_is_rejected_even_inside_valid_docx(self):
        data = build_zip({"word/document.xml": b'<!DOCTYPE w:document [<!ENTITY x SYSTEM "file:///etc/passwd">]><w:document/>'})
        with self.assertRaises(ArchiveDocumentError):
            extract_archive_document(data, DOCX)

    def test_epub_manifest_cannot_escape_container(self):
        entries = {
            "META-INF/container.xml": b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/package.opf"/></rootfiles></container>',
            "OPS/package.opf": b'<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="chapter1" href="../../private.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter1"/></spine></package>',
        }
        with self.assertRaises(ArchiveDocumentError):
            extract_archive_document(build_zip(entries), EPUB)

    def test_missing_required_document_part_rejects(self):
        with self.assertRaises(ArchiveDocumentError):
            extract_archive_document(build_zip({"word/media/image.png": b"garbage"}), DOCX)

    def test_unsupported_media_type_denied(self):
        with self.assertRaises(ArchiveDocumentError):
            extract_archive_document(docx(), "application/zip")

    def test_extraction_requires_actual_bytes(self):
        with self.assertRaises(ArchiveDocumentError):
            extract_archive_document(b"not-a-zip", DOCX)


class ScriptedArchiveTransport:
    timeout_seconds = 3
    transport_mode = "strict_in_memory_archive_test"
    def __init__(self, media, data):
        self.media, self.data = media, data
        self.calls = []

    def fetch_once(self, url, *, user_agent, max_bytes):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResponse(url, 200, {"content-type": "text/plain"}, b"User-agent: *\nAllow: /\n", time.time())
        if url != "https://example.com/manual":
            raise AssertionError("unexpected destination")
        if len(self.data) > max_bytes:
            raise ValueError("reserved bytes exceeded")
        return FetchResponse(url, 200, {"content-type": self.media}, self.data, time.time())


class CanonicalArchiveCaptureTests(unittest.TestCase):
    def test_each_format_is_real_searchable_unreviewed_capture(self):
        for media, body in ((DOCX, docx()), (ODT, odt()), (EPUB, epub())):
            with self.subTest(media=media):
                at = time.time()
                fetcher = ScriptedArchiveTransport(media, body)
                run = CrawlRun.create(CrawlRequest(
                    seed_urls=("https://example.com/manual",),
                    allowed_hosts=("example.com",), max_depth=0,
                    max_requests=4, max_documents=2, max_response_bytes=16384,
                    max_total_bytes=32768, min_host_delay_seconds=.25,
                ), scope={"tenant_id": "t", "owner_id": "o"}, consent={
                    "consent_id": "archive-consent",
                    "capture_acknowledged": True,
                    "source_rights_acknowledged": True,
                    "expires_at": at + 3600,
                }, now=at, fetcher=fetcher)
                for offset in (1, 3):
                    with patch("skeleton.ai.webcrawler.operations.time.time", return_value=at + offset):
                        run.run_slice(
                            max_steps=1, max_seconds=1, authorize=lambda: None,
                            cancelled=lambda: False,
                            on_checkpoint=lambda snapshot, event: None,
                        )
                snap = run.snapshot()
                self.assertEqual(snap["usage"]["requests"], 2)
                self.assertEqual(snap["usage"]["documents"], 1)
                source = next(iter(snap["sources"].values()))
                self.assertEqual(source["content_type"], media)
                self.assertEqual(source["review_state"], "unreviewed")
                self.assertFalse(source["provenance"]["training_permission"])
                self.assertFalse(source["provenance"]["raw_bytes_retained"])
                self.assertTrue(run.search("flight")["hits"])
                self.assertEqual(CrawlRun.from_snapshot(snap, fetcher=fetcher).snapshot(), snap)

    def test_unsafe_archive_does_not_enter_evidence_store(self):
        at = time.time()
        fetcher = ScriptedArchiveTransport(DOCX, build_zip({"../unsafe": b"evil"}))
        run = CrawlRun.create(CrawlRequest(
            seed_urls=("https://example.com/manual",), allowed_hosts=("example.com",),
            max_depth=0, max_requests=4, max_documents=2, max_response_bytes=4096,
            max_total_bytes=8192,
        ), scope={"tenant_id": "t", "owner_id": "o"}, consent={
            "consent_id": "archive-consent", "capture_acknowledged": True,
            "source_rights_acknowledged": True, "expires_at": at + 3600,
        }, now=at, fetcher=fetcher)
        for offset in (1, 3):
            with patch("skeleton.ai.webcrawler.operations.time.time", return_value=at + offset):
                run.run_slice(max_steps=1, max_seconds=1, authorize=lambda: None, cancelled=lambda: False, on_checkpoint=lambda snapshot, event: None)
        self.assertEqual(run.snapshot()["usage"]["documents"], 0)
