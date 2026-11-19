"""Conductor. Samples organs. Does not import all 2560 at once."""

from __future__ import annotations

import importlib
from typing import Any

from skeleton.cue.gb46.caps import names
from skeleton.cue.gb46.cards import cue_card
from skeleton.cue.gb46.law import CAPABILITY_COUNT, HEAT_DROP


class Conductor:
    def __init__(self) -> None:
        self.rows = names()
        if len(self.rows) != CAPABILITY_COUNT:
            raise RuntimeError("count")

    def load(self, module: str):
        return importlib.import_module(f"skeleton.cue.gb46.caps.{module}")

    def pulse_sample(self, step: int = 160) -> list[dict[str, Any]]:
        from skeleton.cue.gb46.caps.c0001_house_001 import CuePulse

        cards: list[dict[str, Any]] = []
        for cid, _family, module in self.rows[::step]:
            organ = self.load(module).Organ()
            pulse = CuePulse(
                generation=1,
                sequence=1,
                house="github",
                topic="forge",
                depth="r1",
                think="proof",
                obscure="mla",
                pointers=("ptr:axis", "ptr:house"),
                cool=True,
            )
            card = organ.family_gate(pulse)
            if card.get("stored_prose", 0) != 0:
                raise RuntimeError("stored_prose")
            card["id"] = cid
            cards.append(card)
            if organ.reverse() is None:
                raise RuntimeError("reverse")
        return cards

    def snapshot(self) -> dict[str, Any]:
        return cue_card("cue-batch", 1, "gb46-batch2560", {"count": len(self.rows), "heat_drop": HEAT_DROP})
