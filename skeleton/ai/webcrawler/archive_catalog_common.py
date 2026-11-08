"""Shared same-origin, non-executing discovery rules for research catalogs.

Never dereferences catalog-linked files, URLs, credentials or metadata.
Only an owner-admitted source can nominate a finite link, and the canonical
CrawlRun must subsequently reauthorize each network request.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

# core -> document_formats -> iiif_manifest_documents -> this module.
# Never import core during module initialization: it is not yet complete.
if TYPE_CHECKING:
    from .core import CrawlPolicy

MAX_BODY = 1_048_576
MAX_ENTRIES = 256
MAX_LINKS = 64


class CatalogDiscoveryError(ValueError):
    """Unrecognized or excessive source-side catalog evidence."""


class CatalogAsDocument(CatalogDiscoveryError):
    """A valid catalog member must be retained as a normal source document."""


@dataclass(frozen=True)
class CatalogLinks:
    kind: str
    links: tuple[str, ...]
    examined: int
    rejected: int
    capped: bool
    links_only: bool = True
    authority_granted: bool = False
    network_executed: bool = False


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for k, v in pairs:
        if k in result:
            raise CatalogDiscoveryError("duplicate JSON catalog property")
        result[k] = v
    return result


def _constant(_value: str) -> None:
    raise CatalogDiscoveryError("nonfinite catalog number")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise CatalogDiscoveryError("nonfinite floating-point catalog number")
    return result


def load_json_catalog(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BODY:
        raise CatalogDiscoveryError("catalog byte limit exceeded")
    if b"\x00" in raw or raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise CatalogDiscoveryError("unsupported catalog byte encoding")
    try:
        data = json.loads(
            raw.decode("utf-8-sig", errors="strict"),
            object_pairs_hook=_object, parse_constant=_constant,
            parse_float=_finite_float,
        )
    except (UnicodeError, RecursionError, ValueError) as exc:
        raise CatalogDiscoveryError("invalid finite JSON catalog") from exc
    if not isinstance(data, dict):
        raise CatalogDiscoveryError("catalog root must be a JSON object")
    return data


def catalog_source(url: str, policy: CrawlPolicy) -> str:
    # Defer the runtime class import until core has finished initializing.
    from .core import CrawlPolicy

    if not isinstance(policy, CrawlPolicy) or not isinstance(url, str):
        raise CatalogDiscoveryError("missing immutable catalog policy")
    from .core import canonicalize_url

    try:
        canonical = canonicalize_url(url)
    except (ValueError, UnicodeError) as exc:
        raise CatalogDiscoveryError("malformed catalog source") from exc
    if canonical != url or not policy.admits(canonical):
        raise CatalogDiscoveryError("catalog source escaped admitted scope")
    return canonical


def candidate_link(
    value: object, *, source: str, policy: CrawlPolicy,
) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 4096:
        return None
    if any(c.isspace() for c in value):
        return None
    from .core import canonicalize_url

    try:
        url = canonicalize_url(value, base=source)
        left, right = urlsplit(source), urlsplit(url)
        if (left.scheme != right.scheme or left.netloc != right.netloc
                or url == source or not policy.admits(url)
                or right.username is not None or right.password is not None):
            return None
    except (ValueError, UnicodeError):
        return None
    return url


class LinkCollector:
    """Finite deduplication and transparent truncation for catalog links."""

    def __init__(self, *, source: str, policy: CrawlPolicy, max_links: int):
        if type(max_links) is not int or not 1 <= max_links <= MAX_LINKS:
            raise CatalogDiscoveryError("invalid catalog link cap")
        self.source = source
        self.policy = policy
        self.limit = max_links
        self.links: list[str] = []
        self.seen: set[str] = set()
        self.examined = 0
        self.rejected = 0
        self.capped = False

    def add(self, value: object) -> None:
        self.examined += 1
        url = candidate_link(value, source=self.source, policy=self.policy)
        if url is None or url in self.seen:
            self.rejected += 1
            return
        self.seen.add(url)
        if len(self.links) >= self.limit:
            self.capped = True
            return
        self.links.append(url)

    def report(self, kind: str) -> CatalogLinks:
        return CatalogLinks(
            kind, tuple(self.links), self.examined,
            self.rejected, self.capped,
        )
