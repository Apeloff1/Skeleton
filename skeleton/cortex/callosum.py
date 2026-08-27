"""Corpus callosum — left and right talk without becoming the same.

Two learned projections split the neo residual into a left stream and a
right stream. Each stream keeps a K-length working-memory bank. Query
of one attends over the other's bank (non-degenerate: K>1). A bilinear
coupling matrix C is Hebbian-updated when both hemispheres fire on the
same stimulus. Fusion is residual. Snapshot/restore is interchange.
Pure Python. No numpy.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

from skeleton.cortex.attn import add, dot, matvec, scale, softmax, zeros

Vec = List[float]
Mat = List[List[float]]

K_MEM = 4


def _rand_mat(rows: int, cols: int, scale_: float, seed: int) -> Mat:
    import random
    rng = random.Random(int(seed) & 0xFFFFFFFF)
    return [[rng.gauss(0.0, scale_) for _ in range(cols)] for _ in range(rows)]


def _copy_mat(m: Mat) -> Mat:
    return [list(row) for row in m]


def _eye(n: int, scale_: float = 1.0) -> Mat:
    out = [[0.0] * n for _ in range(n)]
    for i in range(n):
        out[i][i] = scale_
    return out


def energy(C: Mat, a: Sequence[float], b: Sequence[float]) -> float:
    """aᵀ C b — coupling energy of two streams."""
    acc = 0.0
    for i, ai in enumerate(a):
        row = C[i] if i < len(C) else []
        acc += ai * sum(row[j] * b[j] for j in range(min(len(row), len(b))))
    return acc


class CallosumMemory:
    """Ring of the last K projected hiddens per hemisphere."""

    def __init__(self, k: int = K_MEM) -> None:
        self.k = max(1, int(k))
        self.left: Deque[Vec] = deque(maxlen=self.k)
        self.right: Deque[Vec] = deque(maxlen=self.k)

    def push(self, left: Optional[Sequence[float]], right: Optional[Sequence[float]]) -> None:
        if left is not None:
            self.left.append(list(left))
        if right is not None:
            self.right.append(list(right))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "k": self.k,
            "left": [list(v) for v in self.left],
            "right": [list(v) for v in self.right],
        }

    def restore(self, data: Dict[str, Any]) -> None:
        self.k = max(1, int((data or {}).get("k") or self.k))
        self.left = deque((list(map(float, v)) for v in ((data or {}).get("left") or [])), maxlen=self.k)
        self.right = deque((list(map(float, v)) for v in ((data or {}).get("right") or [])), maxlen=self.k)


def _cross_attend(q: Vec, keys: List[Vec], values: List[Vec],
                  Wq: Mat, Wk: Mat, Wv: Mat) -> Tuple[Vec, List[float]]:
    if not keys or not values:
        return zeros(len(q)), []
    Q = matvec(Wq, q)
    Ks = [matvec(Wk, k) for k in keys]
    Vs = [matvec(Wv, v) for v in values]
    d = max(1, len(Q))
    inv = 1.0 / math.sqrt(d)
    scores = [dot(Q, K) * inv for K in Ks]
    w = softmax(scores)
    ctx = zeros(len(Vs[0]))
    for aij, vj in zip(w, Vs):
        for i, val in enumerate(vj):
            ctx[i] += aij * val
    return ctx, w


class CorpusCallosum:
    """The commissure. Split, attend, Hebb, fuse. One object, one residual."""

    def __init__(self, dim: int = 8, *, seed: int = 17, k: int = K_MEM) -> None:
        D = max(4, int(dim))
        self.dim = D
        self.Wl = _rand_mat(D, D, 0.08, seed)
        self.Wr = _rand_mat(D, D, 0.08, seed + 1)
        self.Wq_l = _rand_mat(D, D, 0.08, seed + 2)
        self.Wk_l = _rand_mat(D, D, 0.08, seed + 3)
        self.Wv_l = _rand_mat(D, D, 0.08, seed + 4)
        self.Wq_r = _rand_mat(D, D, 0.08, seed + 5)
        self.Wk_r = _rand_mat(D, D, 0.08, seed + 6)
        self.Wv_r = _rand_mat(D, D, 0.08, seed + 7)
        self.C = _eye(D, 0.05)
        self.gate_l = 0.35
        self.gate_r = 0.35
        self.mem = CallosumMemory(k=k)
        self.fires = 0
        self.hebbs = 0
        self.last_attn_lr: List[float] = []
        self.last_attn_rl: List[float] = []

    def split(self, h: Sequence[float]) -> Tuple[Vec, Vec]:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        return matvec(self.Wl, v), matvec(self.Wr, v)

    def fuse(
        self,
        h: Sequence[float],
        *,
        left_on: bool = True,
        right_on: bool = True,
    ) -> Tuple[Vec, Vec, Vec]:
        """Returns (fused, h_left', h_right'). Memory updates when a side fires."""
        h_l, h_r = self.split(h)
        if left_on:
            self.mem.left.append(list(h_l))
        if right_on:
            self.mem.right.append(list(h_r))
        ctx_l, w_lr = _cross_attend(h_l, list(self.mem.right), list(self.mem.right),
                                    self.Wq_l, self.Wk_l, self.Wv_l)
        ctx_r, w_rl = _cross_attend(h_r, list(self.mem.left), list(self.mem.left),
                                    self.Wq_r, self.Wk_r, self.Wv_r)
        self.last_attn_lr = w_lr
        self.last_attn_rl = w_rl
        fused_l = add(h_l, scale(ctx_l, self.gate_l)) if ctx_l else list(h_l)
        fused_r = add(h_r, scale(ctx_r, self.gate_r)) if ctx_r else list(h_r)
        n = max(1, len(fused_l))
        fused = [(fused_l[i] + fused_r[i]) * 0.5 for i in range(n)]
        self.fires += 1
        return fused, fused_l, fused_r

    def hebb(self, h: Sequence[float], *, lr: float = 0.04) -> float:
        """When both streams fire, C += lr · outer(h_l, h_r). Returns Δenergy."""
        h_l, h_r = self.split(h)
        before = energy(self.C, h_l, h_r)
        for i, ai in enumerate(h_l):
            row = self.C[i]
            k = lr * ai
            for j, bj in enumerate(h_r):
                row[j] += k * bj
        after = energy(self.C, h_l, h_r)
        self.hebbs += 1
        return after - before

    def coupling(self, h: Sequence[float]) -> float:
        h_l, h_r = self.split(h)
        return energy(self.C, h_l, h_r)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "dim": self.dim,
            "Wl": _copy_mat(self.Wl), "Wr": _copy_mat(self.Wr),
            "Wq_l": _copy_mat(self.Wq_l), "Wk_l": _copy_mat(self.Wk_l), "Wv_l": _copy_mat(self.Wv_l),
            "Wq_r": _copy_mat(self.Wq_r), "Wk_r": _copy_mat(self.Wk_r), "Wv_r": _copy_mat(self.Wv_r),
            "C": _copy_mat(self.C),
            "gate_l": self.gate_l, "gate_r": self.gate_r,
            "mem": self.mem.snapshot(),
            "fires": self.fires, "hebbs": self.hebbs,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "CorpusCallosum":
        cc = cls(dim=int((data or {}).get("dim") or 8), seed=0)
        def _m(key: str, cur: Mat) -> Mat:
            raw = (data or {}).get(key)
            return [list(map(float, row)) for row in raw] if raw else cur
        cc.Wl, cc.Wr = _m("Wl", cc.Wl), _m("Wr", cc.Wr)
        cc.Wq_l, cc.Wk_l, cc.Wv_l = _m("Wq_l", cc.Wq_l), _m("Wk_l", cc.Wk_l), _m("Wv_l", cc.Wv_l)
        cc.Wq_r, cc.Wk_r, cc.Wv_r = _m("Wq_r", cc.Wq_r), _m("Wk_r", cc.Wk_r), _m("Wv_r", cc.Wv_r)
        cc.C = _m("C", cc.C)
        cc.gate_l = float((data or {}).get("gate_l") if (data or {}).get("gate_l") is not None else cc.gate_l)
        cc.gate_r = float((data or {}).get("gate_r") if (data or {}).get("gate_r") is not None else cc.gate_r)
        cc.fires = int((data or {}).get("fires") or 0)
        cc.hebbs = int((data or {}).get("hebbs") or 0)
        if (data or {}).get("mem"):
            cc.mem.restore(data["mem"])
        return cc

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dim": self.dim,
            "fires": self.fires,
            "hebbs": self.hebbs,
            "mem_left": len(self.mem.left),
            "mem_right": len(self.mem.right),
            "gate_l": round(self.gate_l, 4),
            "gate_r": round(self.gate_r, 4),
        }
