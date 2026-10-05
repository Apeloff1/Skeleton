"""Paged KV — vLLM-style slots. Page table only.

Cite: Kwon et al. PagedAttention. Blocks, not one fat tensor.
"""
from __future__ import annotations

from typing import List, Tuple

from skeleton.kernel.ops._stat import bump

Row = List[float]
Slot = Tuple[Row, Row]


class PageKV:
    def __init__(self, page: int = 4) -> None:
        self.page = max(1, int(page))
        self.pages: List[List[Slot]] = []

    def put(self, k: Row, v: Row) -> None:
        if not self.pages or len(self.pages[-1]) >= self.page:
            self.pages.append([])
        self.pages[-1].append((list(k), list(v)))
        bump(1)

    def rows(self) -> List[Slot]:
        out: List[Slot] = []
        for p in self.pages:
            out.extend(p)
        return out

    def card(self) -> dict:
        return {
            "kind": "page-kv",
            "pages": len(self.pages),
            "n": sum(len(p) for p in self.pages),
            "page": self.page,
            "stored_prose": 0,
        }
