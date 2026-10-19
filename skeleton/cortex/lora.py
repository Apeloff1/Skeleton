"""LoRA — the interchangeable adapter, not a second net.

y = W x + (α / r) B (A x)
Birth: B = 0 ⇒ identity. Merge folds BA into W so a peer that does not
speak LoRA still inherits. Snapshot is the hive gene.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence

from skeleton.cortex.attn import add, add_outer, matvec, matvec_T, scale, softmax

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

    def expand_rank(self, new_rank: int, *, seed: int = 101) -> int:
        """Function-preserving LoRA rank expansion (zero-padded B columns)."""
        target = max(self.rank, min(int(new_rank), min(self.out_dim, self.in_dim)))
        if target <= self.rank:
            return self.rank
        extra = target - self.rank
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        old_scale = self.scale
        new_scale = self.alpha / float(target)
        ratio = old_scale / max(new_scale, 1e-12)
        for i in range(self.out_dim):
            self.B[i] = [x * ratio for x in self.B[i]] + [0.0] * extra
        s_a = 1.0 / math.sqrt(max(1, self.in_dim))
        for _ in range(extra):
            self.A.append([rng.gauss(0.0, s_a) for _ in range(self.in_dim)])
        self.rank = target
        self.scale = new_scale
        return self.rank

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

    def fit_output(self, lm, texts: Iterable[str], *, lr: float = 0.04) -> int:
        """Train the mergeable output adapter from real next-token CE gradients.

        Contact training historically attached a LoRA bank but only updated the
        base transformer. This focused path teaches Wout using the same hidden
        states and targets as the language-model objective, so the adapter gene
        accumulates meaningful state that can later be snapshotted or merged.
        """
        adapter = self.adapters.get("Wout")
        if adapter is None or not hasattr(lm, "_ids") or not hasattr(lm, "_forward"):
            return 0
        ctx = max(1, int(getattr(lm, "ctx", 6) or 6))
        steps = 0
        for raw in texts:
            if not raw:
                continue
            ids = list(lm._ids(raw))
            for i in range(1, len(ids)):
                window = ids[max(0, i - ctx):i]
                if not window:
                    continue
                hidden, _ = lm._forward(window)
                if not hidden:
                    continue
                y = list(hidden[-1])
                logits = list(lm._unembed(y))
                probs = softmax(logits)
                target = int(ids[i])
                if target < 0 or target >= len(probs):
                    continue
                dlog = [p - (1.0 if j == target else 0.0) for j, p in enumerate(probs)]
                adapter.step(y, dlog, float(lr))
                steps += 1
        return steps

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

    def expand_rank(self, new_rank: int) -> Dict[str, Any]:
        """Function-preserving rank increase across all adapters in the bank."""
        ranks = {}
        for idx, (name, ad) in enumerate(self.adapters.items()):
            ranks[name] = ad.expand_rank(new_rank, seed=self.seed + 109 * (idx + 1))
        if ranks:
            self.rank = max(ranks.values())
        return {"rank": self.rank, "adapters": ranks}

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


class ContextConditionedLoRA:
    """HyperLoRA / Dynamic HyperNetwork Weight Generator.

    Synthesizes input-conditioned low-rank rank-r diagonal modulation gates
    g(z) = 1 + tanh(W_hyper * z + b_hyper) from a game brief / genre / console
    context embedding z, so the effective weight perturbation is:
        delta(x, z) = (alpha / r) * B * diag(g(z)) * (A * x)
    """

    def __init__(
        self,
        out_dim: int,
        in_dim: int,
        *,
        ctx_dim: int = 8,
        rank: int = 2,
        alpha: float = 4.0,
        seed: int = 0,
        name: str = "W",
    ) -> None:
        self.base = LoRA(out_dim, in_dim, rank=rank, alpha=alpha, seed=seed, name=name)
        self.ctx_dim = max(1, int(ctx_dim))
        self.rank = self.base.rank
        self.alpha = self.base.alpha
        self.out_dim = self.base.out_dim
        self.in_dim = self.base.in_dim
        self.name = self.base.name
        rng = random.Random((int(seed) ^ 0x5A17C3) & 0xFFFFFFFF)
        self.W_hyper: Mat = _rand_mat(self.rank, self.ctx_dim, 0.15 / math.sqrt(self.ctx_dim), rng)
        self.b_hyper: Vec = [0.0] * self.rank
        self._active_ctx: Vec = [0.0] * self.ctx_dim
        self.hyper_steps = 0

    def _fit_ctx(self, ctx_vec: Optional[Sequence[float]]) -> Vec:
        if not ctx_vec:
            return list(self._active_ctx)
        raw = [float(v) for v in ctx_vec]
        if len(raw) >= self.ctx_dim:
            return raw[: self.ctx_dim]
        return raw + [0.0] * (self.ctx_dim - len(raw))

    def bind_context(self, ctx_vec: Sequence[float]) -> Vec:
        self._active_ctx = self._fit_ctx(ctx_vec)
        return self.gate(self._active_ctx)

    def gate(self, ctx_vec: Optional[Sequence[float]] = None) -> Vec:
        z = self._fit_ctx(ctx_vec)
        raw = matvec(self.W_hyper, z)
        return [1.0 + math.tanh(raw[k] + self.b_hyper[k]) for k in range(self.rank)]

    def delta(self, x: Sequence[float], ctx_vec: Optional[Sequence[float]] = None) -> Vec:
        ax = matvec(self.base.A, list(x))
        g = self.gate(ctx_vec)
        gated = [ax[k] * g[k] for k in range(self.rank)]
        return scale(matvec(self.base.B, gated), self.base.scale)

    def apply(self, Wx: Sequence[float], x: Sequence[float], ctx_vec: Optional[Sequence[float]] = None) -> Vec:
        return add(list(Wx), self.delta(x, ctx_vec))

    def step(
        self,
        x: Sequence[float],
        dY: Sequence[float],
        lr: float,
        ctx_vec: Optional[Sequence[float]] = None,
    ) -> Vec:
        xv = list(x)
        dy = list(dY)
        z = self._fit_ctx(ctx_vec)
        ax = matvec(self.base.A, xv)
        g = self.gate(z)
        gated_ax = [ax[k] * g[k] for k in range(self.rank)]
        s = self.base.scale
        bt_dy = matvec_T(self.base.B, dy)
        # Gradient wrt gated rank vector
        d_gated = [bt_dy[k] * s for k in range(self.rank)]
        # Gradient wrt hypernetwork gate g_k: dL/dg_k = d_gated[k] * ax[k], dg_k/du_k = 1 - (g_k - 1)^2
        for k in range(self.rank):
            th = g[k] - 1.0
            du = d_gated[k] * ax[k] * max(0.05, 1.0 - th * th)
            self.b_hyper[k] -= lr * 0.5 * du
            for c_idx in range(self.ctx_dim):
                self.W_hyper[k][c_idx] -= lr * 0.5 * du * z[c_idx]
        # Update base A and B with context-gated activation
        dz = [d_gated[k] * g[k] for k in range(self.rank)]
        add_outer(self.base.B, scale(dy, s), gated_ax, -lr)
        add_outer(self.base.A, dz, xv, -lr)
        self.base.steps += 1
        self.hyper_steps += 1
        return matvec_T(self.base.A, dz)

    def materialize_lora(self, ctx_vec: Optional[Sequence[float]] = None) -> LoRA:
        """Compile a fast static LoRA adapter for a specific game context vector."""
        g = self.gate(ctx_vec)
        compiled = LoRA(
            self.out_dim,
            self.in_dim,
            rank=self.rank,
            alpha=self.alpha,
            name=self.name,
        )
        compiled.A = [[self.base.A[k][j] * g[k] for j in range(self.in_dim)] for k in range(self.rank)]
        compiled.B = _copy(self.base.B)
        compiled.steps = self.base.steps
        return compiled

    def energy(self) -> float:
        base_e = self.base.energy()
        hyper_e = sum(x * x for row in self.W_hyper for x in row) + sum(b * b for b in self.b_hyper)
        return base_e + hyper_e

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": "hyper-lora",
            "ctx_dim": self.ctx_dim,
            "base": self.base.snapshot(),
            "W_hyper": _copy(self.W_hyper),
            "b_hyper": list(self.b_hyper),
            "active_ctx": list(self._active_ctx),
            "hyper_steps": self.hyper_steps,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "ContextConditionedLoRA":
        base_snap = (data or {}).get("base") or {}
        base = LoRA.from_snapshot(base_snap)
        obj = cls(
            base.out_dim,
            base.in_dim,
            ctx_dim=int((data or {}).get("ctx_dim") or 8),
            rank=base.rank,
            alpha=base.alpha,
            name=base.name,
        )
        obj.base = base
        if (data or {}).get("W_hyper"):
            obj.W_hyper = [list(map(float, row)) for row in data["W_hyper"]]
        if (data or {}).get("b_hyper"):
            obj.b_hyper = [float(x) for x in data["b_hyper"]]
        if (data or {}).get("active_ctx"):
            obj._active_ctx = [float(x) for x in data["active_ctx"]]
        obj.hyper_steps = int((data or {}).get("hyper_steps") or 0)
        return obj


class HyperLoRABank:
    """Bank of context-conditioned HyperLoRA adapters across transformer projections."""

    TARGETS = ("Wq", "Wv", "Wout")

    def __init__(self, *, ctx_dim: int = 8, rank: int = 2, alpha: float = 4.0, seed: int = 0) -> None:
        self.ctx_dim = max(1, int(ctx_dim))
        self.rank = max(1, int(rank))
        self.alpha = float(alpha)
        self.seed = int(seed) & 0xFFFFFFFF
        self.adapters: Dict[str, ContextConditionedLoRA] = {}

    def attach(self, lm, targets: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        names = tuple(targets or self.TARGETS)
        D = int(getattr(lm, "dim", 8) or 8)
        V = int(getattr(lm, "V", D) or D)
        attached = []
        for i, name in enumerate(names):
            out_d, in_d = (V, D) if name == "Wout" else (D, D)
            self.adapters[name] = ContextConditionedLoRA(
                out_d,
                in_d,
                ctx_dim=self.ctx_dim,
                rank=self.rank,
                alpha=self.alpha,
                seed=self.seed + 31 * (i + 1),
                name=name,
            )
            attached.append(name)
        setattr(lm, "hyper_lora", self)
        return {"attached": attached, "rank": self.rank, "ctx_dim": self.ctx_dim, "alpha": self.alpha}

    def bind_context(self, ctx_vec: Sequence[float]) -> Dict[str, List[float]]:
        gates: Dict[str, List[float]] = {}
        for name, ad in self.adapters.items():
            gates[name] = [round(v, 6) for v in ad.bind_context(ctx_vec)]
        return gates

    def fit_contextual(
        self,
        lm,
        contextual_texts: Iterable[tuple[Sequence[float], str]],
        *,
        lr: float = 0.04,
    ) -> Dict[str, Any]:
        """Train context-conditioned HyperLoRA adapters on (context_vector, text) pairs."""
        adapter = self.adapters.get("Wout")
        if adapter is None or not hasattr(lm, "_ids") or not hasattr(lm, "_forward"):
            return {"steps": 0, "mean_loss": 0.0}
        ctx_len = max(1, int(getattr(lm, "ctx", 6) or 6))
        steps = 0
        total_loss = 0.0
        for ctx_vec, raw in contextual_texts:
            if not raw:
                continue
            adapter.bind_context(ctx_vec)
            ids = list(lm._ids(raw))
            for i in range(1, len(ids)):
                window = ids[max(0, i - ctx_len):i]
                if not window:
                    continue
                hidden, _ = lm._forward(window)
                if not hidden:
                    continue
                y = list(hidden[-1])
                base_logits = list(lm._unembed(y))
                logits = adapter.apply(base_logits, y, ctx_vec)
                probs = softmax(logits)
                target = int(ids[i])
                if target < 0 or target >= len(probs):
                    continue
                total_loss += -math.log(max(probs[target], 1e-12))
                dlog = [p - (1.0 if j == target else 0.0) for j, p in enumerate(probs)]
                adapter.step(y, dlog, float(lr), ctx_vec)
                steps += 1
        return {
            "steps": steps,
            "mean_loss": round(total_loss / max(1, steps), 6),
            "energy": round(sum(a.energy() for a in self.adapters.values()), 8),
        }

    def compile_static_bank(self, ctx_vec: Sequence[float]) -> LoRABank:
        """Materialize a standard LoRABank specialized for the given game context vector."""
        bank = LoRABank(rank=self.rank, alpha=self.alpha, seed=self.seed)
        for name, ad in self.adapters.items():
            bank.adapters[name] = ad.materialize_lora(ctx_vec)
        return bank

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": "hyper-lora-bank",
            "ctx_dim": self.ctx_dim,
            "rank": self.rank,
            "alpha": self.alpha,
            "seed": self.seed,
            "adapters": {k: v.snapshot() for k, v in self.adapters.items()},
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "HyperLoRABank":
        bank = cls(
            ctx_dim=int((data or {}).get("ctx_dim") or 8),
            rank=int((data or {}).get("rank") or 2),
            alpha=float((data or {}).get("alpha") or 4.0),
            seed=int((data or {}).get("seed") or 0),
        )
        for k, blob in ((data or {}).get("adapters") or {}).items():
            bank.adapters[str(k)] = ContextConditionedLoRA.from_snapshot(blob)
        return bank

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "hyper-lora-bank",
            "ctx_dim": self.ctx_dim,
            "rank": self.rank,
            "n": len(self.adapters),
            "hyper_steps": sum(a.hyper_steps for a in self.adapters.values()),
            "energy": round(sum(a.energy() for a in self.adapters.values()), 8),
        }
