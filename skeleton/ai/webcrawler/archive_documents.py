"""Bounded, no-execution Office/EPUB text acquisition for the canonical crawler.

DOCX, ODT, and EPUB are read from already-admitted, byte-budgeted responses.
The ZIP reader never opens filesystem paths or fetches document references.
Media, macros, embedded objects, scripts, remote resources, hyperlinks, and
relationships are deliberately inert; the result is unreviewed text evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import io
import posixpath
from pathlib import PurePosixPath
import re
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser


ARCHIVE_TYPES = frozenset({
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "application/epub+zip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
})
MAX_MEMBERS = 256
MAX_UNCOMPRESSED = 8_388_608
MAX_XML_PART = 2_097_152
MAX_XML_NODES = 20_000
MAX_XML_DEPTH = 48
MAX_EPUB_CHAPTERS = 96
ZIP_RATIO_CEILING = 300
_XML_UNSAFE = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.I)
DOC_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ODT_TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
ODT_OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
DC_NS = "http://purl.org/dc/elements/1.1/"
OPF_NS = "http://www.idpf.org/2007/opf"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"


class ArchiveDocumentError(ValueError):
    """Invalid or unbounded external document. No partial text is retained."""


@dataclass(frozen=True)
class ArchivedText:
    text: str
    title: str
    links: tuple[str, ...] = ()
    truncated: bool = False
    body_executed: bool = False
    reference_trusted: bool = False
    archive_validated: bool = True


def _name(name: str) -> str:
    if (
        not isinstance(name, str) or not 1 <= len(name) <= 1024
        or name.startswith("/") or "\\" in name
        or "\x00" in name or "\r" in name or "\n" in name
    ):
        raise ArchiveDocumentError("archive has an unsafe member name")
    parts = PurePosixPath(name).parts
    if not parts or any(part in ("", ".", "..") for part in name.split("/")):
        raise ArchiveDocumentError("archive member escapes its container")
    if ":" in parts[0]:
        raise ArchiveDocumentError("archive member has a drive or scheme")
    return name


class BoundedArchive:
    """Validate the entire central directory before reading selected members."""

    def __init__(self, data: bytes):
        if type(data) is not bytes or not data or len(data) > 2_097_152:
            raise ArchiveDocumentError("compressed archive exceeds acquisition bound")
        try:
            self.zip = zipfile.ZipFile(io.BytesIO(data))
            members = self.zip.infolist()
        except (zipfile.BadZipFile, OSError, ValueError) as exc:
            raise ArchiveDocumentError("malformed Office/EPUB ZIP") from exc
        if not 1 <= len(members) <= MAX_MEMBERS:
            raise ArchiveDocumentError("archive member count outside finite budget")
        self.files: dict[str, zipfile.ZipInfo] = {}
        uncompressed = 0
        for info in members:
            name = _name(info.filename.rstrip("/"))
            if info.is_dir():
                continue
            if name in self.files:
                raise ArchiveDocumentError("duplicate archive path")
            if info.flag_bits & 1:
                raise ArchiveDocumentError("encrypted archive cannot be inspected")
            kind = (info.external_attr >> 16) & 0o170000
            if kind not in (0, 0o100000):
                raise ArchiveDocumentError("archive contains symlink or special member")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ArchiveDocumentError("unsupported compressed member")
            if info.file_size < 0 or info.file_size > MAX_XML_PART:
                raise ArchiveDocumentError("oversized individual archive member")
            if info.file_size and (
                info.compress_size <= 0
                or info.file_size > info.compress_size * ZIP_RATIO_CEILING
            ):
                raise ArchiveDocumentError("archive decompression ratio exceeded")
            uncompressed += info.file_size
            if uncompressed > MAX_UNCOMPRESSED:
                raise ArchiveDocumentError("archive expansion exceeds finite budget")
            self.files[name] = info

    def read(self, name: str) -> bytes:
        _name(name)
        if name not in self.files:
            raise ArchiveDocumentError("required document part not present")
        info = self.files[name]
        try:
            # ZIP CRC is verified by ZipFile.open/read. Length is verified twice,
            # since central directory sizes are untrusted until decompressed.
            with self.zip.open(info) as stream:
                data = stream.read(MAX_XML_PART + 1)
                if stream.read(1):
                    raise ArchiveDocumentError("document part exceeds read cap")
        except (zipfile.BadZipFile, RuntimeError, OSError, EOFError, zlib_error()) as exc:
            raise ArchiveDocumentError("archive payload failed integrity validation") from exc
        if len(data) != info.file_size or len(data) > MAX_XML_PART:
            raise ArchiveDocumentError("archive part declared size mismatch")
        return data


def zlib_error():
    # zlib.error is referenced lazily to avoid adding an optional dependency.
    import zlib
    return zlib.error


def _xml(data: bytes) -> ET.Element:
    if (
        not data or len(data) > MAX_XML_PART or b"\x00" in data
        or _XML_UNSAFE.search(data)
        or data.startswith((b"\xff\xfe", b"\xfe\xff"))
    ):
        raise ArchiveDocumentError("unsafe or oversized XML document part")
    try:
        decoded = data.decode("utf-8-sig", errors="strict")
        root = ET.fromstring(decoded)
    except (UnicodeError, ET.ParseError, RecursionError) as exc:
        raise ArchiveDocumentError("invalid UTF-8 document XML") from exc
    stack = [(root, 1)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_XML_NODES or depth > MAX_XML_DEPTH:
            raise ArchiveDocumentError("XML node or depth bound exceeded")
        stack.extend((child, depth + 1) for child in node)
    return root


def _text_bound(rows: list[str], max_chars: int, title: str) -> ArchivedText:
    compact = "\n".join(" ".join(row.split()) for row in rows if row.strip()).strip()
    if not compact:
        raise ArchiveDocumentError("document has no extractable text")
    return ArchivedText(
        compact[:max_chars], title[:512], truncated=len(compact) > max_chars,
    )


def _docx(archive: BoundedArchive, max_chars: int) -> ArchivedText:
    document = _xml(archive.read("word/document.xml"))
    if document.tag != f"{{{DOC_NS}}}document":
        raise ArchiveDocumentError("unexpected DOCX document root")
    rows: list[str] = []
    for part in (
        "word/document.xml", "word/footnotes.xml",
        "word/endnotes.xml", "word/comments.xml",
    ):
        if part not in archive.files:
            continue
        root = document if part == "word/document.xml" else _xml(archive.read(part))
        for paragraph in root.iter(f"{{{DOC_NS}}}p"):
            row = "".join(
                element.text or "" if element.tag == f"{{{DOC_NS}}}t"
                else "\t" if element.tag == f"{{{DOC_NS}}}tab"
                else ""
                for element in paragraph.iter()
            ).strip()
            if row:
                rows.append(row)
            if len(rows) > 8192:
                raise ArchiveDocumentError("DOCX paragraph budget exceeded")
    title = ""
    if "docProps/core.xml" in archive.files:
        meta = _xml(archive.read("docProps/core.xml"))
        for node in meta.iter():
            if node.tag == f"{{{DC_NS}}}title" and node.text:
                title = node.text
                break
    if not title and rows:
        title = rows[0][:128]
    return _text_bound(rows, max_chars, title)


def _odt(archive: BoundedArchive, max_chars: int) -> ArchivedText:
    root = _xml(archive.read("content.xml"))
    if root.tag != f"{{{ODT_OFFICE_NS}}}document-content":
        raise ArchiveDocumentError("unexpected ODT document root")
    rows = []
    for node in root.iter():
        if node.tag not in (f"{{{ODT_TEXT_NS}}}p", f"{{{ODT_TEXT_NS}}}h"):
            continue
        content = "".join(node.itertext()).strip()
        if content:
            rows.append(content)
        if len(rows) > 8192:
            raise ArchiveDocumentError("ODT paragraph budget exceeded")
    title = rows[0][:128] if rows else ""
    if "meta.xml" in archive.files:
        meta = _xml(archive.read("meta.xml"))
        for node in meta.iter():
            if node.tag == f"{{{DC_NS}}}title" and node.text:
                title = node.text
                break
    return _text_bound(rows, max_chars, title)


class _XHTMLText(HTMLParser):
    SKIP = {"script", "style", "svg", "noscript", "template", "iframe"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.skip = 0
        self.elements = 0
        self.size = 0

    def handle_starttag(self, tag, attrs):
        self.elements += 1
        if self.elements > MAX_XML_NODES:
            raise ArchiveDocumentError("EPUB HTML element budget exceeded")
        if tag.lower() in self.SKIP:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.skip:
            return
        self.size += len(data)
        if self.size > MAX_XML_PART:
            raise ArchiveDocumentError("EPUB text exceeds part text budget")
        self.chunks.append(data)


def _container_path(name: str, href: str) -> str:
    if (
        not isinstance(href, str) or not href or len(href) > 512
        or "://" in href or "?" in href or "#" in href
        or href.startswith(("/", "\\")) or "\\" in href
    ):
        raise ArchiveDocumentError("EPUB manifest has external or unsafe reference")
    # Relative references may use parent segments only within the ZIP root.
    base = posixpath.dirname(name)
    resolved = posixpath.normpath(posixpath.join(base, href))
    if resolved.startswith("../") or resolved == ".." or resolved.startswith("/"):
        raise ArchiveDocumentError("EPUB path escapes container root")
    return _name(resolved)


def _epub(archive: BoundedArchive, max_chars: int) -> ArchivedText:
    container = _xml(archive.read("META-INF/container.xml"))
    rootfiles = [
        node.get("full-path") for node in container.iter()
        if node.tag == f"{{{CONTAINER_NS}}}rootfile"
    ]
    if len(rootfiles) != 1 or not isinstance(rootfiles[0], str):
        raise ArchiveDocumentError("EPUB container needs one root package")
    package_path = _name(rootfiles[0])
    package = _xml(archive.read(package_path))
    if package.tag != f"{{{OPF_NS}}}package":
        raise ArchiveDocumentError("invalid EPUB OPF package root")
    manifest: dict[str, str] = {}
    order: list[str] = []
    title = ""
    for node in package.iter():
        if node.tag == f"{{{DC_NS}}}title" and node.text and not title:
            title = node.text
        if node.tag == f"{{{OPF_NS}}}item":
            ident, href = node.get("id"), node.get("href")
            media = node.get("media-type")
            if not ident or len(ident) > 128 or ident in manifest:
                raise ArchiveDocumentError("duplicate/invalid EPUB manifest id")
            if media == "application/xhtml+xml":
                manifest[ident] = _container_path(package_path, href)
            else:
                manifest[ident] = ""
        if node.tag == f"{{{OPF_NS}}}itemref":
            ref = node.get("idref")
            if not ref or len(ref) > 128:
                raise ArchiveDocumentError("invalid EPUB spine reference")
            if node.get("linear", "yes") != "no":
                order.append(ref)
    if not 1 <= len(order) <= MAX_EPUB_CHAPTERS:
        raise ArchiveDocumentError("EPUB chapter count exceeds capacity")
    rows = []
    for ident in order:
        path = manifest.get(ident)
        if not path:
            raise ArchiveDocumentError("EPUB spine references an unsupported chapter")
        # XHTML is XML; validate DTD, entity declarations, size, depth first.
        part = archive.read(path)
        _xml(part)
        parser = _XHTMLText()
        try:
            parser.feed(part.decode("utf-8-sig", errors="strict"))
            parser.close()
        except (UnicodeError, ValueError) as exc:
            raise ArchiveDocumentError("invalid EPUB chapter markup") from exc
        rows.append(" ".join(" ".join(parser.chunks).split()))
        if sum(map(len, rows)) > MAX_XML_PART * 2:
            raise ArchiveDocumentError("EPUB text expansion exceeds capacity")
    if not title:
        title = rows[0][:128] if rows else ""
    return _text_bound(rows, max_chars, title)


def extract_archive_document(
    body: bytes, media_type: str, *, max_chars: int = 524288,
) -> ArchivedText:
    """Extract source-only, inert document text from finite ZIP-based formats."""
    if media_type not in ARCHIVE_TYPES:
        raise ArchiveDocumentError("unsupported archive document media type")
    if type(max_chars) is not int or not 1 <= max_chars <= 2_097_152:
        raise ArchiveDocumentError("invalid source text capacity")
    archive = BoundedArchive(body)
    try:
        from .office_suites import OFFICE_SUITE_TYPES, extract_office_suite
        if media_type in OFFICE_SUITE_TYPES:
            return extract_office_suite(archive, media_type, max_chars=max_chars)
        if media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return _docx(archive, max_chars)
        if media_type == "application/vnd.oasis.opendocument.text":
            return _odt(archive, max_chars)
        return _epub(archive, max_chars)
    finally:
        archive.zip.close()
