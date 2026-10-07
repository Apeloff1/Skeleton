"""Glue compatible local sections. Skip cite/feed cycles."""

from __future__ import annotations

from typing import Mapping

from skeleton.sheaf.cards import sheaf_card
from skeleton.sheaf.cover import intersection, opens
from skeleton.sheaf.law import SKIP_CYCLES


Section = frozenset[str]


def is_skip_cycle(tags: tuple[str, ...] | None) -> bool:
    if not tags:
        return False
    return any(t in SKIP_CYCLES for t in tags)


def compatible(locals_: Mapping[str, Section]) -> bool:
    names = list(locals_)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            cap = intersection(a, b)
            if not cap:
                continue
            sa = locals_[a] & cap
            sb = locals_[b] & cap
            if sa != sb:
                return False
    return True


def glue(locals_: Mapping[str, Section], tags: tuple[str, ...] | None = None) -> Section | None:
    if is_skip_cycle(tags):
        return None
    if not compatible(locals_):
        return None
    out: set[str] = set()
    for sec in locals_.values():
        out.update(sec)
    return frozenset(out)


def glue_card() -> dict:
    names = opens()
    locals_ = {name: frozenset(("p://root",)) for name in names}
    g = glue(locals_)
    skipped = glue(locals_, tags=("cite",))
    return sheaf_card(
        kind="glue",
        hit=1 if g is not None and skipped is None else 0,
        law="glue skip cite/feed",
        extra={"glued": int(g is not None), "skipped": int(skipped is None)},
    )
