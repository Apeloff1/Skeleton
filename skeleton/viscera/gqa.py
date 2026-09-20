"""Grouped-query attention. n_q % n_kv == 0. No torch."""

from __future__ import annotations

from typing import Sequence

from skeleton.viscera.mathutil import dot
from skeleton.viscera.qk_norm import qk_norm


def group_of(qid: int, n_q: int, n_kv: int) -> int:
    if n_q % n_kv != 0:
        raise ValueError("gqa")
    width = n_q // n_kv
    return qid // width


def gqa_scores(
    queries: Sequence[Sequence[float]],
    keys: Sequence[Sequence[float]],
    *,
    n_kv: int,
    norm: bool = True,
) -> list[float]:
    n_q = len(queries)
    if n_q % n_kv != 0 or len(keys) != n_kv:
        raise ValueError("gqa-shape")
    out: list[float] = []
    for qi, q in enumerate(queries):
        k = keys[group_of(qi, n_q, n_kv)]
        qq, kk = (qk_norm(q, k) if norm else (list(q), list(k)))
        out.append(dot(qq, kk))
    return out
