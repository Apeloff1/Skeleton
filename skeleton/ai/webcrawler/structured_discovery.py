"""Bounded, policy-filtered XML sitemap and syndication feed discovery.

This is production link discovery for the canonical CrawlRun transport, not
an evidence/training source or an alternative network client. Sitemap and
feed contents are untrusted. Only exact committed, policy-admissible links
can enter the existing frontier, where the canonical worker *still* enforces
robots, DNS/socket egress, cumulative budgets and consent before fetching.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zlib

from .core import CrawlPolicy, canonicalize_url
from .discovery_relations import sitemap_language_alternate
from .api_discovery import API_DISCOVERY_TYPES, APIDiscoveryError, discover_api_pages
from .federated_activity import ACTIVITY_MEDIA_TYPES, ActivityDiscoveryError, discover_activity_page
from .opds_discovery import OPDS_TYPES, discover_opds
from .iiif_discovery import IIIF_TYPES, discover_iiif
from .oai_pmh_discovery import OAI_TYPES, discover_oai_pmh
from .archive_catalog_common import CatalogDiscoveryError, CatalogAsDocument


XML_MEDIA = frozenset({
    "application/xml", "text/xml", "application/rss+xml",
    "application/atom+xml",
    "application/opml+xml", "text/x-opml",
    "application/rdf+xml",
})
GZIP_MEDIA = frozenset({"application/gzip", "application/x-gzip"})
JSON_MEDIA = frozenset({"application/feed+json", "application/json"})
SUPPORTED_MEDIA = XML_MEDIA | GZIP_MEDIA | JSON_MEDIA | API_DISCOVERY_TYPES | ACTIVITY_MEDIA_TYPES | OPDS_TYPES | IIIF_TYPES | OAI_TYPES
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
ATOM_NS = "http://www.w3.org/2005/Atom"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RSS1_NS = "http://purl.org/rss/1.0/"
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


class UnsupportedDiscoveryRoot(DiscoveryError):
    """Well-formed non-sitemap/non-feed XML needs inert evidence parsing."""


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
                elif kind == "sitemap_urlset":
                    alt = sitemap_language_alternate(
                        namespace=child_ns, local_tag=child_local,
                        rel=child.attrib.get("rel"),
                        hreflang=child.attrib.get("hreflang"),
                        href=child.attrib.get("href"),
                    )
                    if alt is not None:
                        yield alt
    elif kind == "rss1_feed":
        # RSS 1.0 stores its items as RDF siblings of the channel node;
        # rdf:Seq resource links and arbitrary RDF predicates are not navigated.
        for item in root:
            if _local(item.tag) != (RSS1_NS, "item"):
                continue
            for child in item:
                if _local(child.tag) == (RSS1_NS, "link"):
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
    elif kind == "opml_outline":
        # The safe-tree node/depth budget has already been enforced globally.
        for entry in root.iter("outline"):
            if entry.get("type", "").lower() not in ("rss", "atom", "feed"):
                continue
            yield (entry.get("xmlUrl") or "").strip()
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



def _feed_page_links(root: ET.Element, kind: str):
    """Yield only document-level RFC 5005 next-page relations, never entries.

    Feed-level pagination is a discoverable URL hint, not a redirect, content
    provenance, verified knowledge or authority to request unseeded hosts.
    """
    if kind == "atom_feed":
        containers = (root,)
        allowed_tags = {(ATOM_NS, "link"), ("", "link")}
    elif kind == "rss_feed":
        containers = (
            node for node in root if _local(node.tag) == ("", "channel")
        )
        # RSS extension link is specifically the Atom namespace. Ordinary
        # RSS channel <link> is a homepage, not a pagination instruction.
        allowed_tags = {(ATOM_NS, "link")}
    else:
        return
    for container in containers:
        for child in container:
            if _local(child.tag) not in allowed_tags:
                continue
            if child.attrib.get("rel", "").strip().lower() not in ("next", "prev"):
                continue
            media = child.attrib.get("type", "").strip().lower()
            if media and media not in (
                "application/rss+xml", "application/atom+xml",
                "application/feed+json", "application/xml", "text/xml",
            ):
                continue
            yield child.attrib.get("href", "").strip()

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
    if media_type in (OPDS_TYPES | IIIF_TYPES | OAI_TYPES):
        try:
            if media_type in OPDS_TYPES:
                page = discover_opds(body, document_url=document_url,
                    policy=policy, max_links=min(max_links,64),
                    max_entries=min(max_entries,128))
            elif media_type in IIIF_TYPES:
                page = discover_iiif(body, document_url=document_url,
                    policy=policy, max_links=min(max_links,64),
                    max_entries=min(max_entries,128))
            else:
                page = discover_oai_pmh(body, document_url=document_url,
                    policy=policy, max_links=min(max_links,64),
                    max_entries=min(max_entries,128))
        except CatalogAsDocument as exc:
            raise UnsupportedDiscoveryRoot(str(exc)) from exc
        except CatalogDiscoveryError as exc:
            raise DiscoveryError(str(exc)) from exc
        return StructuredDiscovery(
            kind=page.kind, links=page.links,
            examined_entries=page.examined,
            discarded_entries=page.rejected, capped=page.capped,
        )
    if media_type in ACTIVITY_MEDIA_TYPES:
        try:
            page = discover_activity_page(
                body, media_type=media_type, document_url=document_url,
                policy=policy, max_links=min(max_links, 64),
                max_entries=min(max_entries, 128),
            )
        except ActivityDiscoveryError as exc:
            raise DiscoveryError(str(exc)) from exc
        return StructuredDiscovery(
            kind=page.kind, links=page.links,
            examined_entries=page.examined, discarded_entries=page.rejected,
            capped=page.capped,
        )
    if media_type in API_DISCOVERY_TYPES:
        try:
            page = discover_api_pages(
                body, media_type=media_type, document_url=document_url,
                policy=policy, max_links=min(max_links, 64),
                max_entries=max_entries,
            )
        except APIDiscoveryError as exc:
            raise DiscoveryError(str(exc)) from exc
        return StructuredDiscovery(
            kind=page.kind, links=page.links,
            examined_entries=page.examined,
            discarded_entries=page.rejected, capped=page.capped,
        )
    if media_type in JSON_MEDIA:
        return parse_json_feed(
            body, document_url=document_url, policy=policy,
            max_links=max_links, max_entries=max_entries,
        )
    document = _xml_bytes(body, media_type, document_url)
    root = _safe_tree(document)
    namespace, local = _local(root.tag)
    if local == "urlset" and namespace in ("", SITEMAP_NS):
        kind = "sitemap_urlset"
    elif local == "sitemapindex" and namespace in ("", SITEMAP_NS):
        kind = "sitemap_index"
    elif local == "rss" and namespace == "":
        kind = "rss_feed"
    elif local == "RDF" and namespace == RDF_NS and any(
        _local(child.tag) == (RSS1_NS, "channel") for child in root
    ):
        kind = "rss1_feed"
    elif local == "feed" and namespace in ("", ATOM_NS):
        kind = "atom_feed"
    elif local == "opml" and namespace == "":
        kind = "opml_outline"
    else:
        raise UnsupportedDiscoveryRoot("unsupported XML discovery root")
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
            if kind.startswith("sitemap_") or kind == "opml_outline":
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
    # RFC 5005 feed-page relations are a real, finite discovery input.
    # They are never accepted through an alternate network client: the
    # canonical worker subsequently applies robots and per-host admission.
    for value in _feed_page_links(root, kind):
        if examined >= max_entries:
            capped = True
            break
        examined += 1
        if not value or len(value.encode("utf-8")) > 4096:
            rejected += 1
            continue
        try:
            page = canonicalize_url(value, base=canonical)
            if page == canonical or not policy.admits(page) or page in seen:
                raise ValueError("feed pagination outside source scope")
        except (ValueError, UnicodeError):
            rejected += 1
            continue
        seen.add(page)
        if len(links) >= max_links:
            capped = True
            break
        links.append(page)
    return StructuredDiscovery(
        kind=kind, links=tuple(links), examined_entries=examined,
        discarded_entries=rejected, capped=capped,
    )


def parse_plaintext_sitemap(
    body: bytes, *, document_url: str, policy: CrawlPolicy,
    max_entries: int = 512, max_links: int = 128,
) -> StructuredDiscovery:
    """Discover bounded, absolute URLs from an explicit sitemap.txt file.

    Text sitemap entries never become source evidence, and must still pass
    the canonical worker's robots, DNS, consent, host and byte admission.
    """
    if (type(body) is not bytes or not body or len(body) > MAX_XML_BYTES
            or not isinstance(policy, CrawlPolicy)
            or type(max_entries) is not int or not 1 <= max_entries <= 1024
            or type(max_links) is not int or not 1 <= max_links <= MAX_DISCOVERY_LINKS):
        raise DiscoveryError("invalid text sitemap admission")
    canonical = canonicalize_url(document_url)
    if (canonical != document_url or not policy.admits(canonical)
            or urlsplit(canonical).path.lower().rsplit("/", 1)[-1] != "sitemap.txt"):
        raise DiscoveryError("text sitemap requires exact committed sitemap.txt URL")
    try:
        text = body.decode("utf-8-sig", errors="strict")
    except UnicodeError as exc:
        raise DiscoveryError("text sitemap must be strict UTF-8") from exc
    if "\x00" in text or any(
        ord(c) < 32 and c not in "\n\r\t" for c in text
    ):
        raise DiscoveryError("unsafe control bytes in text sitemap")
    links: list[str] = []
    seen: set[str] = set()
    inspected = rejected = 0
    capped = False
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if inspected >= max_entries:
            capped = True
            break
        inspected += 1
        value = raw.strip()
        if (len(value.encode("utf-8")) > 4096
                or any(c.isspace() for c in value)):
            rejected += 1
            continue
        try:
            p = urlsplit(value)
            if not p.scheme or not p.netloc:
                raise ValueError("relative sitemap item")
            url = canonicalize_url(value)
            if url == canonical or url in seen or not policy.admits(url):
                raise ValueError("unadmitted or duplicate text sitemap item")
        except (ValueError, UnicodeError):
            rejected += 1
            continue
        seen.add(url)
        if len(links) >= max_links:
            capped = True
            break
        links.append(url)
    return StructuredDiscovery(
        kind="plaintext_sitemap", links=tuple(links),
        examined_entries=inspected, discarded_entries=rejected, capped=capped,
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
                or not p.path.lower().endswith((".xml", ".xml.gz", "/sitemap.txt"))
                or not policy.admits(url)
                or url in seen):
            continue
        found.append(url)
        seen.add(url)
        if len(found) >= max_sitemaps:
            break
    return tuple(found)

def _no_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    record: dict[str, object] = {}
    for name, value in pairs:
        if name in record:
            raise DiscoveryError("duplicate JSON Feed object key")
        record[name] = value
    return record


def _reject_nonfinite_json(value: str) -> None:
    raise DiscoveryError("non-finite JSON Feed content is invalid")


def parse_json_feed(
    body: bytes, *, document_url: str, policy: CrawlPolicy,
    max_links: int = 128, max_entries: int = 512,
) -> StructuredDiscovery:
    """Discover canonical item links from JSON Feed 1/1.1, never item content.

    Also recognizes application/json when an explicit seed or queued URL
    produces a well-formed, versioned JSON Feed. Full JSON is parsed into a
    finite in-memory structure, but only bounded URLs are projected out.
    """
    if not isinstance(policy, CrawlPolicy):
        raise TypeError("canonical immutable crawl policy required")
    if (not isinstance(body, bytes) or len(body) == 0
            or len(body) > MAX_XML_BYTES):
        raise DiscoveryError("JSON Feed body exceeds the finite parse limit")
    if (type(max_links) is not int or not 1 <= max_links <= MAX_DISCOVERY_LINKS
            or type(max_entries) is not int or not 1 <= max_entries <= 1024):
        raise ValueError("invalid JSON Feed discovery bounds")
    canonical = canonicalize_url(document_url)
    if canonical != document_url or not policy.admits(canonical):
        raise DiscoveryError("JSON Feed URL is outside crawl source scope")
    try:
        decoded = body.decode("utf-8-sig", errors="strict")
        data = json.loads(
            decoded, object_pairs_hook=_no_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json,
        )
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise DiscoveryError("unparseable bounded JSON Feed") from exc
    if (
        not isinstance(data, dict)
        or data.get("version") not in (
            "https://jsonfeed.org/version/1",
            "https://jsonfeed.org/version/1.1",
        )
        or not isinstance(data.get("items"), list)
        or len(data["items"]) > 4096
    ):
        raise DiscoveryError("unsupported or oversized JSON Feed document")
    links = []
    seen = set()
    rejected = 0
    capped = False
    examined = 0
    for item in data["items"]:
        if examined >= max_entries:
            capped = True
            break
        examined += 1
        if not isinstance(item, dict):
            rejected += 1
            continue
        raw = item.get("url") or item.get("external_url")
        if not isinstance(raw, str) or not raw or len(raw.encode("utf-8")) > 4096:
            rejected += 1
            continue
        try:
            candidate = canonicalize_url(raw, base=canonical)
            if candidate == canonical or not policy.admits(candidate):
                raise ValueError("unadmitted JSON Feed item URL")
        except (ValueError, UnicodeError):
            rejected += 1
            continue
        if candidate in seen:
            rejected += 1
            continue
        seen.add(candidate)
        if len(links) >= max_links:
            capped = True
            break
        links.append(candidate)
    # JSON Feed 1/1.1 defines top-level next_url for paginated archives.
    # Content fields and arbitrary URL keys remain inert and cannot enqueue.
    if "next_url" in data:
        if examined >= max_entries:
            capped = True
        else:
            examined += 1
            raw_next = data["next_url"]
            if (not isinstance(raw_next, str) or not raw_next
                    or len(raw_next.encode("utf-8")) > 4096):
                rejected += 1
            else:
                try:
                    page = canonicalize_url(raw_next, base=canonical)
                    if page == canonical or not policy.admits(page) or page in seen:
                        raise ValueError("JSON Feed page is outside source scope")
                except (ValueError, UnicodeError):
                    rejected += 1
                else:
                    seen.add(page)
                    if len(links) >= max_links:
                        capped = True
                    else:
                        links.append(page)
    return StructuredDiscovery(
        kind="json_feed", links=tuple(links),
        examined_entries=examined,
        discarded_entries=rejected,
        capped=capped,
    )
