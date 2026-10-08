"""Conductor. Runs all 80 organs. Fail closed on prose or count drift."""

from __future__ import annotations

from typing import Any

from skeleton.speech.vol157.caps import ORGANS
from skeleton.speech.vol157.cards import speech_card
from skeleton.speech.vol157.law import CAPABILITY_COUNT, HEAT_DROP


class Conductor:
    def __init__(self) -> None:
        self.organs = [(cid, name, cls()) for cid, name, cls in ORGANS]
        if len(self.organs) != CAPABILITY_COUNT:
            raise RuntimeError("count")

    def pulse_all(self, generation: int, sequence: int, energy: float, pointers: tuple[str, ...] = ()) -> list[dict[str, Any]]:
        from skeleton.speech.vol157.caps.c01_generation_fence import Pulse

        cards: list[dict[str, Any]] = []
        for cid, _name, organ in self.organs:
            pulse = Pulse(generation=generation, sequence=sequence, energy=energy, pointers=pointers, cool=energy < 0.05)
            try:
                card = organ.family_gate(pulse)
            except ValueError as exc:
                card = speech_card(
                    "speech-reject",
                    0,
                    str(exc),
                    {"id": cid, "generation": generation, "sequence": sequence},
                )
            if card.get("stored_prose", 0) != 0:
                raise RuntimeError("stored_prose")
            cards.append(card)
        return cards

    def snapshot(self) -> dict[str, Any]:
        hits = 0
        dropped = 0
        mass = 0
        for _cid, _name, organ in self.organs:
            snap = organ.snapshot()
            hits += int(snap["hit"])
            dropped += int(snap["dropped"])
            mass += int(snap["mass"])
        return speech_card(
            "speech-batch",
            1 if len(self.organs) == CAPABILITY_COUNT else 0,
            "vol157-batch80",
            {
                "count": len(self.organs),
                "hits": hits,
                "dropped": dropped,
                "mass": mass,
                "heat_drop": HEAT_DROP,
                "G": 1.0,
                "G0": 1.0,
                "G_delta": 0.0,
                "mass_hint": mass,
            },
        )

    def reverse_all(self) -> int:
        n = 0
        for _cid, _name, organ in self.organs:
            if organ.reverse() is not None:
                n += 1
        return n
