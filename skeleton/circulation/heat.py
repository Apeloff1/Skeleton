"""Heat, bleed, shunt_fever."""

from __future__ import annotations

from skeleton.circulation.cards import circ_card
from skeleton.circulation.law import BLEED, HEAT_DROP


def bleed(heat: float, rate: float = BLEED) -> float:
    out = heat * (1.0 - rate)
    if out < 0.0:
        return 0.0
    return out


def shunt_fever(heat_in: float, *, cool: bool = False) -> dict:
    if cool:
        heat_out = 0.0
        dropped = 0
    else:
        heat_out = bleed(heat_in)
        dropped = 1 if heat_out >= HEAT_DROP else 0
    return circ_card(
        kind="shunt_fever",
        hit=1,
        law="drop if heat_out>=0.90 after bleed; cool drops 0",
        extra={"heat_in": heat_in, "heat_out": heat_out, "dropped": dropped, "cool": int(cool)},
    )
