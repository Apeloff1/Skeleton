"""Tree attention — speculative draft branches share a prefix.

Cite: Meta specdec tree KV. One prefix, many leaves. No full S.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump
from skeleton.kernel.ops.attention import attend

Row = List[float]
Slot = Tuple[Row, Row]


def tree(q_leaf: Row, prefix: List[Slot], branch: List[Slot]) -> Row:
    kv = list(prefix) + list(branch)
    out = attend(q_leaf, kv)
    bump(len(out))
    return out


def accept_path(scores: List[float]) -> int:
    if not scores:
        return 0
    bump(1)
    return max(range(len(scores)), key=lambda i: scores[i])
