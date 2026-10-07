"""Twelve opens on a cycle. Each open covers two consecutive sites."""

from __future__ import annotations

from skeleton.sheaf.cards import sheaf_card
from skeleton.sheaf.law import COVER_N


def sites(n: int = COVER_N) -> list[str]:
    return ["s%02d" % i for i in range(n)]


def opens(n: int = COVER_N) -> list[str]:
    if n != COVER_N:
        raise ValueError("cover-n")
    return ["U%02d" % i for i in range(n)]


def support(open_id: str, n: int = COVER_N) -> frozenset[str]:
    i = int(open_id[1:])
    pts = sites(n)
    return frozenset((pts[i], pts[(i + 1) % n]))


def intersection(a: str, b: str, n: int = COVER_N) -> frozenset[str]:
    return support(a, n) & support(b, n)


def cover_card() -> dict:
    names = opens()
    return sheaf_card(
        kind="cover",
        hit=1 if len(names) == COVER_N else 0,
        law="cover 12 opens",
        extra={"n": len(names), "opens": names},
    )
