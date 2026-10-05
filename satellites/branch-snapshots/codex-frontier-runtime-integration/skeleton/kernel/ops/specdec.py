"""Speculative / EAGLE / MTP verify.

Cite: Meta Llama specdec 2508.08192. Draft tokens, accept prefix.
"""
from __future__ import annotations

from typing import List, Sequence

from skeleton.kernel.ops._stat import bump


def verify(draft: Sequence[int], target: Sequence[int]) -> dict:
    n = min(len(draft), len(target))
    accepted = 0
    for i in range(n):
        if draft[i] != target[i]:
            break
        accepted += 1
    bump(1)
    return {
        "kind": "spec-verify",
        "accepted": accepted,
        "draft_n": len(draft),
        "bonus": 1 if accepted == n and target[n:] else 0,
        "stored_prose": 0,
    }


def mtp_head(hidden: Sequence[float], n: int = 2) -> List[int]:
    # deterministic next-n from argmax slices
    if not hidden:
        return [0] * max(1, n)
    out = []
    for i in range(max(1, int(n))):
        sl = hidden[i:] or hidden
        out.append(max(range(len(sl)), key=lambda j: sl[j]))
    bump(len(out))
    return out
