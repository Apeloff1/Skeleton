"""LoRA — the interchangeable adapter, not a second net.

y = W x + (α / r) B (A x)
Birth: B = 0 ⇒ identity. Merge folds BA into W so a peer that does not
speak LoRA still inherits. Snapshot is the hive gene.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence

from skeleton.cortex.attn import add, add_outer, matvec, matvec_T, scale

Vec = List[float]
Mat = List[List[float]]


def _rand_mat(rows: int, cols: int, s: float, rng: random.Random) -> Mat:
    return [[rng.gauss(0.0, s) for _ in range(cols)] for _ in range(rows)]


def _zeros(rows: int, cols: int) -> Mat:
    return [[0.0] * cols for _ in range(rows)]


def _copy(m: Mat) -> Mat:
    return [list(row) for row in m]


class LoRA:
    def __init__(self, out_dim: int, in_dim: int, *, rank: int = 2, alpha: float = 4.0, seed: int = 0, name: str = "W") -> None:
        r = max(1, min(int(rank), min(out_dim, in_dim)))
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        self.A: Mat = _rand_mat(r, in_dim, 1.0 / math.sqrt(max(1, in_dim)), rng)
        self.B: Mat = _zeros(out_dim, r)
        self.rank = r
        self.alpha = float(alpha)
        self.out_dim = int(out_dim)
        self.in_dim = int(in_dim)
        self.name = str(name)
        self.steps = 0
        self.scale = self.alpha / float(r)

    def delta(self, x: Sequence[float]) -> Vec:
        return scale(matvec(self.B, matvec(self.A, list(x))), self.scale)

    def apply(self, Wx: Sequence[float], x: Sequence[float]) -> Vec:
        return add(list(Wx), self.delta(x))

    def step(self, x: Sequence[float], dY: Sequence[float], lr: float) -> Vec:
        xv, dy = list(x), list(dY)
        z = matvec(self.A, xv)
        s = self.scale
        dz = scale(matvec_T(self.B, dy), s)
        add_outer(self.B, scale(dy, s), z, -lr)
        add_outer(self.A, dz, xv, -lr)
        self.steps += 1
        return matvec_T(self.A, dz)

    def merge_into(self, W: Mat) -> Mat:
        for i in range(self.out_dim):
            brow = self.B[i]
            wrow = W[i]
            for j in range(self.in_dim):
                acc = 0.0
                for k in range(self.rank):
                    acc += brow[k] * self.A[k][j]
                wrow[j] += self.scale * acc
        self.B = _zeros(self.out_dim, self.rank)
        return W

    def energy(self) -> float:
        return sum(x * x for row in self.B for x in row)

    def snapshot(self) -> Dict[str, Any]:
        return {"name": self.name, "rank": self.rank, "alpha": self.alpha, "out_dim": self.out_dim,
                "in_dim": self.in_dim, "steps": self.steps, "A": _copy(self.A), "B": _copy(self.B)}

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "LoRA":
        obj = cls(int((data or {}).get("out_dim") or 1), int((data or {}).get("in_dim") or 1),
                  rank=int((data or {}).get("rank") or 1), alpha=float((data or {}).get("alpha") or 1.0),
                  name=str((data or {}).get("name") or "W"))
        if (data or {}).get("A"):
            obj.A = [list(map(float, row)) for row in data["A"]]
        if (data or {}).get("B"):
            obj.B = [list(map(float, row)) for row in data["B"]]
        obj.steps = int((data or {}).get("steps") or 0)
        obj.scale = obj.alpha / float(max(1, obj.rank))
        return obj

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "rank": self.rank, "alpha": self.alpha, "steps": self.steps, "energy": round(self.energy(), 8)}


class LoRABank:
    TARGETS = ("Wq", "Wv", "Wout")

    def __init__(self, *, rank: int = 2, alpha: float = 4.0, seed: int = 0) -> None:
        self.rank = max(1, int(rank))
        self.alpha = float(alpha)
        self.seed = int(seed) & 0xFFFFFFFF
        self.adapters: Dict[str, LoRA] = {}

    def attach(self, lm, targets: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        names = tuple(targets or self.TARGETS)
        D = int(getattr(lm, "dim", 8) or 8)
        V = int(getattr(lm, "V", D) or D)
        attached = []
        for i, name in enumerate(names):
            out_d, in_d = (V, D) if name == "Wout" else (D, D)
            self.adapters[name] = LoRA(out_d, in_d, rank=self.rank, alpha=self.alpha,
                                       seed=self.seed + 17 * (i + 1), name=name)
            attached.append(name)
        setattr(lm, "lora", self)
        return {"attached": attached, "rank": self.rank, "alpha": self.alpha}

    def merge(self, lm) -> Dict[str, Any]:
        merged = []
        L0 = lm.layers[0] if getattr(lm, "layers", None) else None
        for name, ad in list(self.adapters.items()):
            if name == "Wout" and hasattr(lm, "Wout"):
                ad.merge_into(lm.Wout)
                merged.append(name)
            elif L0 is not None and hasattr(L0, name):
                ad.merge_into(getattr(L0, name))
                merged.append(name)
        return {"merged": merged, "energy": sum(a.energy() for a in self.adapters.values())}

    def snapshot(self) -> Dict[str, Any]:
        return {"rank": self.rank, "alpha": self.alpha, "seed": self.seed,
                "adapters": {k: v.snapshot() for k, v in self.adapters.items()}}

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "LoRABank":
        bank = cls(rank=int((data or {}).get("rank") or 2), alpha=float((data or {}).get("alpha") or 4.0),
                   seed=int((data or {}).get("seed") or 0))
        for k, blob in ((data or {}).get("adapters") or {}).items():
            bank.adapters[str(k)] = LoRA.from_snapshot(blob)
        return bank

    def to_dict(self) -> Dict[str, Any]:
        return {"rank": self.rank, "n": len(self.adapters),
                "steps": sum(a.steps for a in self.adapters.values()),
                "energy": round(sum(a.energy() for a in self.adapters.values()), 8)}
