"""Live ops engine bound to a profile."""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.kernel.ops.fused import fused_block, naive_writes
from skeleton.kernel.ops.kvcache import KVCache
from skeleton.kernel.ops.qlinear import quantize
from skeleton.kernel.ops.sample import sample
from skeleton.kernel.ops._stat import reads, reset


def _eye(n: int) -> List[List[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


class Engine:
    def __init__(self, d: int = 8) -> None:
        self.d = max(4, min(16, int(d)))
        self.cache = KVCache(frames=8 if self.d <= 8 else 16, width=4 if self.d <= 8 else 8)
        ident = _eye(self.d)
        self.wq, self.sq = quantize(ident)
        self.wk, self.sk = quantize(ident)
        self.wv, self.sv = quantize(ident)
        self.wo, self.so = quantize(ident)
        self.runs = 0
        self.last_writes = 0

    def step(self, x: List[float] | None = None) -> Dict[str, Any]:
        vec = list(x) if x else [1.0 / self.d] * self.d
        if len(vec) != self.d:
            vec = (vec + [0.0] * self.d)[: self.d]
        reset()
        card = fused_block(
            vec, self.wq, self.sq, self.wk, self.sk, self.wv, self.sv,
            self.wo, self.so, self.cache,
        )
        self.runs += 1
        self.last_writes = int(card.get("writes") or 0)
        tok = sample(vec, k=1)
        return {
            "kind": "ops-engine",
            "d": self.d,
            "runs": self.runs,
            "writes": self.last_writes,
            "naive": naive_writes(1, self.d),
            "saved": max(0, naive_writes(1, self.d) - self.last_writes),
            "tok": tok,
            "kv": self.cache.card(),
            "stored_prose": 0,
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-ops",
            "d": self.d,
            "runs": self.runs,
            "writes": self.last_writes,
            "naive": naive_writes(1, self.d),
            "kv": self.cache.card(),
            "ops": ("matmul", "attention", "rmsnorm", "kvcache", "qlinear", "sample", "fused"),
            "stored_prose": 0,
        }


def writes() -> int:
    return reads()
