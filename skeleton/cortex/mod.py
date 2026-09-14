"""Mixture of Depths — per-token compute allocation for the neo residual.

Sibling to Mixture-of-Experts (moe.py): MoE routes across *experts*;
MoD routes across *depth* — skip / shallow / deep — per token.

skip     -> identity / residual only (no block compute)
shallow  -> attention residual (no FFN)
deep     -> attention residual + pointwise FFN

The router is deterministic for a fixed score vector.  The execution path
shares one causal-attention pass across shallow/deep tokens and evaluates the
pointwise FFN only for tokens routed deep.  Training uses a routed backward
adapter so skip tokens retain their identity gradient, shallow tokens train the
attention path, and deep tokens train attention + FFN.

Pure Python. No numpy. No torch.
"""
from __future__ import annotations

import math
import random
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from skeleton.cortex.attn import add, dot, gelu, matvec, swiglu, zeros

Vec = List[float]
Mat = List[List[float]]

SKIP = "skip"
SHALLOW = "shallow"
DEEP = "deep"
Depth = str
_VALID_DEPTHS = {SKIP, SHALLOW, DEEP}


def _rand_vec(dim: int, scale: float, rng: random.Random) -> Vec:
    return [rng.gauss(0.0, scale) for _ in range(dim)]


def _capacity(value: float) -> float:
    """Normalise a capacity fraction into the closed unit interval."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v):
        return 0.0
    return max(0.0, min(1.0, v))


def _budget(capacity: float, n: int, available: int) -> int:
    """Translate a fractional capacity into a deterministic token budget.

    Positive capacities receive at least one slot when tokens are available;
    this avoids the surprising ``round(0.5) == 0`` behaviour for short
    sequences while never exceeding the remaining capacity.
    """
    cap = _capacity(capacity)
    if cap <= 0.0 or n <= 0 or available <= 0:
        return 0
    wanted = max(1, int(math.ceil(cap * n)))
    return min(available, wanted)


def allocate_depths(
    scores: Sequence[float],
    *,
    deep_capacity: float = 0.25,
    shallow_capacity: float = 0.25,
) -> List[Depth]:
    """Top-score tokens go deep, the next band shallow, the rest skip.

    Capacities are clamped to [0, 1].  Ties break by lower token index so the
    mapping is deterministic for a fixed score vector.
    """
    n = len(scores)
    if n == 0:
        return []
    deep_k = _budget(deep_capacity, n, n)
    shallow_k = _budget(shallow_capacity, n, n - deep_k)
    order = sorted(range(n), key=lambda i: (-float(scores[i]), i))
    out: List[Depth] = [SKIP] * n
    for i in order[:deep_k]:
        out[i] = DEEP
    for i in order[deep_k : deep_k + shallow_k]:
        out[i] = SHALLOW
    return out


class DepthRouter:
    """Linear token scorer with deterministic capacity-constrained routing."""

    def __init__(
        self,
        dim: int,
        *,
        seed: int = 23,
        deep_capacity: float = 0.25,
        shallow_capacity: float = 0.25,
    ) -> None:
        self.dim = max(1, int(dim))
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        self.w: Vec = _rand_vec(self.dim, 0.08, rng)
        self.b: float = 0.0
        self.deep_capacity = _capacity(deep_capacity)
        self.shallow_capacity = _capacity(shallow_capacity)
        self.steps = 0

    def score(self, X: Sequence[Sequence[float]]) -> List[float]:
        out: List[float] = []
        for h in X:
            v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
            out.append(dot(self.w, v) + self.b)
        return out

    def decide(self, X: Sequence[Sequence[float]]) -> List[Depth]:
        self.steps += 1
        return allocate_depths(
            self.score(X),
            deep_capacity=self.deep_capacity,
            shallow_capacity=self.shallow_capacity,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "w": list(self.w),
            "b": float(self.b),
            "dim": self.dim,
            "deep_capacity": self.deep_capacity,
            "shallow_capacity": self.shallow_capacity,
            "steps": self.steps,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "DepthRouter":
        blob = data or {}
        r = cls(
            dim=int(blob.get("dim") or 8),
            seed=0,
            deep_capacity=float(blob["deep_capacity"]) if "deep_capacity" in blob else 0.25,
            shallow_capacity=float(blob["shallow_capacity"]) if "shallow_capacity" in blob else 0.25,
        )
        w = blob.get("w")
        if w:
            r.w = [float(x) for x in w]
        r.b = float(blob.get("b") or 0.0)
        r.steps = int(blob.get("steps") or 0)
        return r


RouterFn = Callable[[Sequence[Sequence[float]]], List[Depth]]


class MixtureOfDepths:
    """Per-layer MoD router with selective FFN compute and routed backward."""

    SNAPSHOT_VERSION = 2

    def __init__(
        self,
        dim: int = 8,
        *,
        seed: int = 23,
        deep_capacity: float = 0.25,
        shallow_capacity: float = 0.25,
        router: Optional[DepthRouter] = None,
        decide_fn: Optional[RouterFn] = None,
    ) -> None:
        self.dim = max(1, int(dim))
        self.router = router or DepthRouter(
            self.dim,
            seed=seed,
            deep_capacity=deep_capacity,
            shallow_capacity=shallow_capacity,
        )
        self.decide_fn = decide_fn
        self.forwards = 0
        self.tokens_seen = 0
        self.tokens_skip = 0
        self.tokens_shallow = 0
        self.tokens_deep = 0
        self.attention_token_evals = 0
        self.ffn_token_evals = 0

    def route(self, X: Sequence[Sequence[float]]) -> List[Depth]:
        raw = list(self.decide_fn(X)) if self.decide_fn is not None else self.router.decide(X)
        n = len(X)
        raw = (raw + [DEEP] * n)[:n]
        return [d if d in _VALID_DEPTHS else DEEP for d in raw]

    @staticmethod
    def _install_backward_adapter(block: Any, owner: "MixtureOfDepths") -> None:
        """Teach an existing TransformerBlock how to consume MoD caches.

        TinyTransformer owns the ordinary backward loop.  Installing a tiny
        per-instance adapter lets MoD remain an optional sibling module without
        coupling transformer.py to routing internals.
        """
        if hasattr(block, "_mod_backward_original"):
            block._mod_owner = owner
            return
        block._mod_backward_original = block.backward
        block._mod_owner = owner

        def _wrapped(dY, cache, lr, _block=block):
            current = getattr(_block, "_mod_owner", owner)
            if isinstance(cache, dict) and cache.get("mod"):
                return current.backward_block(_block, dY, cache, lr)
            return _block._mod_backward_original(dY, cache, lr)

        block.backward = _wrapped

    @staticmethod
    def _shallow_cache(cache: Dict[str, Any]) -> Dict[str, Any]:
        c = dict(cache)
        for key in ("Un", "hats2", "invs2", "z", "pre", "gate", "up"):
            c[key] = []
        c["shallow"] = True
        return c

    def _selective_ffn(
        self,
        block: Any,
        U: List[List[float]],
        decisions: Sequence[Depth],
        cache: Dict[str, Any],
    ) -> List[List[float]]:
        """Apply the block FFN only to DEEP tokens and build backward cache."""
        n = len(U)
        ff = int(getattr(block, "d_ff", 0) or 0)
        if ff <= 0 or not any(d == DEEP for d in decisions):
            return [list(u) for u in U]

        Un = [zeros(int(getattr(block, "dim", self.dim))) for _ in range(n)]
        hats2 = [zeros(int(getattr(block, "dim", self.dim))) for _ in range(n)]
        invs2 = [0.0 for _ in range(n)]
        z = [zeros(ff) for _ in range(n)]
        pre = [zeros(ff) for _ in range(n)]
        gate = [zeros(ff) for _ in range(n)]
        up = [zeros(ff) for _ in range(n)]
        Y = [list(u) for u in U]

        for t, depth in enumerate(decisions):
            if depth != DEEP:
                continue
            un, hat, inv = block._norm(U[t], block.ln2_g, block.ln2_b)
            Un[t], hats2[t], invs2[t] = un, hat, inv
            if block.ffn_kind == "swiglu":
                zi, gi, ui = swiglu(un, block.W1, block.Wu, block.b1, block.bu)
                z[t], gate[t], up[t], pre[t] = zi, gi, ui, gi
            else:
                pi = add(matvec(block.W1, un), block.b1)
                pre[t] = pi
                z[t] = gelu(pi)
            Y[t] = add(U[t], add(matvec(block.W2, z[t]), block.b2))
            self.ffn_token_evals += 1

        cache.update({
            "Un": Un,
            "hats2": hats2,
            "invs2": invs2,
            "z": z,
            "pre": pre,
            "gate": gate,
            "up": up,
        })
        return Y

    def forward_block(
        self,
        block: Any,
        X: List[List[float]],
        n_heads: int,
    ) -> Tuple[List[List[float]], Dict[str, Any]]:
        """Route one transformer layer while preserving causal attention.

        Attention is shared once when at least one token is shallow/deep.  FFN
        work is pointwise and therefore performed only for deep tokens.  An
        all-skip route is a true identity and performs no block compute.
        """
        n = len(X)
        decisions = self.route(X) if n else []
        self._install_backward_adapter(block, self)

        active = any(d != SKIP for d in decisions)
        if active:
            U, attn_cache = block.forward_shallow(X, n_heads)
            self.attention_token_evals += n
            Y_active = self._selective_ffn(block, U, decisions, attn_cache)
        else:
            U = [list(x) for x in X]
            attn_cache = {}
            Y_active = U

        Y: List[List[float]] = []
        for t, depth in enumerate(decisions):
            if depth == SKIP:
                Y.append(list(X[t]))
                self.tokens_skip += 1
            elif depth == SHALLOW:
                Y.append(list(U[t]))
                self.tokens_shallow += 1
            else:
                Y.append(list(Y_active[t]))
                self.tokens_deep += 1

        self.forwards += 1
        self.tokens_seen += n
        cache: Dict[str, Any] = {
            "X": X,
            "U": U,
            "depths": list(decisions),
            "mod": True,
            "active": active,
            "base": attn_cache,
            "n_heads": n_heads,
        }
        if attn_cache:
            cache.update(attn_cache)
        return Y, cache

    def backward_block(
        self,
        block: Any,
        dY: List[List[float]],
        cache: Dict[str, Any],
        lr: float,
    ) -> List[List[float]]:
        """Backpropagate through the selected routes.

        Deep and shallow output gradients are masked and sent through their
        matching block paths; skip gradients pass through the identity.  This
        preserves route semantics and prevents all-skip caches from reaching
        TransformerBlock.backward, which expects attention tensors.
        """
        depths = list(cache.get("depths") or [])
        n = len(dY)
        if len(depths) != n:
            depths = (depths + [DEEP] * n)[:n]
        original = getattr(block, "_mod_backward_original", block.backward)
        D = int(getattr(block, "dim", self.dim))

        if not any(d != SKIP for d in depths):
            return [list(g) for g in dY]

        parts: List[List[List[float]]] = []
        if any(d == DEEP for d in depths):
            grad = [list(dY[t]) if depths[t] == DEEP else zeros(D) for t in range(n)]
            parts.append(original(grad, dict(cache.get("base") or cache), lr))
        if any(d == SHALLOW for d in depths):
            grad = [list(dY[t]) if depths[t] == SHALLOW else zeros(D) for t in range(n)]
            shallow = self._shallow_cache(dict(cache.get("base") or cache))
            parts.append(original(grad, shallow, lr))

        out = [zeros(D) for _ in range(n)]
        for part in parts:
            for t in range(min(n, len(part))):
                out[t] = add(out[t], part[t])
        for t, depth in enumerate(depths):
            if depth == SKIP:
                out[t] = add(out[t], list(dY[t]))
        return out

    def stats(self) -> Dict[str, Any]:
        seen = max(1, self.tokens_seen)
        return {
            "forwards": self.forwards,
            "tokens_seen": self.tokens_seen,
            "tokens_skip": self.tokens_skip,
            "tokens_shallow": self.tokens_shallow,
            "tokens_deep": self.tokens_deep,
            "attention_token_evals": self.attention_token_evals,
            "ffn_token_evals": self.ffn_token_evals,
            "ffn_fraction": self.ffn_token_evals / seen,
            "deep_capacity": self.router.deep_capacity,
            "shallow_capacity": self.router.shallow_capacity,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "version": self.SNAPSHOT_VERSION,
            "dim": self.dim,
            "router": self.router.snapshot(),
            "forwards": self.forwards,
            "tokens_seen": self.tokens_seen,
            "tokens_skip": self.tokens_skip,
            "tokens_shallow": self.tokens_shallow,
            "tokens_deep": self.tokens_deep,
            "attention_token_evals": self.attention_token_evals,
            "ffn_token_evals": self.ffn_token_evals,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "MixtureOfDepths":
        blob = data or {}
        router_blob = blob.get("router") or {}
        mod = cls(
            dim=int(blob.get("dim") or router_blob.get("dim") or 8),
            seed=0,
            deep_capacity=float(router_blob["deep_capacity"]) if "deep_capacity" in router_blob else 0.25,
            shallow_capacity=float(router_blob["shallow_capacity"]) if "shallow_capacity" in router_blob else 0.25,
        )
        if router_blob:
            mod.router = DepthRouter.from_snapshot(router_blob)
        mod.forwards = int(blob.get("forwards") or 0)
        mod.tokens_seen = int(blob.get("tokens_seen") or 0)
        mod.tokens_skip = int(blob.get("tokens_skip") or 0)
        mod.tokens_shallow = int(blob.get("tokens_shallow") or 0)
        mod.tokens_deep = int(blob.get("tokens_deep") or 0)
        mod.attention_token_evals = int(blob.get("attention_token_evals") or 0)
        mod.ffn_token_evals = int(blob.get("ffn_token_evals") or 0)
        return mod

    def to_dict(self) -> Dict[str, Any]:
        return self.stats()
