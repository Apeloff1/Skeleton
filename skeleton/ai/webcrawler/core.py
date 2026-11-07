"""Deterministic, policy-bound crawler core.

The plane is deliberately transport-agnostic: callers provide a Fetcher so tests and
production transports share the same policy/frontier/provenance state machine.
Network transports MUST enforce the same destination policy on every redirect.
"""

from __future__ import annotations

import hashlib
import heapq
import html
import ipaddress
import json
import posixpath
import re
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from .document_formats import (
    ADDITIONAL_TYPES, RESEARCH_ARTIFACT_TYPES,
    HAR_MEDIA_TYPES, PATCH_MEDIA_TYPES, CSL_MEDIA_TYPES,
    TECHNICAL_MEDIA_TYPES, ASSET_TEXT_MEDIA_TYPES, SUPPLY_CHAIN_TYPES,
    SCENE_ASSET_TYPES, PACKAGE_LOCK_TYPES, INTERFACE_TYPES, IIIF_DOCUMENT_TYPES,
    GRAPH_ARTIFACT_TYPES, TILED_ARTIFACT_TYPES, ROBOT_SCENE_TYPES,
    DocumentFormatError, extract_additional_format,
)
from .archive_documents import ARCHIVE_TYPES, extract_archive_document
from .xml_documents import GENERIC_XML_TYPES, extract_xml_evidence
from .html_semantics import HTMLSemanticError, extract_html_semantics
from .html_landmarks import HTMLLandmarkError, extract_html_landmarks
from .html_structured_entities import (
    StructuredHTMLError, extract_html_structured_entities,
)
from .pdf_documents import PDF_MEDIA_TYPE, extract_pdf_document
from .discovery_relations import navigational_relation
from .warc_catalog import WARC_MEDIA_TYPES, extract_warc_catalog
from .research_projection import ResearchFormatError
from .binary_media_metadata import BINARY_MEDIA_TYPES, extract_binary_media_metadata
from .zip_inventory import ZIP_INVENTORY_TYPES, extract_zip_inventory
from .extended_media import EXTENDED_MEDIA_TYPES, extract_extended_media
from .ml_model_artifacts import ML_MODEL_TYPES, extract_ml_model
from .source_structure import (
    SOURCE_STRUCTURE_TYPES, SourceSignatureError, analyze_source_structure,
)

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_ALLOWED_SCHEMES = {"http", "https"}


def canonicalize_url(url: str, *, base: str | None = None) -> str:
    """Return stable HTTP(S) identity, removing fragments and common tracking noise."""
    if not isinstance(url, str) or len(url) > 16384 or any(ord(c) < 32 for c in url):
        raise ValueError("invalid or oversized crawl URL")
    raw = urljoin(base, url) if base else url
    p = urlsplit(raw.strip())
    scheme = p.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES or not p.hostname:
        raise ValueError("only absolute http(s) URLs are crawlable")
    if p.username is not None or p.password is not None:
        raise ValueError("credential-bearing crawl URLs are forbidden")
    host = p.hostname.encode("idna").decode("ascii").lower()
    port = p.port
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    authority = f"[{host}]" if ":" in host else host
    netloc = authority if port is None or default_port else f"{authority}:{port}"
    path = re.sub(r"/{2,}", "/", p.path or "/")
    trailing = path.endswith("/")
    path = posixpath.normpath(path)
    if not path.startswith("/"):
        path = "/" + path
    if trailing and path != "/":
        path += "/"
    pairs = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True, max_num_fields=256)
        if k.lower() not in _TRACKING_KEYS
        and not any(k.lower().startswith(prefix) for prefix in _TRACKING_PREFIXES)
    ]
    query = urlencode(sorted(pairs), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def destination_allowed(host_or_ip: str) -> bool:
    """Fail closed for literal non-public destinations; DNS transports must recheck IPs."""
    try:
        ip = ipaddress.ip_address(host_or_ip.strip("[]"))
    except ValueError:
        return host_or_ip.lower() not in {"localhost", "localhost.localdomain"}
    return bool(ip.is_global)


@dataclass(frozen=True)
class CrawlPolicy:
    user_agent: str = "SkeletonAI-Crawler/1.0"
    max_depth: int = 4
    max_redirects: int = 5
    max_response_bytes: int = 4_000_000
    min_host_delay_seconds: float = 1.0
    max_retries: int = 3
    retry_base_seconds: float = 2.0
    max_retry_delay_seconds: float = 300.0
    max_links_per_document: int = 500
    max_url_length: int = 4096
    max_query_pairs: int = 32
    max_path_segments: int = 64
    robots_ttl_seconds: float = 86_400.0
    retry_statuses: tuple[int, ...] = (408, 425, 429, 500, 502, 503, 504)
    allowed_content_types: tuple[str, ...] = (
        "text/html",
        "text/plain",
        "application/xhtml+xml",
        "text/markdown",
        "text/x-markdown",
        "text/csv",
        "application/csv",
        "application/json",
        "application/ld+json",
        "application/x-ndjson",
        "application/ndjson",
        "application/jsonl",
        "text/x-jsonl",
        "text/x-python",
        "text/x-c",
        "text/x-csrc",
        "text/x-c++src",
        "text/x-rust",
        "text/x-go",
        "text/x-java-source",
        "text/javascript",
        "application/javascript",
        "application/x-javascript",
        "text/x-typescript",
        "application/typescript",
        "text/css",
        "text/x-rst",
        "text/x-asciidoc",
        "text/yaml",
        "text/x-yaml",
        "application/yaml",
        "application/x-yaml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.text",
        "application/epub+zip",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.presentation",
        "application/xml",
        "text/xml",
        "application/x-xml",
        "application/gpx+xml",
        "application/vnd.google-earth.kml+xml",
        "application/pdf",
        "text/vtt",
        "application/x-subrip",
        "text/srt",
        "text/calendar",
        "application/ics",
        "application/x-research-info-systems",
        "text/ris",
        "application/x-bibtex",
        "text/x-bibtex",
        "application/x-ipynb+json",
        "application/vnd.jupyter",
        "application/n-triples",
        "application/n-quads",
        "application/warc",
        "application/x-warc",
        "application/har+json",
        "application/x-har+json",
        "text/x-diff",
        "text/x-patch",
        "application/x-diff",
        "text/patch",
        "application/vnd.citationstyles.csl+json",
        "application/x-csl+json",
        "model/urdf+xml",
        "application/x-urdf+xml",
        "model/sdf+xml",
        "application/x-sdf+xml",
        "application/x-mjcf+xml",
        "model/mjcf+xml",
        "application/x-tiled-tmx+xml",
        "text/x-tiled-tmx",
        "application/x-tiled-tsx+xml",
        "text/x-tiled-tsx",
        "application/x-tiled-map+json",
        "application/vnd.tiled.map+json",
        "application/vnd.safetensors",
        "application/x-safetensors",
        "application/vnd.gguf",
        "application/x-gguf",
        "application/onnx",
        "application/x-onnx",
        "application/graphml+xml",
        "application/x-graphml+xml",
        "application/gexf+xml",
        "application/x-gexf+xml",
        "text/vnd.graphviz",
        "text/x-dot",
        "application/vnd.graphql.introspection+json",
        "application/graphql-response+json",
        "application/vnd.asyncapi+json",
        "application/asyncapi+json",
        "text/x-protobuf",
        "application/x-protobuf-schema",
        "application/vnd.npm.package-lock+json",
        "application/vnd.cargo.lock+toml",
        "text/x-cargo-lock",
        "text/x-go-mod",
        "application/x-go-mod",
        "application/vnd.python.pylock+toml",
        "text/x-pylock",
        "application/vnd.cyclonedx+json",
        "application/spdx+json",
        "application/vnd.openvex+json",
        "application/opds+json",
        "application/vnd.iiif.presentation+json",
        "application/vnd.openarchives.oai-pmh+xml",
        "application/activity+json",
        "application/vnd.activitystreams+json",
        "image/svg+xml",
        "model/ply",
        "application/x-ply",
        "model/off",
        "text/x-off",
        "application/x-godot-scene",
        "text/x-godot-scene",
        "application/x-unity-scene",
        "text/x-unity-scene",
        "model/vnd.usda",
        "application/x-usda",
        "text/x-ldraw",
        "application/x-ldraw",
        "application/rdf+xml",
        "application/geo+json",
        "application/vnd.geo+json",
        "application/openapi+json",
        "application/vnd.oai.openapi+json",
        "application/schema+json",
        "application/vnd.schema+json",
        "image/png",
        "image/jpeg",
        "image/gif",
        "audio/wav",
        "audio/x-wav",
        "audio/vnd.wave",
        "model/obj",
        "text/x-obj",
        "model/gltf+json",
        "application/x-gltf+json",
        "application/zip",
        "application/x-zip-compressed",
        "image/webp",
        "image/x-icon",
        "image/vnd.microsoft.icon",
        "audio/flac",
        "audio/x-flac",
        "audio/ogg",
        "audio/opus",
        "audio/mp4",
        "video/mp4",
        "model/gltf-binary",
        "application/x-gltf-binary",
        "model/stl",
        "application/sla",
        "application/x-tar",
        "application/tar",
        "text/tab-separated-values",
        "application/tsv",
        "application/toml",
        "text/x-toml",
        "text/x-shellscript",
        "application/x-sh",
    )
    allowed_hosts: frozenset[str] | None = None

    def admits(self, url: str) -> bool:
        try:
            p = urlsplit(canonicalize_url(url))
        except (ValueError, UnicodeError):
            return False
        if len(url) > self.max_url_length:
            return False
        if len(parse_qsl(p.query, keep_blank_values=True)) > self.max_query_pairs:
            return False
        if len([x for x in p.path.split("/") if x]) > self.max_path_segments:
            return False
        if not destination_allowed(p.hostname or ""):
            return False
        return self.allowed_hosts is None or (p.hostname or "").lower() in self.allowed_hosts


@dataclass
class CrawlBudget:
    max_requests: int = 1000
    max_bytes: int = 100_000_000
    max_documents: int = 500
    requests: int = 0
    bytes: int = 0
    documents: int = 0

    def can_request(self) -> bool:
        return self.requests < self.max_requests and self.bytes < self.max_bytes

    def charge_response(self, byte_count: int, *, accepted: bool) -> None:
        self.requests += 1
        self.bytes += max(0, byte_count)
        if accepted:
            self.documents += 1

    @property
    def exhausted(self) -> bool:
        return (
            self.requests >= self.max_requests
            or self.bytes >= self.max_bytes
            or self.documents >= self.max_documents
        )


@dataclass(order=True)
class FrontierItem:
    ready_at: float
    priority: float
    sequence: int
    url: str = field(compare=False)
    depth: int = field(compare=False, default=0)
    parent_url: str | None = field(compare=False, default=None)
    attempts: int = field(compare=False, default=0)


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes
    fetched_at: float
    wire_bytes: int | None = None
    wire_hash: str | None = None
    content_encoding: str = "identity"


class Fetcher(Protocol):
    def fetch(self, url: str, *, user_agent: str, max_bytes: int) -> FetchResponse: ...


@dataclass(frozen=True)
class CrawlDocument:
    canonical_url: str
    fetched_url: str
    title: str
    text: str
    content_type: str
    content_hash: str
    fetched_at: float
    source_score: float
    provenance: Mapping[str, object]
    links: tuple[str, ...]

    def retrieval_record(self) -> dict[str, object]:
        return {
            "id": self.content_hash,
            "text": self.text,
            "metadata": {
                "url": self.canonical_url,
                "title": self.title,
                "content_type": self.content_type,
                "source_score": self.source_score,
                "provenance": dict(self.provenance),
            },
        }


class _Extractor(HTMLParser):
    _SKIP = frozenset({"script", "style", "noscript", "svg", "canvas", "template"})

    def __init__(self, *, max_links: int = 500, max_text_chars: int = 1_000_000) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.text: list[str] = []
        self.links: list[str] = []
        self.title: list[str] = []
        self.in_title = False
        self.max_links = max_links
        self.remaining_text = max_text_chars

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._SKIP:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag in ("a", "link") and not self.skip:
            attributes = dict(attrs)
            href = attributes.get("href")
            rel = set((attributes.get("rel") or "").lower().split())
            eligible = tag == "a" and "nofollow" not in rel
            if tag == "link":
                eligible = navigational_relation(
                    rel, media_type=attributes.get("type") or "",
                    hreflang=attributes.get("hreflang") or "",
                )
            if (eligible and href and len(self.links) < self.max_links
                    and len(href) <= 4096):
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        cleaned = " ".join(data.split())
        if cleaned and self.remaining_text > 0:
            cleaned = cleaned[: self.remaining_text]
            self.remaining_text -= len(cleaned)
            self.text.append(cleaned)
            if self.in_title:
                self.title.append(cleaned)


def _source_score(url: str, text: str, status: int) -> float:
    p = urlsplit(url)
    score = 0.35
    if p.scheme == "https":
        score += 0.15
    if status == 200:
        score += 0.15
    if len(text) >= 500:
        score += 0.15
    if p.path.lower().endswith((".pdf", ".zip", ".exe")):
        score -= 0.25
    return max(0.0, min(1.0, score))



def _archive_document_response(
    response: FetchResponse, canonical_url: str, ctype: str,
    text: str, title: str, links: list[str], truncated: bool,
) -> CrawlDocument:
    """Construct source receipts identically to ordinary text extraction."""
    text = html.unescape(" ".join(text.split())).strip()
    if not text:
        raise ValueError("archived source contains no text")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return CrawlDocument(
        canonical_url=canonical_url,
        fetched_url=response.url,
        title=title[:1000],
        text=text,
        content_type=ctype,
        content_hash=digest,
        fetched_at=response.fetched_at,
        source_score=_source_score(canonical_url, text, response.status),
        provenance={
            "schema": "skeleton.ai.crawl.provenance.v1",
            "canonical_url": canonical_url,
            "fetched_url": response.url,
            "fetched_at": response.fetched_at,
            "status": response.status,
            "content_hash": digest,
            "raw_body_hash": response.wire_hash or hashlib.sha256(response.body).hexdigest(),
            "decoded_body_hash": hashlib.sha256(response.body).hexdigest(),
            "wire_bytes": response.wire_bytes if response.wire_bytes is not None else len(response.body),
            "content_encoding": response.content_encoding,
            "parser_text_truncated": truncated,
        },
        links=tuple(links),
    )


def extract_document(
    response: FetchResponse, canonical_url: str, *, max_links: int = 500,
    max_text_chars: int = 1_000_000, link_base_url: str | None = None,
) -> CrawlDocument | None:
    ctype = response.headers.get("content-type", "text/plain").split(";", 1)[0].strip().lower()
    if ctype in ML_MODEL_TYPES:
        try:
            row=extract_ml_model(
                response.body,ctype,max_chars=max_text_chars,
            )
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return _archive_document_response(
            response,canonical_url,ctype,row.text,row.title,[],row.truncated,
        )
    if ctype in EXTENDED_MEDIA_TYPES:
        try:
            row = extract_extended_media(
                response.body, ctype, max_chars=max_text_chars,
            )
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return _archive_document_response(
            response, canonical_url, ctype, row.text, row.title,
            [], row.truncated,
        )
    if ctype in BINARY_MEDIA_TYPES | ZIP_INVENTORY_TYPES:
        try:
            row = (
                extract_binary_media_metadata(
                    response.body, ctype, max_chars=max_text_chars,
                ) if ctype in BINARY_MEDIA_TYPES else
                extract_zip_inventory(response.body, max_chars=max_text_chars)
            )
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return _archive_document_response(
            response, canonical_url, ctype, row.text, row.title,
            [], row.truncated,
        )
    if ctype in WARC_MEDIA_TYPES:
        try:
            row = extract_warc_catalog(response.body, max_chars=max_text_chars)
        except ResearchFormatError as exc:
            raise DocumentFormatError(str(exc)) from exc
        return _archive_document_response(
            response, canonical_url, ctype, row.text, row.title,
            [], row.truncated,
        )
    if ctype == PDF_MEDIA_TYPE:
        pdf = extract_pdf_document(response.body, max_chars=max(512, max_text_chars))
        return _archive_document_response(
            response, canonical_url, ctype, pdf.text, pdf.title, [], pdf.truncated,
        )
    if ctype in ARCHIVE_TYPES:
        extracted = extract_archive_document(
            response.body, ctype, max_chars=max_text_chars,
        )
        text = extracted.text
        title = extracted.title
        links = list(extracted.links)
        parser_text_truncated = extracted.truncated
        # Source encoding is binary: do not decode ZIP bytes as plain text.
        return _archive_document_response(
            response, canonical_url, ctype, text, title,
            links, parser_text_truncated,
        )
    charset = "utf-8"
    match = re.search(r"charset=([^;\s]+)", response.headers.get("content-type", ""), re.IGNORECASE)
    if match:
        charset = match.group(1).strip("\"'")
    if ctype in (RESEARCH_ARTIFACT_TYPES | HAR_MEDIA_TYPES
                 | PATCH_MEDIA_TYPES | CSL_MEDIA_TYPES
                 | TECHNICAL_MEDIA_TYPES | ASSET_TEXT_MEDIA_TYPES
                 | SUPPLY_CHAIN_TYPES | SCENE_ASSET_TYPES
                 | PACKAGE_LOCK_TYPES | INTERFACE_TYPES
                 | GRAPH_ARTIFACT_TYPES | TILED_ARTIFACT_TYPES
                 | ROBOT_SCENE_TYPES | IIIF_DOCUMENT_TYPES):
        # Parser-specific syntax and citations must not be silently altered by
        # replacement decoding or unsupported source charset declarations.
        if charset.casefold().replace("_", "-") not in ("utf-8", "utf8"):
            raise DocumentFormatError("research artifact requires UTF-8")
        try:
            raw = response.body.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise DocumentFormatError("invalid UTF-8 research artifact") from exc
    else:
        try:
            raw = response.body.decode(charset, errors="replace")
        except (LookupError, UnicodeError):
            raw = response.body.decode("utf-8", errors="replace")
    title = ""
    links: list[str] = []
    parser_text_truncated = False
    if ctype in {"text/html", "application/xhtml+xml"}:
        parser = _Extractor(max_links=max_links, max_text_chars=max_text_chars)
        parser.feed(raw)
        text = " ".join(parser.text)
        title = " ".join(parser.title)
        links = parser.links
        try:
            semantics = extract_html_semantics(
                raw, max_chars=min(max_text_chars, 24000),
            )
        except HTMLSemanticError:
            # Semantic annotations are best-effort and have no authority.
            # A malformed JSON-LD/table cannot authorize or block HTML links.
            pass
        else:
            if semantics.text:
                text += "\n" + semantics.text
            parser_text_truncated = semantics.truncated
        try:
            landmarks = extract_html_landmarks(
                raw, max_chars=min(max_text_chars, 8192),
            )
        except HTMLLandmarkError:
            # Landmark enrichment is advisory; it cannot grant or veto links.
            pass
        else:
            if landmarks.text:
                text += "\n" + landmarks.text
            parser_text_truncated |= landmarks.truncated
        try:
            entities = extract_html_structured_entities(
                raw,max_chars=min(max_text_chars,8192),
            )
        except StructuredHTMLError:
            # Curated markup is unreviewed evidence, not an authority source.
            pass
        else:
            if entities.text:
                text += "\n" + entities.text
            parser_text_truncated |= entities.truncated
    elif ctype == "text/plain":
        text = raw
    elif ctype in GENERIC_XML_TYPES:
        parsed = extract_xml_evidence(
            response.body, max_chars=max_text_chars,
        )
        text, title = parsed.text, parsed.title
        links = list(parsed.links)
        parser_text_truncated = parsed.truncated
    elif ctype in ADDITIONAL_TYPES:
        parsed = extract_additional_format(
            raw, ctype, max_chars=max_text_chars, max_links=max_links,
        )
        text, title = parsed.text, parsed.title
        links = list(parsed.links)
        parser_text_truncated = parsed.truncated
        if ctype in SOURCE_STRUCTURE_TYPES:
            # Structurally inspect only the already-acquired, bounded source.
            # Syntax errors are never permission to discard ordinary text.
            try:
                structs = analyze_source_structure(
                    raw, ctype, max_chars=min(8192, max_text_chars),
                )
            except SourceSignatureError:
                pass
            else:
                annotation = "\n" + structs.text
                remaining = max(0, max_text_chars-len(text))
                text += annotation[:remaining]
                parser_text_truncated |= structs.truncated or len(annotation)>remaining
    else:
        return None
    text = html.unescape(" ".join(text.split())).strip()
    if not text:
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    normalized_links: list[str] = []
    for link in links:
        try:
            normalized_links.append(canonicalize_url(link, base=link_base_url or canonical_url))
        except (ValueError, UnicodeError):
            continue
    provenance = {
        "schema": "skeleton.ai.crawl.provenance.v1",
        "canonical_url": canonical_url,
        "fetched_url": response.url,
        "fetched_at": response.fetched_at,
        "status": response.status,
        "content_hash": digest,
        "raw_body_hash": response.wire_hash or hashlib.sha256(response.body).hexdigest(),
        "decoded_body_hash": hashlib.sha256(response.body).hexdigest(),
        "wire_bytes": response.wire_bytes if response.wire_bytes is not None else len(response.body),
        "content_encoding": response.content_encoding,
        "parser_text_truncated": parser_text_truncated,
    }
    return CrawlDocument(
        canonical_url=canonical_url,
        fetched_url=response.url,
        title=title[:1000],
        text=text,
        content_type=ctype,
        content_hash=digest,
        fetched_at=response.fetched_at,
        source_score=_source_score(canonical_url, text, response.status),
        provenance=provenance,
        links=tuple(dict.fromkeys(normalized_links)),
    )


class InMemoryCrawlStore:
    """Reference storage contract; durable stores can implement the same methods."""

    def __init__(self) -> None:
        self.documents: dict[str, CrawlDocument] = {}
        self.url_to_hash: dict[str, str] = {}
        self.checkpoints: dict[str, str] = {}

    def has_url(self, url: str) -> bool:
        return url in self.url_to_hash

    def has_content(self, digest: str) -> bool:
        return digest in self.documents

    def put(self, doc: CrawlDocument) -> bool:
        duplicate = doc.content_hash in self.documents
        self.url_to_hash[doc.canonical_url] = doc.content_hash
        if not duplicate:
            self.documents[doc.content_hash] = doc
        return not duplicate

    def save_checkpoint(self, key: str, state: Mapping[str, object]) -> None:
        self.checkpoints[key] = json.dumps(state, sort_keys=True, separators=(",", ":"))

    def load_checkpoint(self, key: str) -> dict[str, object] | None:
        raw = self.checkpoints.get(key)
        return json.loads(raw) if raw else None


class RobotsCache:
    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._parsers: dict[str, RobotFileParser] = {}
        self._meta: dict[str, dict[str, object]] = {}

    def install(
        self,
        origin: str,
        robots_text: str,
        *,
        fetched_at: float = 0.0,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> None:
        parser = RobotFileParser()
        parser.set_url(origin.rstrip("/") + "/robots.txt")
        parser.parse(robots_text.splitlines())
        # stdlib RobotFileParser matches the *first* applicable rule. RFC 9309
        # instead selects the longest path match, with Allow winning ties.
        # Sort only rule lines within each parsed agent group so a broad
        # Allow: / cannot accidentally override Disallow: /private.
        groups = [*parser.entries]
        if parser.default_entry is not None:
            groups.append(parser.default_entry)
        for group in groups:
            group.rulelines.sort(
                key=lambda rule: (len(rule.path), rule.allowance),
                reverse=True,
            )
        self._parsers[origin] = parser
        self._meta[origin] = {"fetched_at": fetched_at, "etag": etag, "last_modified": last_modified}

    def known(self, url: str) -> bool:
        p = urlsplit(url)
        return f"{p.scheme}://{p.netloc}" in self._parsers

    def fresh(self, url: str, *, now: float, ttl: float) -> bool:
        p = urlsplit(url)
        meta = self._meta.get(f"{p.scheme}://{p.netloc}")
        return bool(meta and now - float(meta["fetched_at"]) < ttl)

    def validators(self, url: str) -> dict[str, str]:
        p = urlsplit(url)
        meta = self._meta.get(f"{p.scheme}://{p.netloc}") or {}
        out = {}
        if meta.get("etag"):
            out["If-None-Match"] = str(meta["etag"])
        if meta.get("last_modified"):
            out["If-Modified-Since"] = str(meta["last_modified"])
        return out

    def touch(self, url: str, *, fetched_at: float) -> None:
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin in self._meta:
            self._meta[origin]["fetched_at"] = fetched_at

    def allowed(self, url: str) -> bool:
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        parser = self._parsers.get(origin)
        # Fail closed until robots policy has explicitly been loaded.
        return parser is not None and parser.can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        p = urlsplit(url)
        parser = self._parsers.get(f"{p.scheme}://{p.netloc}")
        return parser.crawl_delay(self.user_agent) if parser else None

    def request_rate(self, url: str):
        p = urlsplit(url)
        parser = self._parsers.get(f"{p.scheme}://{p.netloc}")
        return parser.request_rate(self.user_agent) if parser else None


class CrawlEngine:
    """Bounded deterministic scheduler with retries, dedupe and resumable state."""

    def __init__(
        self,
        fetcher: Fetcher,
        *,
        policy: CrawlPolicy | None = None,
        budget: CrawlBudget | None = None,
        store: InMemoryCrawlStore | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.policy = policy or CrawlPolicy()
        self.budget = budget or CrawlBudget()
        self.store = store or InMemoryCrawlStore()
        self.robots = RobotsCache(self.policy.user_agent)
        self._frontier: list[FrontierItem] = []
        self._queued: set[str] = set()
        self._seen: set[str] = set()
        self._host_ready: dict[str, float] = {}
        self._seq = 0

    def install_robots(self, origin: str, robots_text: str) -> None:
        self.robots.install(origin, robots_text)

    def enqueue(
        self,
        url: str,
        *,
        depth: int = 0,
        parent_url: str | None = None,
        priority: float = 0.0,
        ready_at: float = 0.0,
    ) -> bool:
        try:
            url = canonicalize_url(url, base=parent_url)
        except (ValueError, UnicodeError):
            return False
        if depth > self.policy.max_depth or not self.policy.admits(url):
            return False
        if url in self._queued or url in self._seen or self.store.has_url(url):
            return False
        self._seq += 1
        # heapq is min-first; negate caller priority so larger means sooner.
        heapq.heappush(self._frontier, FrontierItem(ready_at, -priority, self._seq, url, depth, parent_url))
        self._queued.add(url)
        return True

    def _next(self, now: float) -> FrontierItem | None:
        """Select the best ready item without one delayed host blocking all others."""
        blocked: list[FrontierItem] = []
        selected = None
        while self._frontier:
            item = heapq.heappop(self._frontier)
            host = urlsplit(item.url).hostname or ""
            ready = max(item.ready_at, self._host_ready.get(host, 0.0))
            if ready <= now:
                selected = item
                break
            blocked.append(item)
        for item in blocked:
            heapq.heappush(self._frontier, item)
        if selected is not None:
            self._queued.discard(selected.url)
        return selected

    def _retry(self, item: FrontierItem, *, now: float, delay: float | None = None) -> None:
        if item.attempts >= self.policy.max_retries:
            return
        self._seen.discard(item.url)
        fallback = self.policy.retry_base_seconds * (2**item.attempts)
        retry = min(self.policy.max_retry_delay_seconds, max(0.0, fallback if delay is None else delay))
        self._seq += 1
        heapq.heappush(
            self._frontier,
            FrontierItem(
                now + retry,
                item.priority,
                self._seq,
                item.url,
                item.depth,
                item.parent_url,
                item.attempts + 1,
            ),
        )
        self._queued.add(item.url)

    @staticmethod
    def _retry_after(headers: Mapping[str, str], *, now: float | None = None) -> float | None:
        raw = headers.get("retry-after")
        if raw is None:
            return None
        try:
            return max(0.0, float(raw.strip()))
        except (ValueError, TypeError):
            try:
                target = parsedate_to_datetime(raw.strip()).timestamp()
                return max(0.0, target - (time.time() if now is None else now))
            except (ValueError, TypeError, OverflowError):
                return None

    def load_robots(self, url: str, *, now: float | None = None) -> bool:
        """Load an origin's robots policy once, charging the crawl budget."""
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        at = time.time() if now is None else now
        if self.robots.known(url) and self.robots.fresh(url, now=at, ttl=self.policy.robots_ttl_seconds):
            return True
        if not self.budget.can_request():
            return False
        robots_url = origin + "/robots.txt"
        try:
            from .redirects import fetch_robots_with_policy

            response = fetch_robots_with_policy(
                self, robots_url, now=at, extra_headers=self.robots.validators(url)
            )
        except Exception:  # noqa: BLE001 -- missing robots always denies acquisition
            return False
        body = response.body[:512_000]
        if response.status == 304 and self.robots.known(url):
            self.robots.touch(url, fetched_at=at)
            return True
        if response.status in {404, 410}:
            self.robots.install(
                origin,
                "",
                fetched_at=at,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )
            return True
        if response.status != 200:
            return False
        ctype = response.headers.get("content-type", "text/plain").split(";", 1)[0].lower()
        if ctype not in {"text/plain", "text/html"}:
            return False
        self.robots.install(
            origin,
            body.decode("utf-8", errors="replace"),
            fetched_at=at,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )
        return True

    def step(self, *, now: float | None = None) -> CrawlDocument | None:
        now = time.time() if now is None else now
        if self.budget.exhausted or not self.budget.can_request():
            return None
        item = self._next(now)
        if item is None:
            return None
        if item.url in self._seen:
            return None
        self._seen.add(item.url)
        if not self.robots.known(item.url) and not self.load_robots(item.url, now=now):
            self._seen.discard(item.url)
            if self.budget.can_request():
                self._retry(item, now=now)
            return None
        if not self.budget.can_request():
            self._seen.discard(item.url)
            return None
        if not self.robots.allowed(item.url):
            return None
        # Redirect-aware fetch_with_policy performs the per-hop host cooldown
        # check and commits its reservation. Reserving here first makes that
        # very same first hop appear too early and rejects positive crawl delays.
        host = urlsplit(item.url).hostname or ""
        # Loading robots may have consumed this host's dispatch slot. Preserve the
        # item without spending a retry; fetch_with_policy owns page admission.
        if self._host_ready.get(host, 0.0) > now:
            self._seen.discard(item.url)
            heapq.heappush(
                self._frontier,
                FrontierItem(
                    self._host_ready[host],
                    item.priority,
                    item.sequence,
                    item.url,
                    item.depth,
                    item.parent_url,
                    item.attempts,
                ),
            )
            self._queued.add(item.url)
            return None
        try:
            from .redirects import fetch_with_policy

            response = fetch_with_policy(self, item.url, now=now)
        except Exception as exc:  # noqa: BLE001 -- transport failures enter bounded retry
            from .redirects import RedirectFetchError

            if isinstance(exc, RedirectFetchError) and exc.request_started:
                self.budget.requests += 1
            self._retry(item, now=now)
            return None

        body = response.body[: self.policy.max_response_bytes]
        if response.status in self.policy.retry_statuses:
            self._retry(item, now=now, delay=self._retry_after(response.headers, now=response.fetched_at))
            return None
        ctype = response.headers.get("content-type", "").split(";", 1)[0].lower()
        accepted_type = ctype in self.policy.allowed_content_types
        successful = 200 <= response.status < 300 and accepted_type
        doc = (
            extract_document(
                FetchResponse(response.url, response.status, response.headers, body, response.fetched_at),
                item.url,
            )
            if successful
            else None
        )
        novel = bool(doc and not self.store.has_content(doc.content_hash))
        # fetch_with_policy already charged each network response, including
        # redirect hops, against the request/byte budget. Only a novel,
        # accepted document remains to be charged here. Counting the same
        # request a second time for fetchers without fetch_once exhausted
        # small budgets prematurely and understated crawl availability.
        if novel:
            self.budget.documents += 1
        if not doc:
            return None
        self.store.put(doc)
        if novel and item.depth < self.policy.max_depth and not self.budget.exhausted:
            for link in doc.links[: self.policy.max_links_per_document]:
                self.enqueue(link, depth=item.depth + 1, parent_url=item.url)
        return doc if novel else None

    def checkpoint(self, key: str = "default") -> None:
        state = {
            "schema": "skeleton.ai.crawl.checkpoint.v1",
            "frontier": [asdict(x) for x in sorted(self._frontier)],
            "queued": sorted(self._queued),
            "seen": sorted(self._seen),
            "host_ready": self._host_ready,
            "sequence": self._seq,
            "budget": asdict(self.budget),
        }
        self.store.save_checkpoint(key, state)

    def restore(self, key: str = "default") -> bool:
        state = self.store.load_checkpoint(key)
        if not state or state.get("schema") != "skeleton.ai.crawl.checkpoint.v1":
            return False
        items = [FrontierItem(**x) for x in state["frontier"]]
        urls = [item.url for item in items]
        if len(urls) != len(set(urls)):
            return False
        queued = set(state["queued"])
        if queued != set(urls):
            return False
        self._frontier = items
        heapq.heapify(self._frontier)
        self._queued = queued
        self._seen = set(state["seen"])
        self._host_ready = {str(k): float(v) for k, v in state["host_ready"].items()}
        self._seq = int(state["sequence"])
        for k, v in state["budget"].items():
            setattr(self.budget, k, v)
        return True

    def retrieval_batch(self) -> list[dict[str, object]]:
        return [
            doc.retrieval_record()
            for doc in sorted(self.store.documents.values(), key=lambda d: d.canonical_url)
        ]
