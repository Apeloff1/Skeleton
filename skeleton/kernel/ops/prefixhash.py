"""Prefix-cache hash — reuse KV when the prompt prefix matches.

Cite: SGLang radix / vLLM prefix caching. Hash only. No body.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from skeleton.kernel.ops._stat import bump

Row = List[float]
Slot = Tuple[Row, Row]


def hsh(tokens: List[int]) -> int:
    acc = 2166136261
    for t in tokens:
        acc ^= int(t) & 0xFFFFFFFF
        acc = (acc * 16777619) & 0xFFFFFFFF
    bump(1)
    return acc


class PrefixCache:
    def __init__(self) -> None:
        self.tab: Dict[int, List[Slot]] = {}

    def get(self, tokens: List[int]) -> List[Slot]:
        return list(self.tab.get(hsh(tokens), []))

    def put(self, tokens: List[int], kv: List[Slot]) -> int:
        key = hsh(tokens)
        self.tab[key] = list(kv)
        bump(len(kv))
        return key

    def card(self) -> dict:
        return {"kind": "prefix-cache", "n": len(self.tab), "stored_prose": 0}
