"""Conductor for 160 supply-chain organs."""

from __future__ import annotations

from typing import Any

from skeleton.supply_chain.vol178.caps import ORGANS
from skeleton.supply_chain.vol178.cards import supply_card
from skeleton.supply_chain.vol178.law import CAPABILITY_COUNT, HEAT_DROP


DIGEST = "a" * 64
REVISION = "b" * 40


class Conductor:
    def __init__(self) -> None:
        self.organs = [(cid, name, cls()) for cid, name, cls in ORGANS]
        if len(self.organs) != CAPABILITY_COUNT:
            raise RuntimeError("count")

    def pulse_all(self, generation: int, sequence: int, scope: str = "direct", severity: str = "low", status: str = "open") -> list[dict[str, Any]]:
        from skeleton.supply_chain.vol178.caps.c001_component_id_grammar import ComponentPulse

        cards: list[dict[str, Any]] = []
        for cid, _name, organ in self.organs:
            pulse = ComponentPulse(
                generation=generation,
                sequence=sequence,
                component_id=f"cmp-{sequence}",
                scope=scope,
                severity=severity,
                status=status,
                digest=DIGEST,
                revision=REVISION,
                pointers=("pkg:pypi/skeleton", "ptr:license"),
                cool=severity == "low",
            )
            try:
                card = organ.family_gate(pulse)
            except ValueError as exc:
                card = supply_card("supply-reject", 0, str(exc), {"id": cid, "sequence": sequence})
            if card.get("stored_prose", 0) != 0:
                raise RuntimeError("stored_prose")
            cards.append(card)
        return cards

    def snapshot(self) -> dict[str, Any]:
        mass = dropped = hits = 0
        for _cid, _name, organ in self.organs:
            snap = organ.snapshot()
            hits += int(snap["hit"])
            dropped += int(snap["dropped"])
            mass += int(snap["mass"])
        return supply_card(
            "supply-batch",
            1 if len(self.organs) == CAPABILITY_COUNT else 0,
            "vol178-batch160",
            {"count": len(self.organs), "hits": hits, "dropped": dropped, "mass": mass, "heat_drop": HEAT_DROP},
        )

    def reverse_all(self) -> int:
        return sum(1 for _c, _n, organ in self.organs if organ.reverse() is not None)
