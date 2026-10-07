"""Compose 12 regions, warp once, bind mouth/body."""

from __future__ import annotations

from typing import Any

from skeleton.hoag.cards import hoag_card
from skeleton.hoag.law import REGION_N
from skeleton.hoag.plane import Warp, bind_mouth_body, region_cards


class HoagEngine:
    def snapshot(self) -> dict[str, Any]:
        cards = region_cards()
        w = Warp()
        first = w.extract("mouth-note")
        second = w.extract("again")
        bind = bind_mouth_body("say", "do")
        ok = (
            len(cards) == REGION_N
            and first["skipped"] == 0
            and second["skipped"] == 1
            and bind["bound"] == 1
        )
        return hoag_card(
            kind="hoag",
            hit=1 if ok else 0,
            law="hoag 1.0",
            extra={"regions": len(cards), "skipped": second["skipped"], "bound": bind["bound"]},
        )
