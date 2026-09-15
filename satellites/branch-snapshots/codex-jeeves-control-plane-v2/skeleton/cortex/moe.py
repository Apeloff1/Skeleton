"""Mixture of Experts — Jeeves acquires the MODELS, not the prompts.

Four experts (pfc / midbrain / left / right) sit on the neo residual.
Each is a residual adapter plus the slot's specialist head. A softmax
router gates them. acquire(slot) stamps the expert as copied from that
tract; distill pulls the adapter toward the teacher hidden; forward is
the gated mix plus residual. predict_* is how neo authors mix/bias/
route/veto/policy without firing the teacher. Fingerprint is the merkle
of the expert snapshots — hive interchange of the guts, not the tape.
Pure Python. CI has no numpy.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from skeleton.cortex.attn import add, add_outer, dot, matvec, matvec_T, softmax, zeros
from skeleton.cortex.heads import (
    BiasHead,
    NumericHead,
    PolicyHead,
    RouteHead,
    VetoHead,
    clamp_mix,
    head_from_snapshot,
    mse,
)
from skeleton.cortex.port import SLOTS

Vec = List[float]
Mat = List[List[float]]
Mix = Tuple[int, int, int]

MIN_FITTED = 6


def _rand_mat(rows: int, cols: int, scale_: float, rng: random.Random) -> Mat:
    return [[rng.gauss(0.0, scale_) for _ in range(cols)] for _ in range(rows)]


def _copy_mat(m: Mat) -> Mat:
    return [list(row) for row in m]


def _tanh(xs: Sequence[float]) -> Vec:
    return [math.tanh(x) for x in xs]


class Router:
    """Softmax over four experts given a hidden."""

    def __init__(self, dim: int, n: int = 4, *, seed: int = 19) -> None:
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        self.W: Mat = _rand_mat(n, dim, 0.08, rng)
        self.b: Vec = zeros(n)
        self.dim = dim
        self.n = n
        self.steps = 0

    def gate(self, h: Sequence[float]) -> Vec:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        logits = [dot(self.W[i], v) + self.b[i] for i in range(self.n)]
        return softmax(logits)

    def credit(self, index: int, *, lr: float = 0.02) -> None:
        if 0 <= index < self.n:
            self.b[index] += lr
            self.steps += 1

    def snapshot(self) -> Dict[str, Any]:
        return {"W": _copy_mat(self.W), "b": list(self.b), "dim": self.dim, "n": self.n, "steps": self.steps}

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "Router":
        r = cls(dim=int((data or {}).get("dim") or 8), n=int((data or {}).get("n") or 4), seed=0)
        raw = (data or {}).get("W")
        if raw:
            r.W = [list(map(float, row)) for row in raw]
        b = (data or {}).get("b")
        if b:
            r.b = [float(x) for x in b]
        r.steps = int((data or {}).get("steps") or 0)
        return r


class Expert:
    """Residual adapter + specialist head (+ optional aux head)."""

    def __init__(self, slot: str, dim: int, *, seed: int = 0) -> None:
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        D = max(4, int(dim))
        self.slot = slot
        self.dim = D
        self.W: Mat = _rand_mat(D, D, 0.05, rng)
        self.b: Vec = zeros(D)
        self.head = _head_for(slot, D, seed)
        self.aux = PolicyHead(dim=D, seed=seed + 31) if slot == "pfc" else None
        self.acquired = 0
        self.distills = 0

    def project(self, h: Sequence[float]) -> Vec:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        raw = [dot(self.W[i], v) + self.b[i] for i in range(self.dim)]
        return add(v, _tanh(raw))

    def distill(self, h: Sequence[float], teacher: Sequence[float], *, lr: float = 0.05) -> float:
        """Adapter residual toward teacher hidden. MSE on the projected vector."""
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        t = list(teacher)[: self.dim] + [0.0] * max(0, self.dim - len(teacher))
        raw = [dot(self.W[i], v) + self.b[i] for i in range(self.dim)]
        th = _tanh(raw)
        pred = add(v, th)
        loss = mse(pred, t)
        n = float(self.dim)
        dpred = [(2.0 / n) * (pred[i] - t[i]) for i in range(self.dim)]
        draw = [dpred[i] * (1.0 - th[i] * th[i]) for i in range(self.dim)]
        add_outer(self.W, draw, v, -lr)
        for i in range(self.dim):
            self.b[i] -= lr * draw[i]
        self.distills += 1
        return loss

    def snapshot(self) -> Dict[str, Any]:
        return {
            "slot": self.slot, "dim": self.dim,
            "W": _copy_mat(self.W), "b": list(self.b),
            "head": self.head.snapshot(),
            "aux": None if self.aux is None else self.aux.snapshot(),
            "acquired": self.acquired, "distills": self.distills,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "Expert":
        slot = str((data or {}).get("slot") or "left")
        dim = int((data or {}).get("dim") or 8)
        ex = cls(slot, dim, seed=0)
        raw = (data or {}).get("W")
        if raw:
            ex.W = [list(map(float, row)) for row in raw]
        b = (data or {}).get("b")
        if b:
            ex.b = [float(x) for x in b]
        if (data or {}).get("head"):
            ex.head = head_from_snapshot(data["head"])
        if (data or {}).get("aux"):
            ex.aux = PolicyHead.from_snapshot(data["aux"])
        ex.acquired = int((data or {}).get("acquired") or 0)
        ex.distills = int((data or {}).get("distills") or 0)
        return ex


def _head_for(slot: str, dim: int, seed: int):
    if slot == "left":
        return NumericHead(dim=dim, seed=seed)
    if slot == "right":
        return BiasHead(dim=dim, seed=seed)
    if slot == "midbrain":
        return RouteHead(dim=dim, seed=seed)
    return VetoHead(dim=dim, seed=seed)


class ExpertBank:
    """The own-system of MODELS. Four experts, one router, one residual."""

    def __init__(self, dim: int = 8, *, seed: int = 19) -> None:
        D = max(4, int(dim))
        self.dim = D
        self.experts: Dict[str, Expert] = {
            s: Expert(s, D, seed=seed + i * 17) for i, s in enumerate(SLOTS)
        }
        self.router = Router(D, n=len(SLOTS), seed=seed)
        self.forwards = 0

    def acquire(self, slot: str) -> int:
        slot = (slot or "").lower()
        ex = self.experts.get(slot)
        if ex is None:
            return 0
        ex.acquired += 1
        return ex.acquired

    def forward(self, h: Sequence[float]) -> Tuple[Vec, Vec]:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        gates = self.router.gate(v)
        mixed = zeros(self.dim)
        for i, slot in enumerate(SLOTS):
            p = self.experts[slot].project(v)
            g = gates[i]
            for d in range(self.dim):
                mixed[d] += g * p[d]
        self.forwards += 1
        return mixed, gates

    def predict_mix(self, h: Sequence[float]) -> Optional[Mix]:
        ex = self.experts["left"]
        if int(getattr(ex.head, "fitted", 0) or 0) < MIN_FITTED:
            return None
        mixed, _ = self.forward(h)
        return ex.head.predict(mixed)

    def predict_bias(self, h: Sequence[float]) -> Optional[str]:
        ex = self.experts["right"]
        if int(getattr(ex.head, "fitted", 0) or 0) < MIN_FITTED:
            return None
        mixed, _ = self.forward(h)
        return ex.head.predict(mixed)

    def predict_route(self, h: Sequence[float]) -> Optional[Tuple[float, float, float]]:
        ex = self.experts["midbrain"]
        if int(getattr(ex.head, "fitted", 0) or 0) < MIN_FITTED:
            return None
        mixed, _ = self.forward(h)
        return ex.head.predict(mixed)

    def predict_veto(self, h: Sequence[float]) -> Optional[bool]:
        ex = self.experts["pfc"]
        if int(getattr(ex.head, "fitted", 0) or 0) < MIN_FITTED:
            return None
        mixed, _ = self.forward(h)
        return bool(ex.head.predict(mixed))

    def predict_policy(self, h: Sequence[float]) -> Optional[Tuple[int, int]]:
        ex = self.experts["pfc"]
        aux = ex.aux
        if aux is None or int(getattr(aux, "fitted", 0) or 0) < MIN_FITTED:
            return None
        mixed, _ = self.forward(h)
        return aux.predict(mixed)

    def credit(self, slot: str, *, lr: float = 0.02) -> None:
        if slot in SLOTS:
            self.router.credit(SLOTS.index(slot), lr=lr)

    def fingerprint(self) -> str:
        guts = {
            "experts": {
                s: {
                    "W": _copy_mat(ex.W),
                    "b": list(ex.b),
                    "head": ex.head.snapshot(),
                    "aux": None if ex.aux is None else ex.aux.snapshot(),
                }
                for s, ex in self.experts.items()
            },
            "router": {"W": _copy_mat(self.router.W), "b": list(self.router.b)},
        }
        blob = json.dumps(guts, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def snapshot(self) -> Dict[str, Any]:
        return {
            "dim": self.dim,
            "experts": {s: ex.snapshot() for s, ex in self.experts.items()},
            "router": self.router.snapshot(),
            "forwards": self.forwards,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "ExpertBank":
        bank = cls(dim=int((data or {}).get("dim") or 8), seed=0)
        for s, blob in ((data or {}).get("experts") or {}).items():
            bank.experts[str(s)] = Expert.from_snapshot(blob)
        if (data or {}).get("router"):
            bank.router = Router.from_snapshot(data["router"])
        bank.forwards = int((data or {}).get("forwards") or 0)
        return bank

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dim": self.dim,
            "forwards": self.forwards,
            "fingerprint": self.fingerprint(),
            "experts": {
                s: {
                    "acquired": ex.acquired,
                    "distills": ex.distills,
                    "head_fitted": int(getattr(ex.head, "fitted", 0) or 0),
                    "head_kind": getattr(ex.head, "kind", ""),
                    "aux_fitted": int(getattr(ex.aux, "fitted", 0) or 0) if ex.aux else 0,
                }
                for s, ex in self.experts.items()
            },
            "router_steps": self.router.steps,
        }
