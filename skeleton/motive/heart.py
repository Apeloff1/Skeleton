"""heart(S) = H0 = 1."""

from __future__ import annotations

from skeleton.motive.cards import motive_card
from skeleton.motive.law import HEART_H0
from skeleton.motive.space import Pointed, sphere


def h0(x: Pointed) -> int:
    return 1 if x.base in x.points else 0


def heart(x: Pointed | None = None) -> int:
    return h0(x if x is not None else sphere())


def heart_card() -> dict:
    val = heart()
    return motive_card(
        kind="heart",
        hit=1 if val == HEART_H0 else 0,
        law="heart(S)=H0=1",
        extra={"H0": val},
    )
