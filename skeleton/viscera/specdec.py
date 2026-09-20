"""Speculative verify. Accept-until-mismatch. No torch."""

from __future__ import annotations

from typing import Sequence

from skeleton.viscera.cards import viscera_card


def verify(draft: Sequence[int], target: Sequence[int]) -> int:
    n = 0
    for a, b in zip(draft, target):
        if a != b:
            break
        n += 1
    return n


def specdec_card(draft: Sequence[int], target: Sequence[int]) -> dict:
    acc = verify(draft, target)
    return viscera_card(
        kind="specdec",
        hit=1 if acc <= min(len(draft), len(target)) else 0,
        law="accept-until-mismatch",
        extra={"accepted": acc, "draft_n": len(draft), "target_n": len(target)},
    )
