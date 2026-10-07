"""QK-norm: RMS on q and k."""

from __future__ import annotations

from typing import Sequence

from skeleton.viscera.cards import viscera_card
from skeleton.viscera.mathutil import dot, normalize_rms


def qk_norm(q: Sequence[float], k: Sequence[float]) -> tuple[list[float], list[float]]:
    return normalize_rms(q), normalize_rms(k)


def attend(q: Sequence[float], k: Sequence[float], *, norm: bool = True) -> float:
    qq, kk = (qk_norm(q, k) if norm else (list(q), list(k)))
    return dot(qq, kk)


def qk_card(q: Sequence[float], k: Sequence[float]) -> dict:
    score = attend(q, k)
    finite = score == score
    return viscera_card(
        kind="qk_norm",
        hit=1 if finite else 0,
        law="QK-norm RMS",
        extra={"score": score},
    )
