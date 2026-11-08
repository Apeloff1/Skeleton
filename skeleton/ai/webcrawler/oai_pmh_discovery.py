"""Open Archives Initiative OAI-PMH ListIdentifiers cursor pagination.

This accepts only a previously authorized public ListIdentifiers URL and
a finite syntactically constrained server resumption token. Identifiers and
record metadata are never projected into new URLs, and an opaque token is
not a training grant, credential, subscription or validation of record truth.

All nominated URLs return to the original CrawlRun frontier, subject to
robots, owner/tenant consent, immutable host scope, DNS/socket, rate limits
and exact request/byte reservations before any additional GET.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .archive_catalog_common import (
    MAX_ENTRIES, CatalogDiscoveryError, CatalogLinks, LinkCollector,
    catalog_source,
)
from .core import CrawlPolicy

OAI_TYPES = frozenset({"application/vnd.openarchives.oai-pmh+xml"})
_NS = "http://www.openarchives.org/OAI/2.0/"
_FORBIDDEN = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.I)
_TOKEN = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
_PREFIX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _tag(name: str) -> str:
    return "{" + _NS + "}" + name


def _bounded_tree(body: bytes) -> ET.Element:
    if type(body) is not bytes or not 1 <= len(body) <= 1_048_576:
        raise CatalogDiscoveryError("OAI-PMH XML byte capacity exceeded")
    if (b"\x00" in body or _FORBIDDEN.search(body)
            or body.startswith((b"\xff\xfe", b"\xfe\xff"))):
        raise CatalogDiscoveryError("unsafe OAI-PMH XML encoding or entity")
    try:
        body.decode("utf-8-sig", errors="strict")
        root = ET.fromstring(body)
    except (UnicodeError, ET.ParseError, RecursionError) as exc:
        raise CatalogDiscoveryError("invalid OAI-PMH XML") from exc
    if root.tag != _tag("OAI-PMH"):
        raise CatalogDiscoveryError("OAI-PMH namespace root absent")
    stack = [(root, 1)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > 4096 or depth > 32 or len(node.attrib) > 32:
            raise CatalogDiscoveryError("OAI-PMH element/depth cap exceeded")
        stack.extend((child, depth+1) for child in node)
    return root


def _request_source(url: str, policy: CrawlPolicy) -> tuple[str, str]:
    canonical = catalog_source(url, policy)
    parsed = urlsplit(canonical)
    try:
        values = parse_qsl(
            parsed.query, keep_blank_values=True,
            strict_parsing=True, max_num_fields=4,
        )
    except ValueError as exc:
        raise CatalogDiscoveryError("OAI-PMH source query invalid") from exc
    if len(values) != len({key for key,_ in values}):
        raise CatalogDiscoveryError("duplicate OAI-PMH source query key")
    params = dict(values)
    if params.get("verb") != "ListIdentifiers":
        raise CatalogDiscoveryError("only explicit ListIdentifiers is navigable")
    names = set(params)
    if names == {"verb", "metadataPrefix"}:
        prefix = params["metadataPrefix"]
        if not _PREFIX.fullmatch(prefix):
            raise CatalogDiscoveryError("unbounded OAI-PMH metadata prefix")
    elif names == {"verb", "resumptionToken"}:
        prefix = params["resumptionToken"]
        if not _TOKEN.fullmatch(prefix):
            raise CatalogDiscoveryError("unbounded OAI-PMH incoming cursor")
    else:
        raise CatalogDiscoveryError("unsupported OAI-PMH query parameter set")
    return canonical, urlunsplit((parsed.scheme,parsed.netloc,parsed.path,"",""))


def discover_oai_pmh(
    body: bytes, *, document_url: str, policy: CrawlPolicy,
    max_links: int = 4, max_entries: int = 128,
) -> CatalogLinks:
    if type(max_entries) is not int or not 1 <= max_entries <= MAX_ENTRIES:
        raise CatalogDiscoveryError("OAI-PMH record-count admission invalid")
    source, endpoint = _request_source(document_url, policy)
    root = _bounded_tree(body)
    if root.find(_tag("error")) is not None:
        raise CatalogDiscoveryError("OAI-PMH response reported protocol error")
    listing = root.find(_tag("ListIdentifiers"))
    if listing is None:
        raise CatalogDiscoveryError("OAI-PMH ListIdentifiers response missing")
    if sum(child.tag == _tag("ListIdentifiers") for child in root) != 1:
        raise CatalogDiscoveryError("multiple OAI-PMH identifier sections")
    headers = listing.findall(_tag("header"))
    if len(headers) > max_entries:
        raise CatalogDiscoveryError("OAI-PMH record headers exceed bound")
    for record in headers:
        identifier = record.find(_tag("identifier"))
        if (identifier is None or not identifier.text
                or len(identifier.text) > 4096):
            raise CatalogDiscoveryError("OAI-PMH identifier is invalid")
        # Identifiers may be arbitrary strings, e-mail addresses, URLs, etc.
        # They are intentionally counted, not retained as links or page text.
    rows = listing.findall(_tag("resumptionToken"))
    if len(rows) > 1:
        raise CatalogDiscoveryError("multiple OAI-PMH cursors")
    out = LinkCollector(source=source, policy=policy, max_links=max_links)
    if rows:
        if len(rows[0]) or len(rows[0].attrib) > 8:
            raise CatalogDiscoveryError("invalid OAI-PMH resumption token structure")
        token = (rows[0].text or "").strip()
        if token:
            if _TOKEN.fullmatch(token) is None:
                raise CatalogDiscoveryError("opaque OAI-PMH token unsafe for URL custody")
            next_url = endpoint + "?" + urlencode({
                "verb":"ListIdentifiers", "resumptionToken":token,
            })
            out.add(next_url)
    return out.report("oai_pmh_listidentifiers")
