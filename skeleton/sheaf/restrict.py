"""Restriction r. Exactness: r composed r equals the direct restriction."""

from __future__ import annotations

from skeleton.sheaf.cards import sheaf_card
from skeleton.sheaf.cover import support


Section = frozenset[str]


def restrict_to_support(section: Section, open_id: str) -> Section:
    return frozenset(x for x in section if x in support(open_id))


def compose(section: Section, u: str, v: str, w: str) -> tuple[Section, Section]:
    s_uv = restrict_to_support(section, u)
    s_vw = frozenset(x for x in s_uv if x in support(v))
    left = frozenset(x for x in s_vw if x in support(w))
    right = frozenset(x for x in s_uv if x in support(w))
    return left, right


def exact_r_compose_r(section: Section, chain: tuple[str, str, str]) -> bool:
    left, right = compose(section, *chain)
    return left == right


def restrict_card(ok: bool) -> dict:
    return sheaf_card(
        kind="restrict",
        hit=1 if ok else 0,
        law="exact r composed r",
        extra={"exact": int(ok)},
    )
