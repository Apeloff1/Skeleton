"""Compose shunt_fever hot and cool paths."""

from __future__ import annotations

from typing import Any

from skeleton.circulation.cards import circ_card
from skeleton.circulation.heat import shunt_fever


class CirculationEngine:
    def snapshot(self) -> dict[str, Any]:
        hot = shunt_fever(1.2)
        cool = shunt_fever(1.2, cool=True)
        ok = hot["dropped"] == 1 and cool["dropped"] == 0
        return circ_card(
            kind="circulation",
            hit=1 if ok else 0,
            law="circulation 1.0",
            extra={"hot_dropped": hot["dropped"], "cool_dropped": cool["dropped"]},
        )
