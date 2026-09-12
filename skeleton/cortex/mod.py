"""Mixture of Depths — per-token compute allocation for the neo residual.

Sibling to Mixture-of-Experts (moe.py): MoE routes across *experts*;
MoD routes across *depth* — skip / shallow / deep — per token.

skip     → identity / residual only (no block compute)
shallow  → cheap partial block (attention residual, no FFN)
deep     → full Pre-LN block (attention + FFN)

A capacity router keeps the deep/shallow budgets deterministic and
testable. Inject a custom router or fixed capacities in tests.
Pure Python. No numpy. No torch.
"""
from __future__ import annotations

import random
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from skeleton.cortex.attn import dot

Vec = List[float]
Mat = List[List[float]]

SKIP = "skip"
SHALLOW = "shallow"
DEEP = "deep"
Depth = str  # one of SKIP | SHALLOW | DEEP


def _rand_vec(dim: int, scale: float, rng: random.Random) -> Vec:
    return [rng.gauss(0.0, scale) for _ in range(dim)]


def allocate_depths(
    scores: Sequence[float],
    *,
    deep_capacity: float = 0.25,
    shallow_capacity: float = 0.25,
) -> List[Depth]:
    """Top-k by score → deep, next band → shallow, remainder → skip.

    Capacities are fractions of sequence length in (0, 1]. Ties break by
    lower index so the mapping is deterministic for a fixed score vector.
    """
    n = len(scores)
    if n == 0:
        return []
    deep_k = max(0, min(n, int(round(float(deep_capacity) * n))))
    shallow_k = max(0, min(n - deep_k, int(round(float(shallow_capacity) * n))))
    # Stable: higher score first, then lower index.
    order = sorted(range(n), key=lambda i: (-float(scores[i]), i))
    out: List[Depth] = [SKIP] * n
    for i in order[:deep_k]:
        out[i] = DEEP
    for i in order[deep_k : deep_k + shallow_k]:
        out[i] = SHALLOW
    return out


class DepthRouter:
    """Linear score per token hidden; capacity bands decide depth."""

    def __init__(
        self,
        dim: int,
        *,
        seed: int = 23,
        deep_capacity: float = 0.25,
        shallow_capacity: float = 0.25,
    ) -> None:
        D = max(1, int(dim))
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        self.w: Vec = _rand_vec(D, 0.08, rng)
        self.b: float = 0.0
        self.dim = D
        self.deep_capacity = float(deep_capacity)
        self.shallow_capacity = float(shallow_capacity)
        self.steps = 0

    def score(self, X: Sequence[Sequence[float]]) -> List[float]:
        out: List[float] = []
        for h in X:
            v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
            out.append(dot(self.w, v) + self.b)
        return out

    def decide(self, X: Sequence[Sequence[float]]) -> List[Depth]:
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
        r = cls(
            dim=int((data or {}).get("dim") or 8),
            seed=0,
            deep_capacity=float((data or {}).get("deep_capacity") or 0.25),
            shallow_capacity=float((data or {}).get("shallow_capacity") or 0.25),
        )
        w = (data or {}).get("w")
        if w:
            r.w = [float(x) for x in w]
        r.b = float((data or {}).get("b") or 0.0)
        r.steps = int((data or {}).get("steps") or 0)
        return r


RouterFn = Callable[[Sequence[Sequence[float]]], List[Depth]]


class MixtureOfDepths:
    """Per-layer MoD wrapper: route tokens, then blend skip/shallow/deep."""

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
        self.decide_fn = decide_fn  # injectable override for tests
        self.forwards = 0
        self.tokens_seen = 0
        self.tokens_skip = 0
        self.tokens_shallow = 0
        self.tokens_deep = 0

    def route(self, X: Sequence[Sequence[float]]) -> List[Depth]:
        if self.decide_fn is not None:
            return list(self.decide_fn(X))
        return self.router.decide(X)

    def forward_block(
        self,
        block: Any,
        X: List[List[float]],
        n_heads: int,
    ) -> Tuple[List[List[float]], Dict[str, Any]]:
        """Apply skip / shallow / deep per token against one TransformerBlock.

        Soft MoD: shallow and deep paths run on the full sequence so causal
        attention stays coherent; per-token output is selected by the router.
        Skip tokens keep the residual identity (X[t]).
        """
        n = len(X)
        decisions = self.route(X) if n else []
        if len(decisions) != n:
            decisions = (list(decisions) + [DEEP] * n)[:n]

        need_deep = any(d == DEEP for d in decisions)
        need_shallow = any(d == SHALLOW for d in decisions)

        Y_deep: Optional[List[List[float]]] = None
        cache_deep: Dict[str, Any] = {}
        Y_shallow: Optional[List[List[float]]] = None
        cache_shallow: Dict[str, Any] = {}

        if need_deep:
            Y_deep, cache_deep = block.forward(X, n_heads)
        if need_shallow:
            if hasattr(block, "forward_shallow"):
                Y_shallow, cache_shallow = block.forward_shallow(X, n_heads)
            else:
                # Fallback: full forward stands in for shallow if block is bare.
                Y_shallow, cache_shallow = block.forward(X, n_heads)

        Y: List[List[float]] = []
        for t in range(n):
            d = decisions[t]
            if d == DEEP and Y_deep is not None:
                Y.append(list(Y_deep[t]))
                self.tokens_deep += 1
            elif d == SHALLOW and Y_shallow is not None:
                Y.append(list(Y_shallow[t]))
                self.tokens_shallow += 1
            else:
                Y.append(list(X[t]))
                self.tokens_skip += 1

        self.forwards += 1
        self.tokens_seen += n
        cache: Dict[str, Any] = {
            "X": X,
            "depths": list(decisions),
            "mod": True,
            "deep": cache_deep,
            "shallow": cache_shallow,
            "n_heads": n_heads,
        }
        # Prefer deep cache fields for compat readers that expect attn keys.
        if cache_deep:
            for k, v in cache_deep.items():
                cache.setdefault(k, v)
        elif cache_shallow:
            for k, v in cache_shallow.items():
                cache.setdefault(k, v)
        return Y, cache

    def stats(self) -> Dict[str, Any]:
        return {
            "forwards": self.forwards,
            "tokens_seen": self.tokens_seen,
            "tokens_skip": self.tokens_skip,
            "tokens_shallow": self.tokens_shallow,
            "tokens_deep": self.tokens_deep,
            "deep_capacity": self.router.deep_capacity,
            "shallow_capacity": self.router.shallow_capacity,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "dim": self.dim,
            "router": self.router.snapshot(),
            "forwards": self.forwards,
            "tokens_seen": self.tokens_seen,
            "tokens_skip": self.tokens_skip,
            "tokens_shallow": self.tokens_shallow,
            "tokens_deep": self.tokens_deep,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "MixtureOfDepths":
        router_blob = (data or {}).get("router") or {}
        mod = cls(
            dim=int((data or {}).get("dim") or router_blob.get("dim") or 8),
            seed=0,
            deep_capacity=float(router_blob.get("deep_capacity") or 0.25),
            shallow_capacity=float(router_blob.get("shallow_capacity") or 0.25),
        )
        if router_blob:
            mod.router = DepthRouter.from_snapshot(router_blob)
        mod.forwards = int((data or {}).get("forwards") or 0)
        mod.tokens_seen = int((data or {}).get("tokens_seen") or 0)
        mod.tokens_skip = int((data or {}).get("tokens_skip") or 0)
        mod.tokens_shallow = int((data or {}).get("tokens_shallow") or 0)
        mod.tokens_deep = int((data or {}).get("tokens_deep") or 0)
        return mod

    def to_dict(self) -> Dict[str, Any]:
        return self.stats()
