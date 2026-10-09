"""Conductor for 320 video organs."""

from __future__ import annotations

from typing import Any

from skeleton.video.vol158.caps import ORGANS
from skeleton.video.vol158.cards import video_card
from skeleton.video.vol158.law import CAPABILITY_COUNT, HEAT_DROP

DIGEST = "ab" * 32


class Conductor:
    def __init__(self) -> None:
        self.organs = [(cid, name, cls()) for cid, name, cls in ORGANS]
        if len(self.organs) != CAPABILITY_COUNT:
            raise RuntimeError("count")

    def pulse_all(self, generation: int, sequence: int, keyframe: bool = True) -> list[dict[str, Any]]:
        from skeleton.video.vol158.caps.c001_asset_01 import FramePulse

        cards: list[dict[str, Any]] = []
        for cid, _name, organ in self.organs:
            pulse = FramePulse(
                generation=generation,
                sequence=sequence,
                asset_id="ASSET-VOL158",
                width=640,
                height=360,
                timestamp_ms=sequence * 40,
                frame_digest=DIGEST,
                pointers=("ptr:gop", "ptr:pts"),
                cool=True,
                keyframe=keyframe,
            )
            try:
                card = organ.family_gate(pulse)
            except ValueError as exc:
                card = video_card("video-reject", 0, str(exc), {"id": cid, "sequence": sequence})
            if card.get("stored_prose", 0) != 0:
                raise RuntimeError("stored_prose")
            cards.append(card)
        return cards

    def snapshot(self) -> dict[str, Any]:
        mass = dropped = 0
        for _cid, _name, organ in self.organs:
            snap = organ.snapshot()
            dropped += int(snap["dropped"])
            mass += int(snap["mass"])
        return video_card(
            "video-batch",
            1 if len(self.organs) == CAPABILITY_COUNT else 0,
            "vol158-batch320",
            {"count": len(self.organs), "dropped": dropped, "mass": mass, "heat_drop": HEAT_DROP},
        )

    def reverse_all(self) -> int:
        return sum(1 for _c, _n, organ in self.organs if organ.reverse() is not None)
