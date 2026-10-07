"""Absmax int8 quant. SNR must be finite."""

from __future__ import annotations

from typing import Sequence

from skeleton.viscera.cards import viscera_card
from skeleton.viscera.law import INT8_ABSMAX
from skeleton.viscera.mathutil import snr_db


def absmax_int8(xs: Sequence[float]) -> tuple[list[int], float]:
    peak = max((abs(v) for v in xs), default=0.0)
    scale = peak / INT8_ABSMAX if peak > 0.0 else 1.0
    q = [int(round(v / scale)) for v in xs]
    q = [max(-127, min(127, v)) for v in q]
    return q, scale


def dequant(q: Sequence[int], scale: float) -> list[float]:
    return [v * scale for v in q]


def quant_snr(xs: Sequence[float]) -> float:
    q, scale = absmax_int8(xs)
    return snr_db(xs, dequant(q, scale))


def quant_card(xs: Sequence[float]) -> dict:
    snr = quant_snr(xs)
    finite = snr == snr and snr != float("-inf")
    return viscera_card(
        kind="quant",
        hit=1 if finite else 0,
        law="absmax int8 SNR finite",
        extra={"snr": snr if snr != float("inf") else 1e9},
    )
