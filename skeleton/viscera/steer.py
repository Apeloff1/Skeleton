"""Activation steer: h <- h + alpha u-hat."""

from __future__ import annotations

from typing import Sequence

from skeleton.viscera.cards import viscera_card
from skeleton.viscera.law import STEER_ALPHA
from skeleton.viscera.mathutil import add, normalize_rms, scale


def steer(h: Sequence[float], u: Sequence[float], alpha: float = STEER_ALPHA) -> list[float]:
    uhat = normalize_rms(u)
    return add(h, scale(uhat, alpha))


def steer_card(h: Sequence[float], u: Sequence[float]) -> dict:
    out = steer(h, u)
    return viscera_card(
        kind="steer",
        hit=1 if len(out) == len(h) else 0,
        law="h += alpha u-hat",
        extra={"n": len(out), "alpha": STEER_ALPHA},
    )
