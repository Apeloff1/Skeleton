"""Tiny neural language model — weights, gradient, not a count table.

Skip-gram next-token softmax. Embedding E (V×D) and output W (D×V)
are the model. SGD on GameForge tokens. Perplexity on held-out
in-domain text must drop. Snapshot/restore is interchange: acquire
copies a net, not a prompt.

Pure Python. No numpy, no torch. Dim 12. This is the small/medium
net the ports were waiting for — CI GameForge has no extra deps.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from skeleton.cortex.port import Thought, fingerprint, tokens

UNK = "__unk__"


def _zeros(n: int) -> List[float]:
    return [0.0] * n


def _rand_mat(rows: int, cols: int, scale: float, rng: random.Random) -> List[List[float]]:
    return [[rng.gauss(0.0, scale) for _ in range(cols)] for _ in range(rows)]


def _softmax(logits: List[float]) -> List[float]:
    m = max(logits) if logits else 0.0
    e = [math.exp(x - m) for x in logits]
    s = sum(e) or 1.0
    return [x / s for x in e]


class NeuralLM:
    """Bigram neural LM. E[prev] → softmax(W, b) over next token."""

    def __init__(
        self,
        vocab: Iterable[str] | None = None,
        *,
        dim: int = 12,
        seed: int = 0,
    ) -> None:
        itos = [UNK] + sorted({str(t) for t in (vocab or ()) if t and t != UNK})
        self.itos: List[str] = itos
        self.stoi: Dict[str, int] = {t: i for i, t in enumerate(itos)}
        self.unk = 0
        V = max(2, len(itos))
        D = max(4, int(dim))
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        scale = 0.08
        self.E = _rand_mat(V, D, scale, rng)
        self.W = _rand_mat(D, V, scale, rng)
        self.b = _zeros(V)
        self.dim = D
        self.fitted = 0
        self.steps = 0

    @property
    def V(self) -> int:
        return len(self.E)

    def _id(self, tok: str) -> int:
        return int(self.stoi.get(tok, self.unk))

    def _logits(self, i: int) -> List[float]:
        h = self.E[i]
        D = self.dim
        V = self.V
        out = list(self.b)
        for d in range(D):
            hd = h[d]
            row = self.W[d]
            for v in range(V):
                out[v] += hd * row[v]
        return out

    def _sgd(self, i: int, j: int, lr: float) -> float:
        logits = self._logits(i)
        p = _softmax(logits)
        loss = -math.log(max(p[j], 1e-12))
        dlog = [p[v] - (1.0 if v == j else 0.0) for v in range(self.V)]
        h = self.E[i]
        D = self.dim
        V = self.V
        dE = _zeros(D)
        for d in range(D):
            acc = 0.0
            row = self.W[d]
            hd = h[d]
            for v in range(V):
                g = dlog[v]
                acc += row[v] * g
                row[v] -= lr * hd * g
            dE[d] = acc
        for v in range(V):
            self.b[v] -= lr * dlog[v]
        for d in range(D):
            h[d] -= lr * dE[d]
        self.steps += 1
        return loss

    def fit(self, texts: Iterable[str], *, lr: float = 0.08) -> int:
        n = 0
        for raw in texts:
            body = tokens(raw)
            if len(body) < 2:
                continue
            ids = [self._id(t) for t in body]
            for a, b in zip(ids, ids[1:]):
                self._sgd(a, b, lr)
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
        for a, b in zip(ids, ids[1:]):
            p = _softmax(self._logits(a))
            lp += math.log(max(p[b], 1e-12))
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

    def generate(self, prefix: str | Sequence[str], n: int = 12, *, seed: int = 0) -> Tuple[str, ...]:
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        if isinstance(prefix, str):
            body = list(tokens(prefix))
        else:
            body = [str(t) for t in prefix]
        ids = [self._id(t) for t in body] or [self.unk]
        out = list(ids)
        for _ in range(max(1, n)):
            p = _softmax(self._logits(out[-1]))
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
            "fitted": self.fitted,
            "steps": self.steps,
            "itos": list(self.itos),
            "E": [list(row) for row in self.E],
            "W": [list(row) for row in self.W],
            "b": list(self.b),
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "NeuralLM":
        itos = list((data or {}).get("itos") or [UNK])
        lm = cls(vocab=[t for t in itos if t != UNK], dim=int((data or {}).get("dim") or 12), seed=0)
        lm.itos = itos
        lm.stoi = {t: i for i, t in enumerate(itos)}
        E = (data or {}).get("E")
        W = (data or {}).get("W")
        b = (data or {}).get("b")
        if E:
            lm.E = [list(map(float, row)) for row in E]
        if W:
            lm.W = [list(map(float, row)) for row in W]
        if b:
            lm.b = [float(x) for x in b]
        lm.fitted = int((data or {}).get("fitted") or 0)
        lm.steps = int((data or {}).get("steps") or 0)
        return lm


class NeuralBackend:
    """ModelPort wrapping a NeuralLM. Interchangeable with Echo / n-gram / local."""

    def __init__(self, lm: NeuralLM, *, slot: str, name: str = "neural") -> None:
        self.lm = lm
        self.slot = slot
        self.name = name
        self.scale = "small" if lm.dim <= 12 else "medium"

    def fit(self, text: str) -> int:
        return self.lm.fit([text])

    def snapshot(self) -> Dict[str, Any]:
        snap = self.lm.snapshot()
        snap["slot"] = self.slot
        snap["name"] = self.name
        snap["kind"] = "neural"
        return snap

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], *, slot: str | None = None) -> "NeuralBackend":
        lm = NeuralLM.from_snapshot(data or {})
        sl = slot or str((data or {}).get("slot") or "pfc")
        return cls(lm, slot=sl, name=str((data or {}).get("name") or "imported-neural"))

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        text = stimulus or ""
        if self.slot == "pfc":
            from skeleton.cortex.pfc import _VETO
            if any(v in text.lower() for v in _VETO) or not text.strip():
                return Thought(
                    slot="pfc", kind="plan",
                    text="INHIBIT: PFC veto. Not a builder act.",
                    confidence=0.95,
                    tags=("veto", "boilerplate", "small", "neural"),
                    numbers=(0.0, 1.0),
                )
        seed = int(fingerprint(text)[:8], 16) if text else 0
        gen = " ".join(self.lm.generate(text, n=16, seed=seed))
        nums: Tuple[float, ...] = (float(self.lm.dim), float(self.lm.steps))
        tags: Tuple[str, ...] = ("neural", self.scale, self.slot)
        if self.slot == "left":
            from skeleton.cortex.hemispheres import LeftHemisphere
            teacher = LeftHemisphere().think(text, context)
            return Thought(
                slot="left", kind="analytic",
                text=f"{teacher.text} | {gen}",
                confidence=teacher.confidence,
                tags=teacher.tags + ("neural",),
                numbers=teacher.numbers,
            )
        if self.slot == "right":
            from skeleton.cortex.hemispheres import RightHemisphere
            teacher = RightHemisphere().think(text, context)
            return Thought(
                slot="right", kind="gestalt",
                text=f"{teacher.text} / {gen}",
                confidence=teacher.confidence,
                tags=teacher.tags + ("neural",),
                numbers=teacher.numbers,
            )
        if self.slot == "midbrain":
            from skeleton.cortex.midbrain import _weights
            arousal, lw, rw = _weights(text)
            return Thought(
                slot="midbrain", kind="route",
                text=f"COORD {gen}",
                confidence=0.80,
                tags=("route", "coordinator", "medium", "neural")
                + (("left",) if lw >= 0.25 else ())
                + (("right",) if rw >= 0.25 else ()),
                numbers=(arousal, lw, rw),
            )
        return Thought(
            slot=self.slot, kind="plan",
            text=gen or text[:160],
            confidence=0.68,
            tags=tags,
            numbers=nums,
        )
