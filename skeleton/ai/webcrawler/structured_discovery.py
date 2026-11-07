"""Bounded, policy-filtered XML sitemap and syndication feed discovery.

This is production link discovery for the canonical CrawlRun transport, not
an evidence/training source or an alternative network client. Sitemap and
feed contents are untrusted. Only exact committed, policy-admissible links
can enter the existing frontier, where the canonical worker *still* enforces
robots, DNS/socket egress, cumulative budgets and consent before fetching.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zlib

from .core import CrawlPolicy, canonicalize_url


XML_MEDIA = frozenset({
    "application/xml", "text/xml", "application/rss+xml",
    "application/atom+xml",
})
GZIP_MEDIA = frozenset({"application/gzip", "application/x-gzip"})
SUPPORTED_MEDIA = XML_MEDIA | GZIP_MEDIA
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
ATOM_NS = "http://www.w3.org/2005/Atom"
MAX_XML_BYTES = 1_048_576
MAX_XML_ELEMENTS = 16_384
MAX_XML_DEPTH = 32
MAX_DISCOVERY_LINKS = 256
_FORBIDDEN = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.I)
_DECL_ENCODING = re.compile(
    rb"<\?xml\s+[^?]*\bencoding\s*=\s*['\"]([^'\"]+)['\"]",
    re.I,
)


class DiscoveryError(ValueError):
    """Malformed or oversized untrusted discovery content; fail closed."""


@dataclass(frozen=True)
class StructuredDiscovery:
    kind: str
    links: tuple[str, ...]
    examined_entries: int
    discarded_entries: int
    capped: bool
    source_text_retained: bool = False
    new_authority_granted: bool = False


def _local(tag: str) -> tuple[str, str]:
    if not isinstance(tag, str):
        raise DiscoveryError("non-string XML tag")
    if tag.startswith("{"):
        ns, _, local = tag[1:].partition("}")
        return ns, local
    return "", tag


def _xml_bytes(body: bytes, media_type: str, url: str) -> bytes:
    if not isinstance(body, bytes) or not body:
        raise DiscoveryError("empty structured response")
    if media_type in GZIP_MEDIA:
        if not urlsplit(url).path.lower().endswith(".xml.gz"):
            raise DiscoveryError("gzip discovery is limited to sitemap XML URLs")
        if len(body) > MAX_XML_BYTES:
            raise DiscoveryError("compressed sitemap is oversized")
        try:
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            result = decoder.decompress(body, MAX_XML_BYTES + 1)
        except zlib.error as exc:
            raise DiscoveryError("malformed sitemap gzip") from exc
        if (len(result) > MAX_XML_BYTES or not decoder.eof
                or decoder.unconsumed_tail or decoder.unused_data):
            raise DiscoveryError("oversized, incomplete or concatenated sitemap gzip")
        body = result
    if len(body) > MAX_XML_BYTES or not body:
        raise DiscoveryError("structured document exceeds bounded XML size")
    if 0 in body:
        raise DiscoveryError("NUL bytes cannot appear in UTF-8 discovery XML")
    if _FORBIDDEN.search(body):
        raise DiscoveryError("DTD and entity declarations are not accepted")
    # No alternate character set is required for crawled link identity.
    # Avoid UTF-16/32 byte encodings that could obscure byte-level DTD checks.
    if body.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00")):
        raise DiscoveryError("unsupported XML byte encoding")
    declaration = _DECL_ENCODING.match(body[:256].lstrip(b"\xef\xbb\xbf"))
    if declaration and declaration.group(1).lower().replace(b"-", b"") != b"utf8":
        raise DiscoveryError("only UTF-8 discovery XML is accepted")
    try:
        body.decode("utf-8-sig", errors="strict")
    except UnicodeError as exc:
        raise DiscoveryError("invalid UTF-8 structured document") from exc
    return body


def _safe_tree(body: bytes) -> ET.Element:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise DiscoveryError("invalid structured XML") from exc
    count, stack = 0, [(root, 1)]
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_XML_ELEMENTS or depth > MAX_XML_DEPTH:
            raise DiscoveryError("XML tree exceeds element or nesting capacity")
        stack.extend((child, depth + 1) for child in node)
    return root


def _entries(root: ET.Element, kind: str):
    if kind in ("sitemap_urlset", "sitemap_index"):
        desired = "url" if kind == "sitemap_urlset" else "sitemap"
        for entry in root:
            ns, local = _local(entry.tag)
            if local != desired or ns not in ("", SITEMAP_NS):
                continue
            for child in entry:
                child_ns, child_local = _local(child.tag)
                if child_local == "loc" and child_ns in ("", SITEMAP_NS):
                    yield (child.text or "").strip()
                    break
    elif kind == "rss_feed":
        for channel in root:
            if _local(channel.tag) != ("", "channel"):
                continue
            for entry in channel:
                if _local(entry.tag) != ("", "item"):
                    continue
                for child in entry:
                    if _local(child.tag) == ("", "link"):
                        yield (child.text or "").strip()
                        break
    elif kind == "atom_feed":
        for entry in root:
            if _local(entry.tag) not in ((ATOM_NS, "entry"), ("", "entry")):
                continue
            for child in entry:
                if _local(child.tag) not in ((ATOM_NS, "link"), ("", "link")):
                    continue
                if child.attrib.get("rel", "alternate") != "alternate":
                    continue
                if child.attrib.get("type", "text/html") not in (
                    "text/html", "application/xhtml+xml",
                ):
                    continue
                yield child.attrib.get("href", "").strip()
                break


def parse_structured_discovery(
    body: bytes, *, media_type: str, document_url: str, policy: CrawlPolicy,
    max_links: int = 128, max_entries: int = 512,
) -> StructuredDiscovery:
    if not isinstance(policy, CrawlPolicy):
        raise TypeError("canonical immutable crawl policy required")
    if media_type not in SUPPORTED_MEDIA:
        raise DiscoveryError("unsupported structured response type")
    if (type(max_links) is not int or not 1 <= max_links <= MAX_DISCOVERY_LINKS
            or type(max_entries) is not int or not 1 <= max_entries <= 1024):
        raise ValueError("invalid structured discovery limits")
    canonical = canonicalize_url(document_url)
    if canonical != document_url or not policy.admits(canonical):
        raise DiscoveryError("structured source URL outside immutable crawl scope")
    document = _xml_bytes(body, media_type, document_url)
    root = _safe_tree(document)
    namespace, local = _local(root.tag)
    if local == "urlset" and namespace in ("", SITEMAP_NS):
        kind = "sitemap_urlset"
    elif local == "sitemapindex" and namespace in ("", SITEMAP_NS):
        kind = "sitemap_index"
    elif local == "rss" and namespace == "":
        kind = "rss_feed"
    elif local == "feed" and namespace in ("", ATOM_NS):
        kind = "atom_feed"
    else:
        raise DiscoveryError("unsupported XML discovery root")
    seen = set()
    links = []
    examined = rejected = 0
    capped = False
    for value in _entries(root, kind):
        if examined >= max_entries:
            capped = True
            break
        examined += 1
        if not value or len(value.encode("utf-8")) > 4096:
            rejected += 1
            continue
        try:
            # Sitemap loc elements must be absolute; Atom and RSS are
            # allowed document-relative links subject to the same admission.
            if kind.startswith("sitemap_"):
                split = urlsplit(value)
                if split.scheme not in ("http", "https") or not split.netloc:
                    raise ValueError("relative sitemap location")
                normalized = canonicalize_url(value)
            else:
                normalized = canonicalize_url(value, base=canonical)
            if (
                normalized == canonical
                or not policy.admits(normalized)
                or (kind == "sitemap_index"
                    and not urlsplit(normalized).path.lower().endswith(
                        (".xml", ".xml.gz")))
            ):
                raise ValueError("link not admissible under current scope")
        except (ValueError, UnicodeError):
            rejected += 1
            continue
        if normalized in seen:
            rejected += 1
            continue
        seen.add(normalized)
        if len(links) >= max_links:
            capped = True
            break
        links.append(normalized)
    return StructuredDiscovery(
        kind=kind, links=tuple(links), examined_entries=examined,
        discarded_entries=rejected, capped=capped,
    )

def extract_robots_sitemaps(
    robots_text: str, *, origin: str, policy: CrawlPolicy,
    max_sitemaps: int = 8,
) -> tuple[str, ...]:
    """Opt-in same-origin sitemap seeds from an already metered robots receipt.

    Robots Sitemap lines are untrusted hints, never a fetch grant. Future
    requests must pass the canonical worker robots, DNS and budget checks.
    """
    if (not isinstance(robots_text, str)
            or len(robots_text.encode("utf-8")) > 65536
            or not isinstance(policy, CrawlPolicy)
            or type(max_sitemaps) is not int
            or not 1 <= max_sitemaps <= 16):
        raise ValueError("invalid bounded robots sitemap extraction")
    parsed_origin = urlsplit(origin)
    if not parsed_origin.hostname or parsed_origin.scheme not in ("http", "https"):
        raise DiscoveryError("robots origin is not canonical")
    found: list[str] = []
    seen: set[str] = set()
    for line in robots_text.splitlines():
        if len(line) > 4096:
            continue
        key, sep, candidate = line.partition(":")
        if not sep or key.strip().casefold() != "sitemap":
            continue
        candidate = candidate.split("#", 1)[0].strip()
        try:
            url = canonicalize_url(candidate)
        except (ValueError, UnicodeError):
            continue
        p = urlsplit(url)
        if (p.hostname != parsed_origin.hostname
                or p.scheme != parsed_origin.scheme
                or not p.path.lower().endswith((".xml", ".xml.gz"))
                or not policy.admits(url)
                or url in seen):
            continue
        found.append(url)
        seen.add(url)
        if len(found) >= max_sitemaps:
            break
    return tuple(found)
