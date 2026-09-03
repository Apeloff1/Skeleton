"""Full house block: embed → RMS → RoPE → fused attn → SwiGLU → sample.

One working row through the obligatory + extra ops. Writes counted.
No nine-matrix path.
"""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.kernel.ops._stat import reset, reads
from skeleton.kernel.ops.embed import Embed
from skeleton.kernel.ops.rmsnorm import rmsnorm
from skeleton.kernel.ops.rope import rope
from skeleton.kernel.ops.qlinear import qlinear, quantize
from skeleton.kernel.ops.attention import attend
from skeleton.kernel.ops.kvcache import KVCache
from skeleton.kernel.ops.residual import residual
from skeleton.kernel.ops.swiglu import swiglu
from skeleton.kernel.ops.sample import sample
from skeleton.kernel.ops.fused import naive_writes


def _eye(n: int) -> List[List[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


class Block:
    def __init__(self, d: int = 8) -> None:
        self.d = max(4, min(16, int(d)))
        self.embed = Embed(d=self.d)
        ident = _eye(self.d)
        self.wq, self.sq = quantize(ident)
        self.wk, self.sk = quantize(ident)
        self.wv, self.sv = quantize(ident)
        self.wo, self.so = quantize(ident)
        self.wg, self.sg = quantize(ident)
        self.wu, self.su = quantize(ident)
        self.wd, self.sd = quantize(ident)
        self.cache = KVCache(frames=8, width=4)
        self.runs = 0
        self.last_writes = 0

    def forward(self, tokens: List[str] | None = None) -> Dict[str, Any]:
        reset()
        toks = [t for t in (tokens or ["plan", "tensor"]) if t][:4]
        x = self.embed.row(toks[0] if toks else "plan")
        h = rmsnorm(x)
        h = rope(h, pos=self.runs)
        q = qlinear(h, self.wq, self.sq)
        k = qlinear(h, self.wk, self.sk)
        v = qlinear(h, self.wv, self.sv)
        self.cache.put(k, v)
        o = attend(q, self.cache.rows())
        y = qlinear(o, self.wo, self.so)
        h = residual(x, y)
        n = rmsnorm(h)
        g = qlinear(n, self.wg, self.sg)
        u = qlinear(n, self.wu, self.su)
        m = swiglu(g, u)
        z = qlinear(m, self.wd, self.sd)
        h = residual(h, z)
        tok = sample(h, k=1)
        self.runs += 1
        self.last_writes = reads()
        return {
            "kind": "kernel-block",
            "d": self.d,
            "runs": self.runs,
            "writes": self.last_writes,
            "naive": naive_writes(1, self.d),
            "saved": max(0, naive_writes(1, self.d) - self.last_writes),
            "tok": tok,
            "kv": self.cache.card(),
            "tokens": toks,
            "stored_prose": 0,
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-block",
            "d": self.d,
            "runs": self.runs,
            "writes": self.last_writes,
            "path": "embed rms rope qkv attn res rms swiglu res sample",
            "stored_prose": 0,
        }
