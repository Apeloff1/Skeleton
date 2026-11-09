"""Specialist heads — the tracts grow output maps, not just text.

Left owns a numeric mix head (trash, elite, boss). Right owns a bias
classifier. Midbrain owns a route head (arousal, left, right). PFC owns
veto and policy. Every head is a linear map on the neo residual stream,
SGD, snapshot/restore. Teacher thoughts are the labels; after fit the
neo emits the same numbers without firing the teacher. Pure Python.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from skeleton.cortex.attn import add_outer, dot, matvec, matvec_T, softmax, zeros
from skeleton.cortex.own import BIASES

Vec = List[float]
Mat = List[List[float]]
Mix = Tuple[int, int, int]


def _sig(x: float) -> float:
    if x >= 20.0:
        return 1.0
    if x <= -20.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _dsig(s: float) -> float:
    return s * (1.0 - s)


def _rand_mat(rows: int, cols: int, scale: float, rng: random.Random) -> Mat:
    return [[rng.gauss(0.0, scale) for _ in range(cols)] for _ in range(rows)]


def _copy_mat(m: Mat) -> Mat:
    return [list(row) for row in m]


def mse(a: Sequence[float], b: Sequence[float]) -> float:
    n = max(1, min(len(a), len(b)))
    return sum((float(a[i]) - float(b[i])) ** 2 for i in range(n)) / n


def kl_div(p: Sequence[float], q: Sequence[float]) -> float:
    acc = 0.0
    for pi, qi in zip(p, q):
        acc += float(pi) * math.log(max(float(pi), 1e-12) / max(float(qi), 1e-12))
    return acc


def clamp_mix(t: float, e: float, b: float) -> Mix:
    return (
        max(1, min(6, int(round(t)))),
        max(0, min(3, int(round(e)))),
        max(0, min(1, int(round(b)))),
    )


class NumericHead:
    """Hidden → (trash ∈ [1,6], elite ∈ [0,3], boss ∈ [0,1]). Sigmoid scales."""

    kind = "numeric"

    def __init__(self, dim: int = 8, *, seed: int = 11) -> None:
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        D = max(2, int(dim))
        self.W: Mat = _rand_mat(3, D, 0.08, rng)
        self.b: Vec = [0.0, 0.0, 0.0]
        self.dim = D
        self.fitted = 0
        self.steps = 0
        self.last_loss = 0.0

    def raw(self, h: Sequence[float]) -> Vec:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        return [dot(self.W[i], v) + self.b[i] for i in range(3)]

    def activate(self, raw: Sequence[float]) -> Vec:
        s0, s1, s2 = _sig(raw[0]), _sig(raw[1]), _sig(raw[2])
        return [1.0 + 5.0 * s0, 3.0 * s1, s2]

    def predict(self, h: Sequence[float]) -> Mix:
        a = self.activate(self.raw(h))
        return clamp_mix(a[0], a[1], a[2])

    def loss(self, h: Sequence[float], target: Sequence[float]) -> float:
        pred = self.activate(self.raw(h))
        tgt = [float(target[0]), float(target[1]), float(target[2])]
        return mse(pred, tgt)

    def step(self, h: Sequence[float], target: Sequence[float], *, lr: float = 0.12) -> float:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        raw = self.raw(v)
        s = [_sig(raw[0]), _sig(raw[1]), _sig(raw[2])]
        pred = [1.0 + 5.0 * s[0], 3.0 * s[1], s[2]]
        tgt = [float(target[0]), float(target[1]), float(target[2])]
        loss = mse(pred, tgt)
        scales = (5.0, 3.0, 1.0)
        dlog = [0.0, 0.0, 0.0]
        for i in range(3):
            dpred = (2.0 / 3.0) * (pred[i] - tgt[i])
            dlog[i] = dpred * scales[i] * _dsig(s[i])
        add_outer(self.W, dlog, v, -lr)
        for i in range(3):
            self.b[i] -= lr * dlog[i]
        self.steps += 1
        self.fitted += 1
        self.last_loss = loss
        return loss

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "dim": self.dim, "fitted": self.fitted,
            "steps": self.steps, "W": _copy_mat(self.W), "b": list(self.b),
            "last_loss": self.last_loss,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "NumericHead":
        h = cls(dim=int((data or {}).get("dim") or 8), seed=0)
        raw = (data or {}).get("W")
        if raw:
            h.W = [list(map(float, row)) for row in raw]
        b = (data or {}).get("b")
        if b:
            h.b = [float(x) for x in b]
        h.fitted = int((data or {}).get("fitted") or 0)
        h.steps = int((data or {}).get("steps") or 0)
        h.last_loss = float((data or {}).get("last_loss") or 0.0)
        return h


class BiasHead:
    """Hidden → {loot, combat, heat, balanced}. Softmax CE."""

    kind = "bias"
    labels: Tuple[str, ...] = BIASES

    def __init__(self, dim: int = 8, *, seed: int = 13) -> None:
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        D = max(2, int(dim))
        C = len(self.labels)
        self.W: Mat = _rand_mat(C, D, 0.08, rng)
        self.b: Vec = zeros(C)
        self.dim = D
        self.fitted = 0
        self.steps = 0
        self.last_loss = 0.0

    def logits(self, h: Sequence[float]) -> Vec:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        return [dot(self.W[i], v) + self.b[i] for i in range(len(self.labels))]

    def probs(self, h: Sequence[float]) -> Vec:
        return softmax(self.logits(h))

    def predict(self, h: Sequence[float]) -> str:
        p = self.probs(h)
        return self.labels[max(range(len(p)), key=lambda i: p[i])]

    def loss(self, h: Sequence[float], label: str) -> float:
        p = self.probs(h)
        i = self._idx(label)
        return -math.log(max(p[i], 1e-12))

    def step(self, h: Sequence[float], label: str, *, lr: float = 0.12) -> float:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        p = self.probs(v)
        i = self._idx(label)
        loss = -math.log(max(p[i], 1e-12))
        dlog = [p[k] - (1.0 if k == i else 0.0) for k in range(len(p))]
        add_outer(self.W, dlog, v, -lr)
        for k, g in enumerate(dlog):
            self.b[k] -= lr * g
        self.steps += 1
        self.fitted += 1
        self.last_loss = loss
        return loss

    def distill_kl(self, h: Sequence[float], teacher: Sequence[float], *, lr: float = 0.08) -> float:
        """Match a teacher distribution over the four biases."""
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        p = self.probs(v)
        t = list(teacher)
        s = sum(t) or 1.0
        t = [x / s for x in t]
        loss = kl_div(t, p)
        dlog = [p[k] - t[k] for k in range(len(p))]
        add_outer(self.W, dlog, v, -lr)
        for k, g in enumerate(dlog):
            self.b[k] -= lr * g
        self.steps += 1
        self.fitted += 1
        self.last_loss = loss
        return loss

    def _idx(self, label: str) -> int:
        lab = (label or "balanced").lower()
        if lab in self.labels:
            return self.labels.index(lab)
        return self.labels.index("balanced")

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "dim": self.dim, "fitted": self.fitted,
            "steps": self.steps, "W": _copy_mat(self.W), "b": list(self.b),
            "last_loss": self.last_loss,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "BiasHead":
        h = cls(dim=int((data or {}).get("dim") or 8), seed=0)
        raw = (data or {}).get("W")
        if raw:
            h.W = [list(map(float, row)) for row in raw]
        b = (data or {}).get("b")
        if b:
            h.b = [float(x) for x in b]
        h.fitted = int((data or {}).get("fitted") or 0)
        h.steps = int((data or {}).get("steps") or 0)
        h.last_loss = float((data or {}).get("last_loss") or 0.0)
        return h


class RouteHead:
    """Hidden → (arousal, left_w, right_w) in [0,1]. Independent sigmoids."""

    kind = "route"

    def __init__(self, dim: int = 8, *, seed: int = 3) -> None:
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        D = max(2, int(dim))
        self.W: Mat = _rand_mat(3, D, 0.08, rng)
        self.b: Vec = zeros(3)
        self.dim = D
        self.fitted = 0
        self.steps = 0
        self.last_loss = 0.0

    def activate(self, h: Sequence[float]) -> Vec:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        return [_sig(dot(self.W[i], v) + self.b[i]) for i in range(3)]

    def predict(self, h: Sequence[float]) -> Tuple[float, float, float]:
        a = self.activate(h)
        return float(a[0]), float(a[1]), float(a[2])

    def loss(self, h: Sequence[float], target: Sequence[float]) -> float:
        pred = self.activate(h)
        tgt = [float(x) for x in list(target)[:3]]
        while len(tgt) < 3:
            tgt.append(0.5)
        return mse(pred, tgt)

    def step(self, h: Sequence[float], target: Sequence[float], *, lr: float = 0.12) -> float:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        raw = [dot(self.W[i], v) + self.b[i] for i in range(3)]
        s = [_sig(x) for x in raw]
        tgt = [float(x) for x in list(target)[:3]]
        while len(tgt) < 3:
            tgt.append(0.5)
        loss = mse(s, tgt)
        dlog = [(2.0 / 3.0) * (s[i] - tgt[i]) * _dsig(s[i]) for i in range(3)]
        add_outer(self.W, dlog, v, -lr)
        for i in range(3):
            self.b[i] -= lr * dlog[i]
        self.steps += 1
        self.fitted += 1
        self.last_loss = loss
        return loss

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "dim": self.dim, "fitted": self.fitted,
            "steps": self.steps, "W": _copy_mat(self.W), "b": list(self.b),
            "last_loss": self.last_loss,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "RouteHead":
        h = cls(dim=int((data or {}).get("dim") or 8), seed=0)
        raw = (data or {}).get("W")
        if raw:
            h.W = [list(map(float, row)) for row in raw]
        b = (data or {}).get("b")
        if b:
            h.b = [float(x) for x in b]
        h.fitted = int((data or {}).get("fitted") or 0)
        h.steps = int((data or {}).get("steps") or 0)
        h.last_loss = float((data or {}).get("last_loss") or 0.0)
        return h


class VetoHead:
    """Hidden → P(veto). Binary logistic. PFC inhibition as a learned gate."""

    kind = "veto"

    def __init__(self, dim: int = 8, *, seed: int = 2) -> None:
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        D = max(2, int(dim))
        self.w: Vec = [rng.gauss(0.0, 0.08) for _ in range(D)]
        self.b = 0.0
        self.dim = D
        self.fitted = 0
        self.steps = 0
        self.last_loss = 0.0

    def predict_prob(self, h: Sequence[float]) -> float:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        return _sig(dot(self.w, v) + self.b)

    def predict(self, h: Sequence[float]) -> bool:
        return self.predict_prob(h) >= 0.5

    def loss(self, h: Sequence[float], target: float) -> float:
        p = self.predict_prob(h)
        y = 1.0 if float(target) >= 0.5 else 0.0
        return -(y * math.log(max(p, 1e-12)) + (1.0 - y) * math.log(max(1.0 - p, 1e-12)))

    def step(self, h: Sequence[float], target: float, *, lr: float = 0.12) -> float:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        p = self.predict_prob(v)
        y = 1.0 if float(target) >= 0.5 else 0.0
        loss = -(y * math.log(max(p, 1e-12)) + (1.0 - y) * math.log(max(1.0 - p, 1e-12)))
        g = p - y
        for i in range(self.dim):
            self.w[i] -= lr * g * v[i]
        self.b -= lr * g
        self.steps += 1
        self.fitted += 1
        self.last_loss = loss
        return loss

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "dim": self.dim, "fitted": self.fitted,
            "steps": self.steps, "w": list(self.w), "b": self.b,
            "last_loss": self.last_loss,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "VetoHead":
        h = cls(dim=int((data or {}).get("dim") or 8), seed=0)
        w = (data or {}).get("w")
        if w:
            h.w = [float(x) for x in w]
        h.b = float((data or {}).get("b") or 0.0)
        h.fitted = int((data or {}).get("fitted") or 0)
        h.steps = int((data or {}).get("steps") or 0)
        h.last_loss = float((data or {}).get("last_loss") or 0.0)
        return h


class PolicyHead:
    """Hidden → (spawn_weapon, extract_late). Two independent logistics."""

    kind = "policy"

    def __init__(self, dim: int = 8, *, seed: int = 5) -> None:
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        D = max(2, int(dim))
        self.W: Mat = _rand_mat(2, D, 0.08, rng)
        self.b: Vec = zeros(2)
        self.dim = D
        self.fitted = 0
        self.steps = 0
        self.last_loss = 0.0

    def activate(self, h: Sequence[float]) -> Vec:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        return [_sig(dot(self.W[i], v) + self.b[i]) for i in range(2)]

    def predict(self, h: Sequence[float]) -> Tuple[int, int]:
        a = self.activate(h)
        return int(a[0] >= 0.5), int(a[1] >= 0.5)

    def loss(self, h: Sequence[float], target: Sequence[float]) -> float:
        p = self.activate(h)
        y = [1.0 if float(target[0]) >= 0.5 else 0.0, 1.0 if float(target[1]) >= 0.5 else 0.0]
        return mse(p, y)

    def step(self, h: Sequence[float], target: Sequence[float], *, lr: float = 0.12) -> float:
        v = list(h)[: self.dim] + [0.0] * max(0, self.dim - len(h))
        raw = [dot(self.W[i], v) + self.b[i] for i in range(2)]
        s = [_sig(x) for x in raw]
        y = [1.0 if float(target[0]) >= 0.5 else 0.0, 1.0 if float(target[1]) >= 0.5 else 0.0]
        loss = mse(s, y)
        dlog = [(s[i] - y[i]) * _dsig(s[i]) for i in range(2)]
        add_outer(self.W, dlog, v, -lr)
        for i in range(2):
            self.b[i] -= lr * dlog[i]
        self.steps += 1
        self.fitted += 1
        self.last_loss = loss
        return loss

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "dim": self.dim, "fitted": self.fitted,
            "steps": self.steps, "W": _copy_mat(self.W), "b": list(self.b),
            "last_loss": self.last_loss,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "PolicyHead":
        h = cls(dim=int((data or {}).get("dim") or 8), seed=0)
        raw = (data or {}).get("W")
        if raw:
            h.W = [list(map(float, row)) for row in raw]
        b = (data or {}).get("b")
        if b:
            h.b = [float(x) for x in b]
        h.fitted = int((data or {}).get("fitted") or 0)
        h.steps = int((data or {}).get("steps") or 0)
        h.last_loss = float((data or {}).get("last_loss") or 0.0)
        return h


def head_from_snapshot(data: Dict[str, Any]):
    kind = str((data or {}).get("kind") or "")
    if kind == "numeric":
        return NumericHead.from_snapshot(data)
    if kind == "bias":
        return BiasHead.from_snapshot(data)
    if kind == "route":
        return RouteHead.from_snapshot(data)
    if kind == "veto":
        return VetoHead.from_snapshot(data)
    if kind == "policy":
        return PolicyHead.from_snapshot(data)
    return NumericHead.from_snapshot(data)


Head = Union[NumericHead, BiasHead, RouteHead, VetoHead, PolicyHead]
