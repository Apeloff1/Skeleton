"""Bounded query-facet and encoded-path crawl-trap veto.

This module counts already-known URL *shapes* in one current canonical run,
including both seen and pending frontier identities. It never generates a URL,
issues network IO, estimates remote safety, changes crawl policy, or creates
durable state; replaying an immutable snapshot yields the same decision.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from urllib.parse import unquote, urlsplit

_MAX_UNIVERSE = 1024
_MAX_SHAPES = 48
_MAX_QUERY_PAIRS = 32
_MAX_PERCENT_ROUNDS = 3
_ENCODED_DELIMITERS = re.compile(r"%(?:2e|2f|5c|3f|23|40|00)", re.I)
_CREDENTIALS = re.compile(
    r"(?i)(?:^|[-_])(?:access_token|refresh_token|id_token|api[-_]?key|"
    r"secret|password|passwd|authorization|credential|session|signature|jwt|"
    r"client_secret|private_key)(?:$|[-_])"
)
_OPAQUE_SEGMENT = re.compile(r"^[a-f0-9]{20,128}$", re.I)
_DIGIT_GROUP = re.compile(r"^[0-9]{3,18}$")


@dataclass(frozen=True)
class AntichainVerdict:
    allowed: bool
    reason: str
    structural_digest: str
    known_path_variants: int
    max_path_variants: int
    content_inspected: bool = False
    network_executed: bool = False
    policy_granted: bool = False


def _decoded(value: str, *, reject_delimiters: bool) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("invalid bounded URL component")
    current = value
    for _ in range(_MAX_PERCENT_ROUNDS):
        new = unquote(current, encoding="utf-8", errors="strict")
        if new == current:
            break
        if reject_delimiters and (
            "\\" in new or "\x00" in new or any(x in new for x in ("#", "?"))
        ):
            raise ValueError("encoded URL structural delimiter")
        current = new
    if reject_delimiters and _ENCODED_DELIMITERS.search(current):
        raise ValueError("multiply encoded URL delimiter")
    if "\x00" in current or "\r" in current or "\n" in current:
        raise ValueError("source URL includes control characters")
    return current


def _path_shape(url: str) -> tuple[str, str]:
    if not isinstance(url, str) or not 1 <= len(url) <= 4096:
        raise ValueError("invalid finite candidate URL")
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ValueError("invalid canonical URL origin")
    # The origin must not change under untrusted path decoding.
    pieces = []
    for segment in parsed.path.split("/"):
        value = _decoded(segment, reject_delimiters=True).casefold()
        if value in (".", "..") or "/" in value or "\\" in value:
            raise ValueError("path interpretation changes under decoding")
        if _DIGIT_GROUP.fullmatch(value) or _OPAQUE_SEGMENT.fullmatch(value):
            value = "{id}"
        pieces.append(value[:128])
    path = parsed.scheme + "://" + parsed.netloc.casefold() + "/" + "/".join(pieces)
    return path[:2048], parsed.query


def _query_keys(query: str) -> tuple[str, ...]:
    if len(query) > 4096:
        raise ValueError("oversized source query")
    keys = []
    for pair in query.split("&"):
        if not pair:
            continue
        if len(keys) >= _MAX_QUERY_PAIRS:
            raise ValueError("unbounded URL query facets")
        raw = pair.partition("=")[0]
        key = _decoded(raw, reject_delimiters=False).casefold()
        if (not key or len(key) > 128 or _CREDENTIALS.search(key)
                or any(ord(c) < 33 for c in key)):
            raise ValueError("credential-bearing or malformed query key")
        keys.append(key)
    return tuple(sorted(set(keys)))


def vet_url_antichain(
    candidate: str, *,
    seen: list[str] | tuple[str, ...],
    frontier: list[str] | tuple[str, ...],
    max_path_variants: int = _MAX_SHAPES,
) -> AntichainVerdict:
    if (not isinstance(seen, (list, tuple))
            or not isinstance(frontier, (list, tuple))
            or len(seen) + len(frontier) > _MAX_UNIVERSE
            or type(max_path_variants) is not int
            or not 1 <= max_path_variants <= _MAX_SHAPES):
        raise ValueError("antichain source snapshot or limits invalid")
    try:
        path, query = _path_shape(candidate)
        keys = _query_keys(query)
    except (ValueError, UnicodeError):
        return AntichainVerdict(False, "untrusted_encoded_url_structure",
                                hashlib.sha256(str(candidate).encode("utf-8")[:4096]).hexdigest(),
                                0, max_path_variants)
    shape = path + "?" + "|".join(keys)
    identity = hashlib.sha256(shape.encode("utf-8")).hexdigest()
    variants = set()
    for url in (*seen, *frontier):
        try:
            other_path, other_query = _path_shape(url)
            if other_path == path and other_query:
                variants.add((_query_keys(other_query), other_query))
        except (ValueError, UnicodeError) as exc:
            # This is already persisted canonical state, not a new external
            # candidate. A tampered snapshot must never be silently skipped.
            raise ValueError("malformed historical frontier identity") from exc
    if query and len(variants) >= max_path_variants and candidate not in (*seen, *frontier):
        return AntichainVerdict(False, "path_facet_variant_budget_exhausted",
                                identity, len(variants), max_path_variants)
    return AntichainVerdict(True, "bounded_facet_variant",
                            identity, len(variants), max_path_variants)
