"""Safe bounded HTTP Link-header next-page and feed discovery.

No header can request arbitrary cross-origin transport, elevate source rights,
mark content trusted, or bypass the canonical CrawlRun robots/budget/DNS owner.
Only rel=next and explicitly typed feed alternates are candidates; values
are canonicalized and narrowed under the immutable allowed_hosts policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .core import CrawlPolicy, canonicalize_url
from .discovery_relations import navigational_relation


_FEEDS = frozenset({
    "application/rss+xml", "application/atom+xml",
    "application/feed+json", "application/xml", "text/xml",
})
_PARAM = re.compile(
    r"^\s*([a-z0-9][a-z0-9-]{0,63})\s*=\s*(?:\"([^\"]{0,256})\"|([^\s;]{1,256}))\s*$",
    re.I,
)
_REL = re.compile(r"^[a-z][a-z0-9-]{0,63}$", re.I)


@dataclass(frozen=True)
class HeaderDiscovery:
    links: tuple[str, ...]
    relations_read: int
    rejected: int
    truncated: bool
    link_header_did_not_grant_network_authority: bool = True


def _segments(header: str):
    """Comma split only outside quotes and URI angle brackets, fail closed."""
    quoted = False
    angle = False
    escaped = False
    start = 0
    for i, char in enumerate(header):
        if escaped:
            escaped = False
        elif char == "\\" and quoted:
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == "<" and not quoted:
            if angle:
                raise ValueError("nested HTTP Link URI brackets")
            angle = True
        elif char == ">" and not quoted:
            if not angle:
                raise ValueError("unmatched HTTP Link closing bracket")
            angle = False
        elif char == "," and not quoted and not angle:
            yield header[start:i].strip()
            start = i + 1
    if quoted or angle or escaped:
        raise ValueError("unterminated HTTP Link header syntax")
    yield header[start:].strip()


def parse_link_headers(
    headers: Mapping[str, str], *, base_url: str, policy: CrawlPolicy,
    max_links: int = 16, max_relations: int = 48,
) -> HeaderDiscovery:
    if (not isinstance(headers, Mapping) or not isinstance(policy, CrawlPolicy)
            or type(max_links) is not int or not 1 <= max_links <= 64
            or type(max_relations) is not int or not 1 <= max_relations <= 128):
        raise ValueError("invalid Link-header inspection contract")
    canonical = canonicalize_url(base_url)
    if not policy.admits(canonical):
        raise ValueError("Link-header source escaped crawler scope")
    raw = next(
        (value for key, value in headers.items()
         if isinstance(key, str) and key.lower() == "link"), "",
    )
    if not raw:
        return HeaderDiscovery((), 0, 0, False)
    if (not isinstance(raw, str) or len(raw) > 8192
            or any(ord(ch) < 32 and ch != "\t" for ch in raw)):
        raise ValueError("Link-header text exceeds bounded safe syntax")
    links = []
    seen = set()
    rejected = inspected = 0
    truncated = False
    for segment in _segments(raw):
        if inspected >= max_relations:
            truncated = True
            break
        inspected += 1
        match = re.fullmatch(r"\s*<([^<>]{1,4096})>\s*(?:;(.*))?", segment, re.S)
        if not match:
            rejected += 1
            continue
        url, raw_params = match.group(1), match.group(2) or ""
        params = {}
        invalid = False
        for parameter in raw_params.split(";"):
            if not parameter.strip():
                continue
            token = _PARAM.fullmatch(parameter)
            if token is None:
                invalid = True
                break
            name = token.group(1).lower()
            if name in params:
                invalid = True
                break
            params[name] = token.group(2) if token.group(2) is not None else token.group(3)
        if invalid:
            rejected += 1
            continue
        relation = params.get("rel", "")
        rels = {token.lower() for token in relation.split() if _REL.fullmatch(token)}
        mime = params.get("type", "").split(";", 1)[0].lower().strip()
        if not navigational_relation(
            rels, media_type=mime, hreflang=params.get("hreflang", ""),
        ):
            rejected += 1
            continue
        try:
            dest = canonicalize_url(url, base=canonical)
            if not policy.admits(dest) or dest == canonical:
                raise ValueError("Link header URL is outside original scope")
        except (ValueError, UnicodeError):
            rejected += 1
            continue
        if dest in seen:
            rejected += 1
            continue
        seen.add(dest)
        if len(links) >= max_links:
            truncated = True
            break
        links.append(dest)
    return HeaderDiscovery(tuple(links), inspected, rejected, truncated)
