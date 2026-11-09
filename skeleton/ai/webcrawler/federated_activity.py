"""Public ActivityStreams 2 collection navigation for a bounded HTTP crawler.

Only explicit public Collection/OrderedCollection page links and already
public Article/Note/Document item links can be nominated. Every URL must
remain same-origin and CrawlPolicy-admissible; actor, inbox, outbox, followers,
webfinger and remote JSON-LD contexts never grant authority or extra fetches.
This module performs no network, publication, authentication, or actor I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.parse import urlsplit

from .core import CrawlPolicy, canonicalize_url

ACTIVITY_MEDIA_TYPES = frozenset({
    "application/activity+json",
    "application/vnd.activitystreams+json",
})
MAX_ACTIVITY_BYTES = 1_048_576
MAX_ACTIVITY_ITEMS = 128
MAX_ACTIVITY_LINKS = 64
_PUBLIC = "https://www.w3.org/ns/activitystreams#Public"
_CONTEXT = "https://www.w3.org/ns/activitystreams"
_COLLECTIONS = frozenset({
    "Collection", "OrderedCollection", "CollectionPage", "OrderedCollectionPage",
})
_PAGES = frozenset({"CollectionPage", "OrderedCollectionPage"})
_PUBLIC_TYPES = frozenset({"Article", "Document", "Note"})
_RESERVED_ROUTES = frozenset({
    "inbox", "outbox", "followers", "following", "sharedinbox",
    "liked", "likes", "blocks", "block", "private",
})


class ActivityDiscoveryError(ValueError):
    """Unapproved ActivityStreams graph root or malformed bounded document."""


@dataclass(frozen=True)
class ActivityPage:
    kind: str
    links: tuple[str, ...]
    examined: int
    rejected: int
    capped: bool
    public_items: int
    same_origin_only: bool = True
    executes_activity: bool = False
    network_executed: bool = False
    grants_authority: bool = False


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise ActivityDiscoveryError("duplicate ActivityStreams JSON field")
        obj[key] = value
    return obj


def _nonfinite(_value: str) -> None:
    raise ActivityDiscoveryError("nonfinite ActivityStreams value")


def _validate_context(value: object) -> None:
    if isinstance(value, str):
        contexts = [value]
    elif isinstance(value, list) and len(value) <= 4:
        contexts = value
    else:
        raise ActivityDiscoveryError("ActivityStreams context format unsupported")
    # No remote context resolution, even when the link is embedded in source.
    if not contexts or any(not isinstance(x, str) or x != _CONTEXT for x in contexts):
        raise ActivityDiscoveryError("ActivityStreams external context denied")


def _link(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Only explicit Link objects; no JSON-LD relationship traversal.
        if value.get("type") != "Link":
            return None
        raw = value.get("href")
        if isinstance(raw, str):
            return raw
    return None


def _public_item(value: object) -> str | None:
    if (not isinstance(value, dict) or not isinstance(value.get("type"), str)
            or value["type"] not in _PUBLIC_TYPES):
        return None
    if any(field in value for field in ("bto", "bcc", "inReplyTo", "replies")):
        return None
    audience = value.get("to")
    if isinstance(audience, str):
        audience = [audience]
    if not isinstance(audience, list) or len(audience) > 32:
        return None
    if _PUBLIC not in audience:
        return None
    raw = value.get("url", value.get("id"))
    if isinstance(raw, dict):
        raw = _link(raw)
    return raw if isinstance(raw, str) else None


def _safe_url(
    value: object, *, document_url: str,
    policy: CrawlPolicy,
) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 4096:
        return None
    if any(c.isspace() for c in value):
        return None
    try:
        candidate = canonicalize_url(value, base=document_url)
        a, b = urlsplit(document_url), urlsplit(candidate)
        if (a.scheme != b.scheme or a.netloc != b.netloc
                or candidate == document_url or not policy.admits(candidate)
                or b.username or b.password):
            return None
        # Endpoint labels are not proof of privacy, but disabling implicit
        # ActivityPub inbox/outbox routes avoids obvious write targets.
        name = b.path.rstrip("/").rsplit("/", 1)[-1].casefold()
        if name in _RESERVED_ROUTES:
            return None
        return candidate
    except (ValueError, UnicodeError):
        return None


def discover_activity_page(
    body: bytes, *, media_type: str,
    document_url: str, policy: CrawlPolicy,
    max_links: int = 32, max_entries: int = MAX_ACTIVITY_ITEMS,
) -> ActivityPage:
    if (media_type not in ACTIVITY_MEDIA_TYPES
            or not isinstance(policy, CrawlPolicy)
            or type(body) is not bytes or not 1 <= len(body) <= MAX_ACTIVITY_BYTES
            or type(max_links) is not int or not 1 <= max_links <= MAX_ACTIVITY_LINKS
            or type(max_entries) is not int or not 1 <= max_entries <= MAX_ACTIVITY_ITEMS):
        raise ActivityDiscoveryError("invalid bounded ActivityStreams admission")
    if canonicalize_url(document_url) != document_url or not policy.admits(document_url):
        raise ActivityDiscoveryError("ActivityStreams origin outside crawl scope")
    try:
        raw = body.decode("utf-8-sig", "strict")
        document = json.loads(
            raw, object_pairs_hook=_unique, parse_constant=_nonfinite,
        )
    except (UnicodeError, RecursionError, ValueError) as exc:
        raise ActivityDiscoveryError("invalid ActivityStreams JSON document") from exc
    if not isinstance(document, dict):
        raise ActivityDiscoveryError("ActivityStreams root must be an object")
    _validate_context(document.get("@context"))
    kind = document.get("type")
    if not isinstance(kind, str) or kind not in _COLLECTIONS:
        raise ActivityDiscoveryError("non-public ActivityStreams collection root")
    items = document.get("orderedItems", document.get("items", []))
    if not isinstance(items, list) or len(items) > max_entries:
        raise ActivityDiscoveryError("ActivityStreams item capacity exceeded")
    links: list[str] = []
    seen: set[str] = set()
    rejected = examined = public_items = 0
    capped = False
    def add(candidate: object) -> None:
        nonlocal examined, rejected, capped
        examined += 1
        destination = _safe_url(candidate, document_url=document_url, policy=policy)
        if destination is None or destination in seen:
            rejected += 1
            return
        seen.add(destination)
        if len(links) >= max_links:
            capped = True
            return
        links.append(destination)
    # Distinguish collection roots from page records. "first" may nominate
    # an in-scope page, but not perform a WebSub subscription.
    if kind in _PAGES:
        for key in ("next", "prev"):
            value = document.get(key)
            if value is not None:
                add(_link(value))
    else:
        value = document.get("first")
        if value is not None:
            add(_link(value))
        for key in ("next", "prev"):
            value = document.get(key)
            if value is not None:
                add(_link(value))
    for item in items:
        if not isinstance(item, dict):
            rejected += 1
            continue
        candidate = _public_item(item)
        if candidate is not None:
            public_items += 1
            add(candidate)
        else:
            rejected += 1
    return ActivityPage(
        kind="activitystreams_"+kind.casefold(),
        links=tuple(links), examined=examined, rejected=rejected,
        capped=capped, public_items=public_items,
    )
