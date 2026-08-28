"""Tiny causal transformer — stacked Pre-LN blocks.

Skip-gram sees the last token. One layer mixes the window. Two layers
mix the mix — that is the identity. Pure Python. No numpy. No torch.
CUDA is a harness (torch_lm.TorchAccel) bound by to(), never imported
here. Snapshot/restore is interchange, including stacked layers.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from skeleton.cortex.attn import (
    add,
    add_outer,
    apply_rope,
    apply_rope_bwd,
    cached_mha,
    cosine_lr,
    gelu,
    gelu_bwd,
    layer_norm,
    layer_norm_bwd,
    matvec,
    matvec_T,
    mha_backward,
    multi_head_attend,
    ones,
    rms_norm,
    rms_norm_bwd,
    sample_logits,
    silu,
    softmax,
    swiglu,
    swiglu_bwd,
    zeros,
)
from skeleton.cortex.port import Thought, fingerprint, tokens

UNK = "__unk__"


def _rand_mat(rows: int, cols: int, scale_: float, rng: random.Random) -> List[List[float]]:
    return [[rng.gauss(0.0, scale_) for _ in range(cols)] for _ in range(rows)]


def _copy_mat(m: List[List[float]]) -> List[List[float]]:
    return [list(row) for row in m]


class TransformerBlock:
    """One Pre-LN residual block: X + Attn(LN(X)) then X + FFN(LN(X))."""

    def __init__(self, dim: int, d_ff: int, rng: random.Random, scale_: float, *,
                 norm: str = "ln", ffn_kind: str = "gelu") -> None:
        D = dim
        ff = max(0, int(d_ff))
        self.Wq = _rand_mat(D, D, scale_, rng)
        self.Wk = _rand_mat(D, D, scale_, rng)
        self.Wv = _rand_mat(D, D, scale_, rng)
        self.Wo = _rand_mat(D, D, scale_, rng)
        self.ln1_g = ones(D)
        self.ln1_b = zeros(D)
        self.W1 = _rand_mat(ff, D, scale_, rng) if ff else []
        self.b1 = zeros(ff) if ff else []
        self.Wu = _rand_mat(ff, D, scale_, rng) if ff else []
        self.bu = zeros(ff) if ff else []
        self.W2 = _rand_mat(D, ff, scale_, rng) if ff else []
        self.b2 = zeros(D) if ff else []
        self.ln2_g = ones(D)
        self.ln2_b = zeros(D)
        self.d_ff = ff
        self.dim = D
        self.norm = "rms" if str(norm).lower() == "rms" else "ln"
        self.ffn_kind = "swiglu" if str(ffn_kind).lower() == "swiglu" else "gelu"

    def _norm(self, x: List[float], g: List[float], b: List[float]):
        if self.norm == "rms":
            y, hat, inv = rms_norm(x, g)
            return y, hat, inv
        return layer_norm(x, g, b)

    def _norm_bwd(self, dy: List[float], hat: List[float], inv: float, g: List[float], x: Optional[List[float]] = None):
        if self.norm == "rms":
            src = x if x is not None else [hat[i] / inv if inv else hat[i] for i in range(len(hat))]
            dx, dg = rms_norm_bwd(dy, src, hat, inv, g)
            return dx, dg, zeros(len(dg))
        return layer_norm_bwd(dy, hat, inv, g)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "Wq": _copy_mat(self.Wq), "Wk": _copy_mat(self.Wk),
            "Wv": _copy_mat(self.Wv), "Wo": _copy_mat(self.Wo),
            "ln1_g": list(self.ln1_g), "ln1_b": list(self.ln1_b),
            "W1": _copy_mat(self.W1) if self.W1 else [],
            "b1": list(self.b1) if self.b1 else [],
            "Wu": _copy_mat(self.Wu) if self.Wu else [],
            "bu": list(self.bu) if self.bu else [],
            "W2": _copy_mat(self.W2) if self.W2 else [],
            "b2": list(self.b2) if self.b2 else [],
            "ln2_g": list(self.ln2_g), "ln2_b": list(self.ln2_b),
            "d_ff": self.d_ff, "dim": self.dim,
            "norm": self.norm, "ffn_kind": self.ffn_kind,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], *, dim: int, d_ff: int) -> "TransformerBlock":
        blk = cls(dim, d_ff, random.Random(0), 0.0,
                  norm=str((data or {}).get("norm") or "ln"),
                  ffn_kind=str((data or {}).get("ffn_kind") or "gelu"))
        def _m(key: str, cur: List[List[float]]) -> List[List[float]]:
            raw = (data or {}).get(key)
            return [list(map(float, row)) for row in raw] if raw else cur
        def _v(key: str, cur: List[float]) -> List[float]:
            raw = (data or {}).get(key)
            return [float(x) for x in raw] if raw else cur
        blk.Wq, blk.Wk = _m("Wq", blk.Wq), _m("Wk", blk.Wk)
        blk.Wv, blk.Wo = _m("Wv", blk.Wv), _m("Wo", blk.Wo)
        blk.W1, blk.W2 = _m("W1", blk.W1), _m("W2", blk.W2)
        blk.b1, blk.b2 = _v("b1", blk.b1), _v("b2", blk.b2)
        blk.Wu, blk.bu = _m("Wu", blk.Wu), _v("bu", blk.bu)
        blk.ln1_g, blk.ln1_b = _v("ln1_g", blk.ln1_g), _v("ln1_b", blk.ln1_b)
        blk.ln2_g, blk.ln2_b = _v("ln2_g", blk.ln2_g), _v("ln2_b", blk.ln2_b)
        if not blk.ln1_g:
            blk.ln1_g = ones(dim)
        if not blk.ln2_g:
            blk.ln2_g = ones(dim)
        return blk

    def forward(self, X: List[List[float]], n_heads: int):
        n = len(X)
        Xn: List[List[float]] = []
        hats1: List[List[float]] = []
        invs1: List[float] = []
        for x in X:
            y, hat, inv = self._norm(x, self.ln1_g, self.ln1_b)
            Xn.append(y)
            hats1.append(hat)
            invs1.append(inv)
        Q = [apply_rope(matvec(self.Wq, x), t) for t, x in enumerate(Xn)]
        K = [apply_rope(matvec(self.Wk, x), t) for t, x in enumerate(Xn)]
        V = [matvec(self.Wv, x) for x in Xn]
        C, As = multi_head_attend(Q, K, V, n_heads)
        attn = [matvec(self.Wo, c) for c in C]
        U = [add(X[t], attn[t]) for t in range(n)]
        z: List[List[float]] = []
        pre: List[List[float]] = []
        gate: List[List[float]] = []
        up: List[List[float]] = []
        Un: List[List[float]] = []
        hats2: List[List[float]] = []
        invs2: List[float] = []
        Y = U
        if self.d_ff:
            for u in U:
                y, hat, inv = self._norm(u, self.ln2_g, self.ln2_b)
                Un.append(y)
                hats2.append(hat)
                invs2.append(inv)
            if self.ffn_kind == "swiglu":
                for u in Un:
                    yi, g, p = swiglu(u, self.W1, self.Wu, self.b1, self.bu)
                    z.append(yi); gate.append(g); up.append(p)
                pre = gate
            else:
                pre = [add(matvec(self.W1, u), self.b1) for u in Un]
                z = [gelu(p) for p in pre]
            ff = [add(matvec(self.W2, zi), self.b2) for zi in z]
            Y = [add(U[t], ff[t]) for t in range(n)]
        cache = {
            "X": X, "Xn": Xn, "hats1": hats1, "invs1": invs1,
            "Q": Q, "K": K, "V": V, "C": C, "As": As, "attn": attn, "U": U,
            "Un": Un, "hats2": hats2, "invs2": invs2, "z": z, "pre": pre,
            "gate": gate, "up": up, "n_heads": n_heads,
        }
        return Y, cache

    def backward(self, dY: List[List[float]], cache: Dict[str, Any], lr: float) -> List[List[float]]:
        n = len(dY)
        D = self.dim
        for t in range(n):
            g = math.sqrt(sum(x * x for x in dY[t]))
            if g > 2.0:
                s = 2.0 / g
                dY[t] = [x * s for x in dY[t]]
        dU = [list(dY[t]) for t in range(n)]
        if self.d_ff and cache.get("z"):
            Un = cache["Un"]
            z = cache["z"]
            acc_b2 = zeros(D)
            acc_b1 = zeros(len(self.b1))
            d_Un = [zeros(D) for _ in range(n)]
            for t in range(n):
                add_outer(self.W2, dY[t], z[t], -lr)
                for i in range(D):
                    acc_b2[i] += dY[t][i]
                d_z = matvec_T(self.W2, dY[t])
                if self.ffn_kind == "swiglu" and cache.get("gate"):
                    d_gate, d_up = swiglu_bwd(d_z, cache["gate"][t], cache["up"][t])
                    add_outer(self.W1, d_gate, Un[t], -lr)
                    add_outer(self.Wu, d_up, Un[t], -lr)
                    for i in range(len(self.b1)):
                        acc_b1[i] += d_gate[i]
                        self.bu[i] -= lr * d_up[i]
                    d_Un[t] = add(matvec_T(self.W1, d_gate), matvec_T(self.Wu, d_up))
                else:
                    d_pre = gelu_bwd(d_z, cache["pre"][t])
                    add_outer(self.W1, d_pre, Un[t], -lr)
                    for i in range(len(self.b1)):
                        acc_b1[i] += d_pre[i]
                    d_Un[t] = matvec_T(self.W1, d_pre)
            for i in range(D):
                self.b2[i] -= lr * acc_b2[i]
            for i in range(len(self.b1)):
                self.b1[i] -= lr * acc_b1[i]
            acc_dg = zeros(D)
            acc_db = zeros(D)
            hats2 = cache["hats2"]
            invs2 = cache["invs2"]
            Usrc = cache.get("U") or []
            for t in range(n):
                dx, dg, db = self._norm_bwd(d_Un[t], hats2[t], invs2[t], self.ln2_g, Usrc[t] if t < len(Usrc) else None)
                dU[t] = add(dU[t], dx)
                acc_dg = add(acc_dg, dg)
                acc_db = add(acc_db, db)
            for i in range(D):
                self.ln2_g[i] -= lr * acc_dg[i]
                if self.norm != "rms":
                    self.ln2_b[i] -= lr * acc_db[i]

        C = cache["C"]
        Xn = cache["Xn"]
        dC = [matvec_T(self.Wo, dU[t]) for t in range(n)]
        for t in range(n):
            add_outer(self.Wo, dU[t], C[t], -lr)
        dQ, dK, dV = mha_backward(
            dC, cache["Q"], cache["K"], cache["V"], cache["As"], int(cache["n_heads"]),
        )
        dQ = [apply_rope_bwd(dq, t) for t, dq in enumerate(dQ)]
        dK = [apply_rope_bwd(dk, t) for t, dk in enumerate(dK)]
        dXn = [zeros(D) for _ in range(n)]
        for t in range(n):
            add_outer(self.Wq, dQ[t], Xn[t], -lr)
            add_outer(self.Wk, dK[t], Xn[t], -lr)
            add_outer(self.Wv, dV[t], Xn[t], -lr)
            dXn[t] = add(add(matvec_T(self.Wq, dQ[t]), matvec_T(self.Wk, dK[t])),
                         matvec_T(self.Wv, dV[t]))
        acc_dg = zeros(D)
        acc_db = zeros(D)
        dX_ln = [zeros(D) for _ in range(n)]
        hats1 = cache["hats1"]
        invs1 = cache["invs1"]
        Xsrc = cache.get("X") or []
        for t in range(n):
            dx, dg, db = self._norm_bwd(dXn[t], hats1[t], invs1[t], self.ln1_g, Xsrc[t] if t < len(Xsrc) else None)
            dX_ln[t] = dx
            acc_dg = add(acc_dg, dg)
            acc_db = add(acc_db, db)
        for i in range(D):
            self.ln1_g[i] -= lr * acc_dg[i]
            if self.norm != "rms":
                self.ln1_b[i] -= lr * acc_db[i]
        X = cache["X"]
        return [add(dU[t], dX_ln[t]) for t in range(n)] if X else dX_ln

    def step(
        self,
        x: List[float],
        Ks: List[List[float]],
        Vs: List[List[float]],
        n_heads: int,
        pos: int,
    ) -> List[float]:
        """One-token decode step. Ks/Vs grow with unroped keys; RoPE at attend time."""
        y, _, _ = self._norm(x, self.ln1_g, self.ln1_b)
        q = matvec(self.Wq, y)
        k = matvec(self.Wk, y)
        v = matvec(self.Wv, y)
        Ks.append(k)
        Vs.append(v)
        K_rope = [apply_rope(kk, t) for t, kk in enumerate(Ks)]
        q_rope = apply_rope(q, pos)
        c, _ = cached_mha(q_rope, K_rope, Vs, n_heads)
        attn = matvec(self.Wo, c)
        u = add(x, attn)
        if self.d_ff:
            un, _, _ = self._norm(u, self.ln2_g, self.ln2_b)
            if self.ffn_kind == "swiglu":
                z, _, _ = swiglu(un, self.W1, self.Wu, self.b1, self.bu)
            else:
                z = gelu(add(matvec(self.W1, un), self.b1))
            ff = add(matvec(self.W2, z), self.b2)
            return add(u, ff)
        return u


class KVCache:
    """Window-relative key/value bank. Reset when the window origin moves."""

    def __init__(self, n_layers: int, ctx: int) -> None:
        self.n_layers = max(1, int(n_layers))
        self.ctx = max(2, int(ctx))
        self.K: List[List[List[float]]] = [[] for _ in range(self.n_layers)]
        self.V: List[List[List[float]]] = [[] for _ in range(self.n_layers)]
        self.tokens: List[int] = []

    def reset(self) -> None:
        self.K = [[] for _ in range(self.n_layers)]
        self.V = [[] for _ in range(self.n_layers)]
        self.tokens = []

    def primed_for(self, window: Sequence[int]) -> bool:
        """True iff cache holds window[:-1] and can extend by window[-1]."""
        if not window:
            return False
        return self.tokens == list(window[:-1])


class TinyTransformer:
    """Causal attention LM. P(next | prefix), not P(next | last). Stackable."""

    def __init__(
        self,
        vocab: Iterable[str] | None = None,
        *,
        dim: int = 8,
        ctx: int = 6,
        seed: int = 0,
        n_heads: int = 1,
        n_layers: int = 1,
        d_ff: int = 0,
        norm: str = "ln",
        ffn_kind: str = "gelu",
    ) -> None:
        itos = [UNK] + sorted({str(t) for t in (vocab or ()) if t and t != UNK})
        self.itos: List[str] = itos
        self.stoi: Dict[str, int] = {t: i for i, t in enumerate(itos)}
        self.unk = 0
        V = max(2, len(itos))
        D = max(4, int(dim))
        C = max(2, int(ctx))
        heads = max(1, int(n_heads))
        if D % heads:
            heads = 1
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        s = 0.08
        self.E = _rand_mat(V, D, s, rng)
        self.P = _rand_mat(C, D, s, rng)
        nL = max(1, int(n_layers))
        ff = max(0, int(d_ff))
        self.norm = "rms" if str(norm).lower() == "rms" else "ln"
        self.ffn_kind = "swiglu" if str(ffn_kind).lower() == "swiglu" else "gelu"
        self.layers: List[TransformerBlock] = [
            TransformerBlock(D, ff, rng, s, norm=self.norm, ffn_kind=self.ffn_kind)
            for _ in range(nL)
        ]
        self.Wout = _rand_mat(V, D, s, rng)
        self.bout = zeros(V)
        self.tied = False
        self.dim = D
        self.ctx = C
        self.n_heads = heads
        self.n_layers = nL
        self.d_ff = ff
        self.fitted = 0
        self.steps = 0
        self.device = "cpu"
        self.requested = "cpu"
        self.resident = False
        self._accel = None

    @property
    def V(self) -> int:
        return len(self.E)

    @property
    def Wq(self) -> List[List[float]]:
        return self.layers[0].Wq

    @Wq.setter
    def Wq(self, v: List[List[float]]) -> None:
        self.layers[0].Wq = v

    @property
    def Wk(self) -> List[List[float]]:
        return self.layers[0].Wk

    @Wk.setter
    def Wk(self, v: List[List[float]]) -> None:
        self.layers[0].Wk = v

    @property
    def Wv(self) -> List[List[float]]:
        return self.layers[0].Wv

    @Wv.setter
    def Wv(self, v: List[List[float]]) -> None:
        self.layers[0].Wv = v

    @property
    def Wo(self) -> List[List[float]]:
        return self.layers[0].Wo

    @Wo.setter
    def Wo(self, v: List[List[float]]) -> None:
        self.layers[0].Wo = v

    @property
    def W1(self) -> List[List[float]]:
        return self.layers[0].W1

    @W1.setter
    def W1(self, v: List[List[float]]) -> None:
        self.layers[0].W1 = v

    @property
    def W2(self) -> List[List[float]]:
        return self.layers[0].W2

    @W2.setter
    def W2(self, v: List[List[float]]) -> None:
        self.layers[0].W2 = v

    @property
    def b1(self) -> List[float]:
        return self.layers[0].b1

    @b1.setter
    def b1(self, v: List[float]) -> None:
        self.layers[0].b1 = v

    @property
    def b2(self) -> List[float]:
        return self.layers[0].b2

    @b2.setter
    def b2(self, v: List[float]) -> None:
        self.layers[0].b2 = v

    def _id(self, tok: str) -> int:
        return int(self.stoi.get(tok, self.unk))

    def _encode(self, ids: Sequence[int]) -> List[List[float]]:
        X: List[List[float]] = []
        for t, idx in enumerate(ids):
            X.append(add(self.E[idx], self.P[t]))
        return X

    def to(self, device: str = "cpu") -> "TinyTransformer":
        """Bind a device. CUDA if torch can see a GPU; else CPU. Never throws.

        When torch exists the weights pin on the bound device (GPU-resident
        if cuda, otherwise torch-cpu). Python lists catch up on snapshot().
        """
        from skeleton.cortex.device import resolve
        info = resolve(device)
        self.requested = str(info.get("requested") or device)
        self.device = str(info.get("actual") or "cpu")
        if self._accel is not None:
            try:
                self._accel.sync()
            except Exception:
                pass
        self._accel = None
        self.resident = False
        pin = bool(info.get("torch")) and self.requested != "cpu"
        if pin:
            try:
                from skeleton.cortex.torch_lm import TorchAccel
                self._accel = TorchAccel(self, device=self.device)
                self._accel.pin()
                self.device = self._accel.device_name
                self.resident = True
            except Exception:
                self._accel = None
                self.device = "cpu"
                self.resident = False
        return self

    def _forward(self, ids: Sequence[int]):
        H = self._encode(ids)
        caches = []
        for layer in self.layers:
            H, cache = layer.forward(H, self.n_heads)
            caches.append(cache)
        return H, caches

    def _block(self, ids: Sequence[int]):
        """Compat: last-layer cache shaped like the old 1-layer tuple."""
        H, caches = self._forward(ids)
        c = caches[-1] if caches else {}
        U = c.get("U") or H
        z_seq = c.get("z") or []
        z = z_seq[-1] if z_seq else []
        return (
            c.get("X") or [],
            c.get("Q") or [],
            c.get("K") or [],
            c.get("V") or [],
            c.get("C") or [],
            c.get("As") or [],
            U[-1] if U else [],
            z,
            H[-1] if H else [],
        )

    def _logits(self, ids: Sequence[int]) -> List[float]:
        if self._accel is not None:
            try:
                return list(self._accel.logits(ids))
            except Exception:
                self._accel = None
                self.resident = False
        H, _ = self._forward(ids)
        y = H[-1] if H else zeros(self.dim)
        return self._unembed(y)

    def _step(self, idx: int, cache: KVCache) -> List[float]:
        """Extend the cache by one id. RoPE position is window-relative."""
        t = len(cache.tokens)
        ei = int(idx) if 0 <= int(idx) < self.V else self.unk
        x = add(self.E[ei], self.P[min(t, self.ctx - 1)])
        for li, layer in enumerate(self.layers):
            x = layer.step(x, cache.K[li], cache.V[li], self.n_heads, t)
        cache.tokens.append(ei)
        return self._unembed(x)

    def _logits_window(self, ids: Sequence[int], cache: Optional[KVCache] = None) -> List[float]:
        window = list(ids[-self.ctx:] or [self.unk])
        if cache is None:
            return self._logits(window)
        if cache.primed_for(window):
            return self._step(window[-1], cache)
        cache.reset()
        for idx in window[:-1]:
            self._step(idx, cache)
        return self._step(window[-1], cache)

    def hidden(self, prefix: str) -> List[float]:
        """Last-position context after the stacked residual stream."""
        seq = self.hidden_seq(prefix)
        return list(seq[-1]) if seq else zeros(self.dim)

    def hidden_seq(self, prefix: str) -> List[List[float]]:
        """Full residual stream. Callosum reads this, not just the last token."""
        ids = [self._id(t) for t in tokens(prefix)] or [self.unk]
        ids = ids[-self.ctx:]
        if self._accel is not None:
            try:
                h = list(self._accel.hidden(ids))
                H, _ = self._forward(ids)
                return [list(row) for row in H] if H else [h]
            except Exception:
                self._accel = None
                self.resident = False
        H, _ = self._forward(ids)
        return [list(row) for row in H] if H else [zeros(self.dim)]

    def weights_last(self, prefix: str) -> List[float]:
        ids = [self._id(t) for t in tokens(prefix)] or [self.unk]
        ids = ids[-self.ctx:]
        _H, caches = self._forward(ids)
        As = (caches[-1].get("As") if caches else None) or []
        A0 = As[0] if As else []
        return list(A0[-1]) if A0 else []

    def token_prob(self, prefix: str, tok: str) -> float:
        ids = [self._id(t) for t in tokens(prefix)] or [self.unk]
        ids = ids[-self.ctx:]
        p = softmax(self._logits(ids))
        return float(p[self._id(tok)])

    def _sgd(self, ids: List[int], target: int, lr: float) -> float:
        """Last-token CE through stacked Pre-LN blocks. CPU or bound accel."""
        if self._accel is not None:
            try:
                return float(self._accel.sgd(ids, target, lr))
            except Exception:
                self._accel = None
                self.resident = False
        n = len(ids)
        D = self.dim
        H, caches = self._forward(ids)
        y = H[-1] if H else zeros(D)
        logits = self._unembed(y)
        p = softmax(logits)
        loss = -math.log(max(p[target], 1e-12))
        dlog = [p[v] - (1.0 if v == target else 0.0) for v in range(self.V)]
        g2 = math.sqrt(sum(x * x for x in dlog))
        if g2 > 5.0:
            s = 5.0 / g2
            dlog = [x * s for x in dlog]

        W = self.E if self.tied else self.Wout
        dy = matvec_T(W, dlog)
        add_outer(W, dlog, y, -lr)
        for v in range(self.V):
            self.bout[v] -= lr * dlog[v]

        dH = [zeros(D) for _ in range(n)]
        dH[-1] = dy
        for layer, cache in zip(reversed(self.layers), reversed(caches)):
            dH = layer.backward(dH, cache, lr)

        for t in range(n):
            g = math.sqrt(sum(x * x for x in dH[t]))
            if g > 2.0:
                s = 2.0 / g
                dH[t] = [x * s for x in dH[t]]
        for t, idx in enumerate(ids):
            dx = dH[t]
            for d in range(D):
                self.E[idx][d] -= lr * dx[d]
                self.P[t][d] -= lr * dx[d]
        self.steps += 1
        return loss

    def fit(self, texts: Iterable[str], *, lr: float = 0.04, schedule: str = "const") -> int:
        corpus = [t for t in texts if t]
        windows: List[Tuple[List[int], int]] = []
        for raw in corpus:
            body = tokens(raw)
            if len(body) < 2:
                continue
            ids = [self._id(t) for t in body]
            for i in range(1, len(ids)):
                windows.append((ids[max(0, i - self.ctx):i], ids[i]))
        total = max(1, len(windows))
        n = 0
        for step, (window, target) in enumerate(windows):
            eta = cosine_lr(step, total, base=lr) if schedule == "cosine" else lr
            self._sgd(window, target, eta)
            n += 1
        self.fitted += len(corpus)
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
        """Next-token decode on the bound device (CPU default, CUDA if harnessed)."""
        if self._accel is not None:
            try:
                return str(self._accel.decode(prefix, n=n, seed=seed))
            except Exception:
                self._accel = None
                self.resident = False
        return " ".join(self.generate(prefix, n=n, seed=seed))

    def _unembed(self, y: Sequence[float]) -> List[float]:
        W = self.E if self.tied else self.Wout
        return add(matvec(W, list(y)), self.bout)

    def tie(self) -> "TinyTransformer":
        """Wout is E. Birth of the token mouth as its own unembed."""
        self.Wout = self.E
        self.tied = True
        return self

    def untie(self) -> "TinyTransformer":
        if self.tied:
            self.Wout = [list(row) for row in self.E]
            self.tied = False
        return self

    def from_bpe(self, text: str, bpe=None) -> List[int]:
        """Token ids from the BPE mouth. Unknown pieces fall to word _id / UNK."""
        if bpe is None:
            bpe = getattr(self, "bpe", None)
        if bpe is None or not hasattr(bpe, "encode_pieces"):
            return [self._id(t) for t in tokens(text)] or [self.unk]
        ids: List[int] = []
        for piece in bpe.encode_pieces(text or ""):
            if piece in self.stoi:
                ids.append(self._id(piece))
            else:
                ids.append(self.unk)
        return ids or [self.unk]

    def beam(self, prefix: str, *, n: int = 8, width: int = 4) -> Dict[str, Any]:
        from skeleton.cortex.beam import beam_search
        return beam_search(self, prefix, n=n, width=width)

    def accumulate(self, texts: Iterable[str], *, k: int = 4, lr: float = 0.04) -> Dict[str, Any]:
        from skeleton.cortex.accum import accumulate_fit
        return accumulate_fit(self, texts, k=k, lr=lr)

    def attach_lora(self, *, rank: int = 2, alpha: float = 4.0, seed: int = 0) -> Dict[str, Any]:
        from skeleton.cortex.lora import LoRABank
        return LoRABank(rank=rank, alpha=alpha, seed=seed).attach(self)

    def merge_lora(self) -> Dict[str, Any]:
        bank = getattr(self, "lora", None)
        return {"merged": []} if bank is None else bank.merge(self)

    def generate(
        self,
        prefix: str | Sequence[str],
        n: int = 12,
        *,
        seed: int = 0,
        temperature: float = 1.0,
        top_k: int = 0,
        top_p: float = 1.0,
        use_cache: bool = True,
    ) -> Tuple[str, ...]:
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        if isinstance(prefix, str):
            body = list(tokens(prefix))
        else:
            body = [str(t) for t in prefix]
        ids = [self._id(t) for t in body] or [self.unk]
        out = list(ids)
        cache = KVCache(self.n_layers, self.ctx) if use_cache else None
        for _ in range(max(1, n)):
            window = out[-self.ctx:]
            logits = self._logits_window(window, cache)
            nxt = sample_logits(
                logits, rng, temperature=temperature, top_k=top_k, top_p=top_p,
            )
            out.append(int(nxt))
        return tuple(self.itos[i] if 0 <= i < len(self.itos) else UNK for i in out[:n])

    def snapshot(self) -> Dict[str, Any]:
        if self._accel is not None:
            try:
                self._accel.sync()
            except Exception:
                pass
        L0 = self.layers[0]
        return {
            "dim": self.dim,
            "ctx": self.ctx,
            "n_heads": self.n_heads,
            "n_layers": self.n_layers,
            "d_ff": self.d_ff,
            "device": self.device,
            "resident": bool(self.resident),
            "fitted": self.fitted,
            "steps": self.steps,
            "tied": bool(self.tied),
            "norm": self.norm,
            "ffn_kind": self.ffn_kind,
            "itos": list(self.itos),
            "E": _copy_mat(self.E),
            "P": _copy_mat(self.P),
            "Wq": _copy_mat(L0.Wq),
            "Wk": _copy_mat(L0.Wk),
            "Wv": _copy_mat(L0.Wv),
            "Wo": _copy_mat(L0.Wo),
            "Wout": _copy_mat(self.Wout),
            "bout": list(self.bout),
            "W1": _copy_mat(L0.W1) if L0.W1 else [],
            "b1": list(L0.b1) if L0.b1 else [],
            "W2": _copy_mat(L0.W2) if L0.W2 else [],
            "b2": list(L0.b2) if L0.b2 else [],
            "layers": [L.snapshot() for L in self.layers],
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "TinyTransformer":
        itos = list((data or {}).get("itos") or [UNK])
        n_layers = int((data or {}).get("n_layers") or 1)
        lm = cls(
            vocab=[t for t in itos if t != UNK],
            dim=int((data or {}).get("dim") or 8),
            ctx=int((data or {}).get("ctx") or 6),
            seed=0,
            n_heads=int((data or {}).get("n_heads") or 1),
            n_layers=n_layers,
            d_ff=int((data or {}).get("d_ff") or 0),
            norm=str((data or {}).get("norm") or "ln"),
            ffn_kind=str((data or {}).get("ffn_kind") or "gelu"),
        )
        lm.itos = itos
        lm.stoi = {t: i for i, t in enumerate(itos)}
        def _m(key: str, cur: List[List[float]]) -> List[List[float]]:
            raw = (data or {}).get(key)
            return [list(map(float, row)) for row in raw] if raw else cur
        lm.E = _m("E", lm.E)
        lm.P = _m("P", lm.P)
        lm.Wout = _m("Wout", lm.Wout)
        if (data or {}).get("tied"):
            lm.tie()
        b = (data or {}).get("bout")
        if b:
            lm.bout = [float(x) for x in b]
        raw_layers = (data or {}).get("layers")
        if raw_layers:
            lm.layers = [
                TransformerBlock.from_snapshot(blob, dim=lm.dim, d_ff=lm.d_ff)
                for blob in raw_layers
            ]
            lm.n_layers = max(1, len(lm.layers))
        else:
            L0 = lm.layers[0]
            L0.Wq = _m("Wq", L0.Wq)
            L0.Wk = _m("Wk", L0.Wk)
            L0.Wv = _m("Wv", L0.Wv)
            L0.Wo = _m("Wo", L0.Wo)
            L0.W1 = _m("W1", L0.W1)
            L0.W2 = _m("W2", L0.W2)
            if (data or {}).get("b1"):
                L0.b1 = [float(x) for x in data["b1"]]
            if (data or {}).get("b2"):
                L0.b2 = [float(x) for x in data["b2"]]
        lm.fitted = int((data or {}).get("fitted") or 0)
        lm.steps = int((data or {}).get("steps") or 0)
        lm.device = str((data or {}).get("device") or "cpu")
        if lm.device == "cuda":
            lm.device = "cpu"
            lm.requested = "cuda"
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
