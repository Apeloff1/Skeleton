"""Conductor for 1280 audio organs."""

from __future__ import annotations

from typing import Any

from skeleton.audio.vol156.caps import ORGANS
from skeleton.audio.vol156.cards import audio_card
from skeleton.audio.vol156.law import CAPABILITY_COUNT, HEAT_DROP

DIGEST = "ef" * 32


class Conductor:
    def __init__(self) -> None:
        self.organs = [(cid, name, cls()) for cid, name, cls in ORGANS]
        if len(self.organs) != CAPABILITY_COUNT:
            raise RuntimeError("count")

    def pulse_all(self, generation: int, sequence: int, kind: str = "event") -> list[dict[str, Any]]:
        from skeleton.audio.vol156.caps.c0001_asset_01 import EnvelopePulse

        cards: list[dict[str, Any]] = []
        for cid, _name, organ in self.organs:
            pulse = EnvelopePulse(
                generation=generation,
                sequence=sequence,
                asset_id="ASSET-VOL156",
                sample_rate=48000,
                channels=2,
                start_ms=sequence * 20,
                end_ms=sequence * 20 + 20,
                duration_ms=10_000,
                kind=kind,
                confidence=0.8,
                source_digest=DIGEST,
                pointers=("ptr:env", "ptr:kind"),
                cool=True,
            )
            try:
                card = organ.family_gate(pulse)
            except ValueError as exc:
                card = audio_card("audio-reject", 0, str(exc), {"id": cid, "sequence": sequence})
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
        return audio_card(
            "audio-batch",
            1 if len(self.organs) == CAPABILITY_COUNT else 0,
            "vol156-batch1280",
            {"count": len(self.organs), "dropped": dropped, "mass": mass, "heat_drop": HEAT_DROP},
        )

    def reverse_all(self) -> int:
        return sum(1 for _c, _n, organ in self.organs if organ.reverse() is not None)
