"""Multi-head Latent Attention — DeepSeek-style compressed KV.

One latent row, not per-head K/V writes. Obscure, bandwidth-first.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.attention import attend

Row = List[float]


def _compress(rows: List[Row], latent: int) -> Row:
    if not rows:
        return [0.0] * max(1, latent)
    d = len(rows[0])
    lat = max(1, min(int(latent), d))
    acc = [0.0] * lat
    for r in rows:
        for i in range(lat):
            acc[i] += r[i % len(r)]
    n = max(1, len(rows))
    out = [v / n for v in acc]
    bump(len(out))
    return out


def mla(q: Row, kv: List[Tuple[Row, Row]], *, latent: int = 4) -> Row:
    if not kv:
        return list(q)
    ks = [k for k, _ in kv]
    vs = [v for _, v in kv]
    ck = _compress(ks, latent)
    cv = _compress(vs, latent)
    # one latent slot through the tiled attend
    out = attend(q[: len(ck)] if len(q) >= len(ck) else q + [0.0] * (len(ck) - len(q)), [(ck, cv)])
    bump(len(out))
    return out


def mla_bytes(heads: int, d: int, latent: int) -> int:
    # naive KV = 2 * heads * d ; latent KV = 2 * latent
    return 2 * max(1, int(latent))
