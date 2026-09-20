"""Compose cover, restrict, glue, stalk, Cech, nerve."""

from __future__ import annotations

from typing import Any

from skeleton.sheaf.cards import sheaf_card
from skeleton.sheaf.cech import cech_card
from skeleton.sheaf.cover import cover_card, opens, sites
from skeleton.sheaf.glue import glue_card
from skeleton.sheaf.law import COVER_N
from skeleton.sheaf.nerve import nerve_card
from skeleton.sheaf.restrict import exact_r_compose_r, restrict_card
from skeleton.sheaf.stalk import stalk_card


class SheafEngine:
    def snapshot(self) -> dict[str, Any]:
        names = opens()
        section = frozenset(sites())
        exact = exact_r_compose_r(section, (names[0], names[1], names[1]))
        cards = (
            cover_card(),
            restrict_card(exact),
            glue_card(),
            stalk_card(),
            cech_card(),
            nerve_card(),
        )
        ok = all(c["hit"] == 1 for c in cards)
        cech = cards[4]
        return sheaf_card(
            kind="sheaf",
            hit=1 if ok else 0,
            law="sheaf 1.1",
            extra={
                "cover_n": COVER_N,
                "H0": cech.get("H0"),
                "H1": cech.get("H1"),
                "exact": int(exact),
            },
        )
