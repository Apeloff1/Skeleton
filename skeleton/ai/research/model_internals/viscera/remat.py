"""Rematerialize: second forward == first."""

from __future__ import annotations

from typing import Callable, Sequence

from skeleton.viscera.cards import viscera_card


def remat(fn: Callable[[Sequence[float]], list[float]], x: Sequence[float]) -> tuple[list[float], list[float], bool]:
    a = list(fn(x))
    b = list(fn(x))
    same = a == b
    return a, b, same


def remat_card(fn: Callable[[Sequence[float]], list[float]], x: Sequence[float]) -> dict:
    _, _, same = remat(fn, x)
    return viscera_card(
        kind="remat",
        hit=1 if same else 0,
        law="remat identity",
        extra={"identity": int(same)},
    )
