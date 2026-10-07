"""Radix kernel — shared-prefix trie.

Pointer: SGLang RadixAttention. House mapping is a token trie
with hit counts. No attention weights.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable


class _Node:
    __slots__ = ("kids", "hits")

    def __init__(self) -> None:
        self.kids: Dict[str, "_Node"] = {}
        self.hits = 0


class Radix:
    def __init__(self) -> None:
        self.root = _Node()
        self.nodes = 1
        self.lookups = 0

    def insert(self, tokens: Iterable[str]) -> int:
        node = self.root
        depth = 0
        for tok in tokens:
            if tok not in node.kids:
                node.kids[tok] = _Node()
                self.nodes += 1
            node = node.kids[tok]
            node.hits += 1
            depth += 1
        return depth

    def share(self, tokens: Iterable[str]) -> int:
        self.lookups += 1
        node = self.root
        depth = 0
        for tok in tokens:
            kid = node.kids.get(tok)
            if kid is None:
                break
            node = kid
            depth += 1
        return depth

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-radix",
            "nodes": self.nodes,
            "lookups": self.lookups,
            "stored_prose": 0,
        }
