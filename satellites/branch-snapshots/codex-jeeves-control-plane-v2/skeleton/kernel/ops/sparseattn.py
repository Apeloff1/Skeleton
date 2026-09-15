"""Token-sparse attention — DeepSeek DSA / FlashPrefill V2 family.

Keep top-m KV slots by |q·k|. Mean-correct the drop. No full S.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.attention import attend

Row = List[float]
Slot = Tuple[Row, Row]


def _score(q: Row, k: Row) -> float:
    return sum(a * b for a, b in zip(q, k))


def sparse(q: Row, kv: List[Slot], *, keep: int = 2) -> Row:
    if not kv:
        return list(q)
    m = max(1, min(int(keep), len(kv)))
    ranked = sorted(range(len(kv)), key=lambda i: _score(q, kv[i][0]), reverse=True)
    chosen = [kv[i] for i in ranked[:m]]
    dropped = [kv[i] for i in ranked[m:]]
    o = attend(q, chosen)
    if dropped:
        mean_v = [0.0] * len(dropped[0][1])
        for _, v in dropped:
            for i, val in enumerate(v):
                mean_v[i] += val
        n = len(dropped)
        corr = 0.05
        o = [oi + corr * (mv / n) for oi, mv in zip(o, mean_v)]
    bump(len(o))
    return o


def density(keep: int, n: int) -> float:
    return 0.0 if n <= 0 else min(1.0, float(keep) / float(n))
