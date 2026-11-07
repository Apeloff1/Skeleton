"""Shared bounded navigation predicates, never network execution authority."""
from __future__ import annotations

import re

_LANGUAGE = re.compile(r"(?i)^(?:x-default|[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,4})$")
_HTML = frozenset({"", "text/html", "application/xhtml+xml"})
_FEEDS = frozenset({
    "application/rss+xml", "application/atom+xml",
    "application/feed+json", "application/xml", "text/xml",
})


def admissible_language(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 35 and bool(_LANGUAGE.fullmatch(value))


def navigational_relation(
    relations: object, *, media_type: str = "", hreflang: str = "",
) -> bool:
    """Recognize next/prev, typed feeds or explicitly language-bound alternate."""
    if (not isinstance(relations, (set, frozenset))
            or len(relations) > 16
            or not all(isinstance(x, str) and len(x) <= 64 for x in relations)
            or not isinstance(media_type, str) or len(media_type) > 128
            or not isinstance(hreflang, str)):
        return False
    rels = {x.casefold() for x in relations}
    mime = media_type.split(";", 1)[0].strip().casefold()
    if "next" in rels or "prev" in rels:
        return True
    return ("alternate" in rels and (
        mime in _FEEDS or (admissible_language(hreflang.strip()) and mime in _HTML)
    ))


def sitemap_language_alternate(
    *, namespace: str, local_tag: str, rel: object,
    hreflang: object, href: object,
) -> str | None:
    if namespace != "http://www.w3.org/1999/xhtml" or local_tag != "link":
        return None
    if not isinstance(rel, str) or rel.strip().casefold() != "alternate":
        return None
    if not admissible_language(hreflang):
        return None
    if not isinstance(href, str) or not 1 <= len(href) <= 4096:
        return None
    return href.strip() or None
