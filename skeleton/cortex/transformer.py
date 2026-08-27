"""Tiny causal transformer — the medium language model.

One attention head over a prefix, then a next-token softmax. Skip-gram
only sees the last token; this net mixes the whole window. That is the
identity. Pure Python. No numpy. Snapshot/restore is interchange.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from skeleton.cortex.attn import (
    add,
    add_outer,
    causal_attend,
    matvec,
    matvec_T,
    scale,
    softmax,
    zeros,
    zeros2,
)
from skeleton.cortex.port import Thought, fingerprint, tokens

UNK = "__unk__"


def _rand_mat(rows: int, cols: int, scale_: float, rng: random.Random) -> List[List[float]]:
    return [[rng.gauss(0.0, scale_) for _ in range(cols)] for _ in range(rows)]


class TinyTransformer:
    """Causal attention LM. P(next | prefix), not P(next | last)."""

    def __init__(
        self,
        vocab: Iterable[str] | None = None,
        *,
        dim: int = 8,
        ctx: int = 6,
        seed: int = 0,
    ) -> None:
        itos = [UNK] + sorted({str(t) for t in (vocab or ()) if t and t != UNK})
        self.itos: List[str] = itos
        self.stoi: Dict[str, int] = {t: i for i, t in enumerate(itos)}
        self.unk = 0
        V = max(2, len(itos))
        D = max(4, int(dim))
        C = max(2, int(ctx))
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        s = 0.08
        self.E = _rand_mat(V, D, s, rng)
        self.P = _rand_mat(C, D, s, rng)
        self.Wq = _rand_mat(D, D, s, rng)
        self.Wk = _rand_mat(D, D, s, rng)
        self.Wv = _rand_mat(D, D, s, rng)
        self.Wo = _rand_mat(D, D, s, rng)
        self.Wout = _rand_mat(V, D, s, rng)
        self.bout = zeros(V)
        self.dim = D
        self.ctx = C
        self.fitted = 0
        self.steps = 0

    @property
    def V(self) -> int:
        return len(self.E)

    def _id(self, tok: str) -> int:
        return int(self.stoi.get(tok, self.unk))

    def _encode(self, ids: Sequence[int]) -> List[List[float]]:
        X: List[List[float]] = []
        for t, idx in enumerate(ids):
            X.append(add(self.E[idx], self.P[t]))
        return X

    def _logits(self, ids: Sequence[int]) -> List[float]:
        X = self._encode(ids)
        Q = [matvec(self.Wq, x) for x in X]
        K = [matvec(self.Wk, x) for x in X]
        V = [matvec(self.Wv, x) for x in X]
        C, _ = causal_attend(Q, K, V)
        H = matvec(self.Wo, C[-1])
        return add(matvec(self.Wout, H), self.bout)

    def hidden(self, prefix: str) -> List[float]:
        """Last-position context vector. Mixes the whole prefix."""
        ids = [self._id(t) for t in tokens(prefix)] or [self.unk]
        ids = ids[-self.ctx:]
        X = self._encode(ids)
        Q = [matvec(self.Wq, x) for x in X]
        K = [matvec(self.Wk, x) for x in X]
        V = [matvec(self.Wv, x) for x in X]
        C, _ = causal_attend(Q, K, V)
        return list(C[-1])

    def weights_last(self, prefix: str) -> List[float]:
        ids = [self._id(t) for t in tokens(prefix)] or [self.unk]
        ids = ids[-self.ctx:]
        X = self._encode(ids)
        Q = [matvec(self.Wq, x) for x in X]
        K = [matvec(self.Wk, x) for x in X]
        V = [matvec(self.Wv, x) for x in X]
        _, A = causal_attend(Q, K, V)
        return list(A[-1])

    def token_prob(self, prefix: str, tok: str) -> float:
        ids = [self._id(t) for t in tokens(prefix)] or [self.unk]
        ids = ids[-self.ctx:]
        p = softmax(self._logits(ids))
        return float(p[self._id(tok)])

    def _sgd(self, ids: List[int], target: int, lr: float) -> float:
        """Last-token CE through one causal head."""
        n = len(ids)
        D = self.dim
        X = self._encode(ids)
        Q = [matvec(self.Wq, x) for x in X]
        K = [matvec(self.Wk, x) for x in X]
        V = [matvec(self.Wv, x) for x in X]
        C, A = causal_attend(Q, K, V)
        H = matvec(self.Wo, C[-1])
        logits = add(matvec(self.Wout, H), self.bout)
        p = softmax(logits)
        loss = -math.log(max(p[target], 1e-12))
        dlog = [p[v] - (1.0 if v == target else 0.0) for v in range(self.V)]

        dH = matvec_T(self.Wout, dlog)
        add_outer(self.Wout, dlog, H, -lr)
        for v in range(self.V):
            self.bout[v] -= lr * dlog[v]

        dC_last = matvec_T(self.Wo, dH)
        add_outer(self.Wo, dH, C[-1], -lr)

        i = n - 1
        w = A[i]
        dV = [zeros(D) for _ in range(n)]
        dA = zeros(n)
        for j, aij in enumerate(w):
            for d in range(D):
                dV[j][d] += dC_last[d] * aij
            dA[j] = sum(dC_last[d] * V[j][d] for d in range(D))
        # softmax backward on last row
        dot_da = sum(dA[j] * w[j] for j in range(len(w)))
        ds = [(dA[j] - dot_da) * w[j] for j in range(len(w))]
        inv = 1.0 / math.sqrt(D)
        dQ_i = zeros(D)
        dK = [zeros(D) for _ in range(n)]
        for j, dsj in enumerate(ds):
            g = dsj * inv
            for d in range(D):
                dQ_i[d] += K[j][d] * g
                dK[j][d] += Q[i][d] * g

        dX = [zeros(D) for _ in range(n)]
        add_outer(self.Wq, dQ_i, X[i], -lr)
        dx = matvec_T(self.Wq, dQ_i)
        dX[i] = add(dX[i], dx)
        for j in range(n):
            add_outer(self.Wk, dK[j], X[j], -lr)
            dX[j] = add(dX[j], matvec_T(self.Wk, dK[j]))
            add_outer(self.Wv, dV[j], X[j], -lr)
            dX[j] = add(dX[j], matvec_T(self.Wv, dV[j]))
        for t, idx in enumerate(ids):
            dx = scale(dX[t], lr)
            for d in range(D):
                self.E[idx][d] -= dx[d]
                self.P[t][d] -= dx[d]
        self.steps += 1
        return loss

    def fit(self, texts: Iterable[str], *, lr: float = 0.06) -> int:
        n = 0
        for raw in texts:
            body = tokens(raw)
            if len(body) < 2:
                continue
            ids = [self._id(t) for t in body]
            for i in range(1, len(ids)):
                window = ids[max(0, i - self.ctx):i]
                self._sgd(window, ids[i], lr)
                n += 1
            self.fitted += 1
        return n

    def logprob(self, text: str) -> float:
        body = tokens(text)
        if len(body) < 2:
            return math.log(1.0 / max(1, self.V))
        ids = [self._id(t) for t in body]
        lp = 0.0
        n = 0
        for i in range(1, len(ids)):
            window = ids[max(0, i - self.ctx):i]
            p = softmax(self._logits(window))
            lp += math.log(max(p[ids[i]], 1e-12))
            n += 1
        return lp / max(1, n)

    def perplexity(self, texts: Iterable[str] | str) -> float:
        if isinstance(texts, str):
            seq = [texts]
        else:
            seq = [t for t in texts if t]
        if not seq:
            return float(self.V)
        mean = sum(self.logprob(t) for t in seq) / len(seq)
        return math.exp(-mean)

    def decode(self, prefix: str, *, n: int = 14, seed: int = 0) -> str:
        """CPU next-token decode. No GPU. No torch."""
        return " ".join(self.generate(prefix, n=n, seed=seed))

    def generate(self, prefix: str | Sequence[str], n: int = 12, *, seed: int = 0) -> Tuple[str, ...]:
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        if isinstance(prefix, str):
            body = list(tokens(prefix))
        else:
            body = [str(t) for t in prefix]
        ids = [self._id(t) for t in body] or [self.unk]
        out = list(ids)
        for _ in range(max(1, n)):
            window = out[-self.ctx:]
            p = softmax(self._logits(window))
            r = rng.random()
            acc = 0.0
            nxt = self.V - 1
            for v, pv in enumerate(p):
                acc += pv
                if acc >= r:
                    nxt = v
                    break
            out.append(nxt)
        return tuple(self.itos[i] if 0 <= i < len(self.itos) else UNK for i in out[:n])

    def snapshot(self) -> Dict[str, Any]:
        return {
            "dim": self.dim,
            "ctx": self.ctx,
            "fitted": self.fitted,
            "steps": self.steps,
            "itos": list(self.itos),
            "E": [list(r) for r in self.E],
            "P": [list(r) for r in self.P],
            "Wq": [list(r) for r in self.Wq],
            "Wk": [list(r) for r in self.Wk],
            "Wv": [list(r) for r in self.Wv],
            "Wo": [list(r) for r in self.Wo],
            "Wout": [list(r) for r in self.Wout],
            "bout": list(self.bout),
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "TinyTransformer":
        itos = list((data or {}).get("itos") or [UNK])
        lm = cls(
            vocab=[t for t in itos if t != UNK],
            dim=int((data or {}).get("dim") or 8),
            ctx=int((data or {}).get("ctx") or 6),
            seed=0,
        )
        lm.itos = itos
        lm.stoi = {t: i for i, t in enumerate(itos)}
        def _m(key: str, cur: List[List[float]]) -> List[List[float]]:
            raw = (data or {}).get(key)
            return [list(map(float, row)) for row in raw] if raw else cur
        lm.E = _m("E", lm.E)
        lm.P = _m("P", lm.P)
        lm.Wq = _m("Wq", lm.Wq)
        lm.Wk = _m("Wk", lm.Wk)
        lm.Wv = _m("Wv", lm.Wv)
        lm.Wo = _m("Wo", lm.Wo)
        lm.Wout = _m("Wout", lm.Wout)
        b = (data or {}).get("bout")
        if b:
            lm.bout = [float(x) for x in b]
        lm.fitted = int((data or {}).get("fitted") or 0)
        lm.steps = int((data or {}).get("steps") or 0)
        return lm


class TransformerBackend:
    """ModelPort wrapping TinyTransformer. Medium scale. Midbrain/neo."""

    def __init__(self, lm: TinyTransformer, *, slot: str = "midbrain", name: str = "attn") -> None:
        self.lm = lm
        self.slot = slot
        self.name = name
        self.scale = "medium"

    def fit(self, text: str) -> int:
        return self.lm.fit([text])

    def snapshot(self) -> Dict[str, Any]:
        snap = self.lm.snapshot()
        snap["slot"] = self.slot
        snap["name"] = self.name
        snap["kind"] = "transformer"
        return snap

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], *, slot: str | None = None) -> "TransformerBackend":
        lm = TinyTransformer.from_snapshot(data or {})
        sl = slot or str((data or {}).get("slot") or "midbrain")
        return cls(lm, slot=sl, name=str((data or {}).get("name") or "imported-attn"))

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        text = stimulus or ""
        seed = int(fingerprint(text)[:8], 16) if text else 0
        gen = " ".join(self.lm.generate(text, n=14, seed=seed))
        if self.slot == "midbrain":
            from skeleton.cortex.midbrain import _weights
            arousal, lw, rw = _weights(text)
            return Thought(
                slot="midbrain", kind="route",
                text=f"COORD {gen}",
                confidence=0.82,
                tags=("route", "coordinator", "medium", "attn")
                + (("left",) if lw >= 0.25 else ())
                + (("right",) if rw >= 0.25 else ()),
                numbers=(arousal, lw, rw),
            )
        return Thought(
            slot=self.slot, kind="plan",
            text=gen or text[:160],
            confidence=0.70,
            tags=("attn", "medium", self.slot),
            numbers=(float(self.lm.dim), float(self.lm.steps)),
        )
