"""Explicit opt-in temporal Memento Link observations, same-origin only.

Source-supplied Link headers and memento-datetime fields are untrusted.
Only well-formed HTTP Link rel=memento with a bounded past UTC HTTP date
can become a frontier hint; never derive authority from timegate/timemap,
original, external archive hosts, authentication headers or cookies.

The canonical worker still performs the entire request, DNS, robots, consent
and budget admission. This parser neither fetches nor promotes history truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
import math
import re
from typing import Mapping
from urllib.parse import urlsplit

from .core import CrawlPolicy, canonicalize_url
from .link_header_discovery import _segments, _PARAM

_MAX_HEADER_BYTES = 8192
_MAX_RELATIONS = 64
_MAX_LINKS = 12
_RELATION = re.compile(r"^[a-z][a-z0-9-]{0,63}$", re.I)


class MementoDiscoveryError(ValueError):
    """Malformed temporal link metadata or bounded source authority."""


@dataclass(frozen=True)
class MementoDiscovery:
    links: tuple[str, ...]
    checked_relations: int
    rejected: int
    capped: bool
    historical_urls_not_verified: bool = True
    network_requests_started: bool = False
    grants_network_authority: bool = False
    consent_expiry_extended: bool = False


def _datetime(value: object, now: float) -> float | None:
    if not isinstance(value, str) or not 8 <= len(value) <= 128:
        return None
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            return None
        stamp = date.astimezone(timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError, IndexError):
        return None
    if not math.isfinite(stamp) or not 0 <= stamp <= now+300:
        return None
    return round(stamp, 3)


def discover_mementos(
    headers: Mapping[str, str], *,
    base_url: str, policy: CrawlPolicy,
    observed_at: float, max_links: int = _MAX_LINKS,
) -> MementoDiscovery:
    if (not isinstance(headers, Mapping) or not isinstance(policy, CrawlPolicy)
            or type(observed_at) not in (float, int)
            or not math.isfinite(observed_at) or not 0 <= observed_at <= 4102444800
            or type(max_links) is not int or not 1 <= max_links <= _MAX_LINKS):
        raise MementoDiscoveryError("invalid temporal discovery authority or bounds")
    source = canonicalize_url(base_url)
    if source != base_url or not policy.admits(source):
        raise MementoDiscoveryError("temporal source outside immutable host policy")
    found = [value for key, value in headers.items()
             if isinstance(key, str) and key.casefold() == "link"]
    if not found:
        return MementoDiscovery((), 0, 0, False)
    if len(found) != 1 or not isinstance(found[0], str):
        raise MementoDiscoveryError("duplicate or malformed Link header")
    raw = found[0]
    if len(raw) > _MAX_HEADER_BYTES or any(ord(c) < 32 and c != "\t" for c in raw):
        raise MementoDiscoveryError("temporal Link header too large or has controls")
    checked = rejected = 0
    links: list[str] = []
    seen: set[str] = set()
    capped = False
    origin = urlsplit(source)
    try:
        segments = tuple(_segments(raw))
    except ValueError as exc:
        raise MementoDiscoveryError("unbalanced Link header") from exc
    if len(segments) > _MAX_RELATIONS:
        raise MementoDiscoveryError("temporal relation count exceeded")
    for segment in segments:
        checked += 1
        match = re.fullmatch(r"\s*<([^<>]{1,4096})>\s*(?:;(.*))?", segment, re.S)
        if match is None:
            rejected += 1
            continue
        link, fields = match.group(1), match.group(2) or ""
        params: dict[str, str] = {}
        invalid = False
        for raw_field in fields.split(";"):
            if not raw_field.strip():
                continue
            record = _PARAM.fullmatch(raw_field)
            if record is None:
                invalid = True
                break
            name = record.group(1).casefold()
            if name in params:
                invalid = True
                break
            params[name] = record.group(2) if record.group(2) is not None else record.group(3)
        if invalid:
            rejected += 1
            continue
        rels = set(params.get("rel", "").casefold().split())
        if "memento" not in rels:
            continue
        if any(not _RELATION.fullmatch(x) for x in rels):
            rejected += 1
            continue
        if _datetime(params.get("datetime"), observed_at) is None:
            rejected += 1
            continue
        try:
            dest = canonicalize_url(link, base=source)
            target = urlsplit(dest)
            if (target.scheme != origin.scheme or target.netloc != origin.netloc
                    or dest == source or not policy.admits(dest)
                    or target.username or target.password):
                raise ValueError("temporal candidate has different origin")
        except (ValueError, UnicodeError):
            rejected += 1
            continue
        if dest in seen:
            rejected += 1
            continue
        seen.add(dest)
        if len(links) >= max_links:
            capped = True
            break
        links.append(dest)
    return MementoDiscovery(tuple(links), checked, rejected, capped)
