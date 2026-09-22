"""Stalk at a site = germs of sections on opens that contain the site."""

from __future__ import annotations

from skeleton.sheaf.cards import sheaf_card
from skeleton.sheaf.cover import opens, support
from skeleton.sheaf.law import COVER_N


def opens_at(site: str) -> list[str]:
    return [u for u in opens() if site in support(u)]


def stalk(site: str, sections: dict[str, frozenset[str]]) -> frozenset[str]:
    germ: set[str] = set()
    for u in opens_at(site):
        germ.update(x for x in sections.get(u, frozenset()) if x)
    return frozenset(germ)


def stalk_card() -> dict:
    site = "s00"
    nbh = opens_at(site)
    return sheaf_card(
        kind="stalk",
        hit=1 if len(nbh) >= 1 else 0,
        law="stalk",
        extra={"site": site, "opens": nbh, "n": COVER_N},
    )
