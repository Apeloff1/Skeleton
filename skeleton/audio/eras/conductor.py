"""Samples one organ per era. Does not import all 5120."""

from __future__ import annotations

import importlib
from typing import Any

from skeleton.audio.eras.caps import names
from skeleton.audio.eras.law import CAPABILITY_COUNT


class Conductor:
    def __init__(self) -> None:
        self.rows = names()
        if len(self.rows) != CAPABILITY_COUNT:
            raise RuntimeError("count")

    def pulse_eras(self) -> list[dict[str, Any]]:
        from skeleton.audio.eras.caps.c0001_pong_001 import EraPulse

        cards = []
        seen = set()
        for cid, era, module in self.rows:
            if era in seen:
                continue
            seen.add(era)
            organ = importlib.import_module(f"skeleton.audio.eras.caps.{module}").Organ()
            pulse = EraPulse(1, 1, 1, 8000, 1, 0.5, pointers=("ptr:era",), cool=True)
            card = organ.admit(pulse)
            if card.get("stored_prose", 0) != 0:
                raise RuntimeError("stored_prose")
            if organ.reverse() is None:
                raise RuntimeError("reverse")
            card["id"] = cid
            cards.append(card)
        return cards
