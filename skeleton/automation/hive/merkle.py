"""Local merkle of roots. No network."""

from __future__ import annotations

import hashlib
from typing import Iterable


def digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def merkle_pair(a: str, b: str) -> str:
    lo, hi = (a, b) if a <= b else (b, a)
    return digest("m:" + lo + ":" + hi)


def fold(roots: Iterable[str]) -> str:
    items = [r for r in roots if r]
    if not items:
        return digest("empty")
    while len(items) > 1:
        nxt: list[str] = []
        for i in range(0, len(items), 2):
            if i + 1 < len(items):
                nxt.append(merkle_pair(items[i], items[i + 1]))
            else:
                nxt.append(items[i])
        items = nxt
    return items[0]
