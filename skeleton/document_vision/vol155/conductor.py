"""Conductor for 640 document-vision organs."""

from __future__ import annotations

from typing import Any

from skeleton.document_vision.vol155.caps import ORGANS
from skeleton.document_vision.vol155.cards import vision_card
from skeleton.document_vision.vol155.law import CAPABILITY_COUNT, HEAT_DROP

DIGEST = "cd" * 32


class Conductor:
    def __init__(self) -> None:
        self.organs = [(cid, name, cls()) for cid, name, cls in ORGANS]
        if len(self.organs) != CAPABILITY_COUNT:
            raise RuntimeError("count")

    def pulse_all(self, generation: int, sequence: int, agree: bool = True) -> list[dict[str, Any]]:
        from skeleton.document_vision.vol155.caps.c001_page_01 import SpanPulse

        cards: list[dict[str, Any]] = []
        for cid, _name, organ in self.organs:
            pulse = SpanPulse(
                generation=generation,
                sequence=sequence,
                document_id="DOC-VOL155",
                page=1,
                x=8,
                y=8,
                width=120,
                height=24,
                page_width=800,
                page_height=1100,
                render_digest=DIGEST,
                confidence=0.82,
                pointers=("ptr:span", "ptr:region"),
                cool=True,
                agree=agree,
            )
            try:
                card = organ.family_gate(pulse)
            except ValueError as exc:
                card = vision_card("vision-reject", 0, str(exc), {"id": cid, "sequence": sequence})
            if card.get("stored_prose", 0) != 0:
                raise RuntimeError("stored_prose")
            cards.append(card)
        return cards

    def snapshot(self) -> dict[str, Any]:
        mass = dropped = conflicts = 0
        for _cid, _name, organ in self.organs:
            snap = organ.snapshot()
            dropped += int(snap["dropped"])
            mass += int(snap["mass"])
            conflicts += int(snap["conflicts"])
        return vision_card(
            "vision-batch",
            1 if len(self.organs) == CAPABILITY_COUNT else 0,
            "vol155-batch640",
            {"count": len(self.organs), "dropped": dropped, "mass": mass, "conflicts": conflicts, "heat_drop": HEAT_DROP},
        )

    def reverse_all(self) -> int:
        return sum(1 for _c, _n, organ in self.organs if organ.reverse() is not None)
