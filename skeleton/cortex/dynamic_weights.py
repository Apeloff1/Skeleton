"""Adaptive and reactive weights beside the live Jeeves transformer.

Live parameters stay on the transformer. Shadow weights stay on the
trial ledger. These banks are a separate residual:

* adaptive — persistent low-rank map ``h + B(Ah) + bias``, clipped SGD
* reactive — fast ``dim x dim`` matrix that decays and writes an outer product

Neither bank writes ``transformer.E`` or advances ``transformer.steps``.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Sequence

from skeleton.cortex.attn import matvec, matvec_T

Vec = List[float]
Mat = List[List[float]]

_DIM_MIN = 1
_DIM_MAX = 4096
_REACTIVE_CLIP = 1.0
_SEED = 0.02

__all__ = ["AdaptiveWeights", "ReactiveWeights", "DynamicWeightState"]


def _require_dim(dim: object) -> int:
    if isinstance(dim, bool) or not isinstance(dim, int) or not _DIM_MIN <= dim <= _DIM_MAX:
        raise ValueError("dimension must be an int in 1..4096")
    return dim


def _require_rank(rank: object, dim: int) -> int:
    if isinstance(rank, bool) or not isinstance(rank, int) or not 1 <= rank <= dim:
        raise ValueError("rank must be an int in 1..dim")
    return rank


def _require_finite(value: object, name: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if positive and number <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
    if nonnegative and number < 0.0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return number


def _require_unit_interval(value: object, name: str) -> float:
    number = _require_finite(value, name, nonnegative=True)
    if number > 1.0:
        raise ValueError(f"{name} must be within [0, 1]")
    return number


def _require_vec(values: object, dim: int, name: str) -> Vec:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{name} must be a length-{dim} vector")
    if len(values) != dim:
        raise ValueError(f"{name} must have dimension {dim}")
    out: Vec = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{name} must be finite")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError(f"{name} must be finite")
        out.append(number)
    return out


def _clip(value: float, limit: float) -> float:
    if value > limit:
        return limit
    if value < -limit:
        return -limit
    return value


def _l2(values: Sequence[float]) -> float:
    acc = 0.0
    for value in values:
        acc += value * value
    norm = math.sqrt(acc)
    if not math.isfinite(norm):
        raise ValueError("vector norm must be finite")
    return norm


def _frobenius(matrix: Mat) -> float:
    acc = 0.0
    for row in matrix:
        for value in row:
            acc += value * value
    norm = math.sqrt(acc)
    if not math.isfinite(norm):
        raise ValueError("matrix norm must be finite")
    return norm


def _copy_mat(matrix: Mat) -> Mat:
    return [list(row) for row in matrix]


def _digest(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require_matrix(raw: object, rows: int, cols: int, name: str) -> Mat:
    if not isinstance(raw, list) or len(raw) != rows:
        raise ValueError(f"{name} must be a {rows}x{cols} matrix")
    out: Mat = []
    for row in raw:
        if not isinstance(row, list) or len(row) != cols:
            raise ValueError(f"{name} must be a {rows}x{cols} matrix")
        parsed: Vec = []
        for item in row:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValueError(f"{name} must be finite")
            number = float(item)
            if not math.isfinite(number):
                raise ValueError(f"{name} must be finite")
            parsed.append(number)
        out.append(parsed)
    return out


class AdaptiveWeights:
    """Low-rank residual ``h + B(Ah) + bias`` trained by clipped SGD."""

    def __init__(self, dim: int, *, rank: int = 4, lr: float = 0.05, clip: float = 0.25) -> None:
        self.dim = _require_dim(dim)
        self.rank = _require_rank(rank, self.dim)
        self.lr = _require_finite(lr, "lr", positive=True)
        self.clip = _require_finite(clip, "clip", positive=True)
        # Seed A so z = Ah is nonzero. B stays zero, matching a residual that
        # starts at identity, and the first step still has a gradient on B.
        self.A: Mat = [
            [_SEED if j % self.rank == k else 0.0 for j in range(self.dim)]
            for k in range(self.rank)
        ]
        self.B: Mat = [[0.0 for _ in range(self.rank)] for _ in range(self.dim)]
        self.bias: Vec = [0.0 for _ in range(self.dim)]
        self.steps = 0
        self.last_error = 0.0

    def predict(self, hidden: Sequence[float]) -> Vec:
        hidden_v = _require_vec(hidden, self.dim, "hidden")
        low = self._low_rank(hidden_v)
        return [hidden_v[i] + low[i] + self.bias[i] for i in range(self.dim)]

    def residual(self, hidden: Sequence[float]) -> Vec:
        hidden_v = _require_vec(hidden, self.dim, "hidden")
        low = self._low_rank(hidden_v)
        return [low[i] + self.bias[i] for i in range(self.dim)]

    def step(self, hidden: Sequence[float], target: Sequence[float]) -> float:
        """Move ``h + B(Ah) + bias`` toward ``target`` and clip every updated value."""
        hidden_v = _require_vec(hidden, self.dim, "hidden")
        target_v = _require_vec(target, self.dim, "target")
        low = self._low_rank(hidden_v)
        error = [hidden_v[i] + low[i] + self.bias[i] - target_v[i] for i in range(self.dim)]
        z = matvec(self.A, hidden_v)
        grad_z = matvec_T(self.B, error)
        lr = self.lr
        limit = self.clip
        for i in range(self.dim):
            row = self.B[i]
            scaled = error[i] * lr
            for k in range(self.rank):
                row[k] = _clip(row[k] - scaled * z[k], limit)
        for k in range(self.rank):
            row = self.A[k]
            scaled = grad_z[k] * lr
            for j in range(self.dim):
                row[j] = _clip(row[j] - scaled * hidden_v[j], limit)
        for i in range(self.dim):
            self.bias[i] = _clip(self.bias[i] - lr * error[i], limit)
        self.steps += 1
        fitted = self.predict(hidden_v)
        self.last_error = _l2([fitted[i] - target_v[i] for i in range(self.dim)])
        return self.last_error

    def bias_norm(self) -> float:
        return _l2(self.bias)

    def factor_norm(self) -> float:
        return math.sqrt(_frobenius(self.A) ** 2 + _frobenius(self.B) ** 2)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": "adaptive-weights",
            "dim": self.dim,
            "rank": self.rank,
            "lr": self.lr,
            "clip": self.clip,
            "steps": self.steps,
            "last_error": self.last_error,
            "A": _copy_mat(self.A),
            "B": _copy_mat(self.B),
            "bias": list(self.bias),
        }

    def restore(self, snap: Dict[str, Any]) -> None:
        if not isinstance(snap, dict):
            raise ValueError("snapshot must be a mapping")
        if type(snap.get("dim")) is not int or snap.get("dim") != self.dim:
            raise ValueError("snapshot dimension does not match")
        rank = _require_rank(snap.get("rank"), self.dim)
        lr = _require_finite(snap.get("lr"), "lr", positive=True)
        clip = _require_finite(snap.get("clip"), "clip", positive=True)
        steps = snap.get("steps")
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0:
            raise ValueError("snapshot steps must be a nonnegative int")
        last_error = _require_finite(snap.get("last_error", 0.0), "last_error", nonnegative=True)
        matrix_a = _require_matrix(snap.get("A"), rank, self.dim, "A")
        matrix_b = _require_matrix(snap.get("B"), self.dim, rank, "B")
        bias = _require_vec(snap.get("bias"), self.dim, "bias")
        self.rank = rank
        self.lr = lr
        self.clip = clip
        self.steps = steps
        self.last_error = last_error
        self.A = matrix_a
        self.B = matrix_b
        self.bias = bias

    def report(self) -> Dict[str, Any]:
        return {
            "kind": "adaptive-weights",
            "dim": self.dim,
            "rank": self.rank,
            "steps": self.steps,
            "last_error": self.last_error,
            "bias_norm": self.bias_norm(),
            "factor_norm": self.factor_norm(),
            "digest": _digest(self.snapshot()),
        }

    def _low_rank(self, hidden: Vec) -> Vec:
        return matvec(self.B, matvec(self.A, hidden))


class ReactiveWeights:
    """Fast matrix. ``write`` decays, adds a normalized outer product, and clips."""

    def __init__(self, dim: int, *, decay: float = 0.5, eta: float = 0.2) -> None:
        self.dim = _require_dim(dim)
        self.decay = _require_unit_interval(decay, "decay")
        self.eta = _require_finite(eta, "eta", nonnegative=True)
        self.M: Mat = [[0.0 for _ in range(self.dim)] for _ in range(self.dim)]
        self.writes = 0

    def write(self, hidden: Sequence[float]) -> None:
        hidden_v = self._normalized(hidden)
        decay = self.decay
        eta = self.eta
        for i in range(self.dim):
            row = self.M[i]
            hi = hidden_v[i]
            for j in range(self.dim):
                row[j] = _clip(row[j] * decay + eta * hi * hidden_v[j], _REACTIVE_CLIP)
        self.writes += 1

    def read(self, hidden: Sequence[float]) -> Vec:
        hidden_v = _require_vec(hidden, self.dim, "hidden")
        return [_clip(value, _REACTIVE_CLIP) for value in matvec(self.M, hidden_v)]

    def decay_once(self) -> None:
        decay = self.decay
        for row in self.M:
            for j in range(self.dim):
                row[j] *= decay

    def norm(self) -> float:
        return _frobenius(self.M)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": "reactive-weights",
            "dim": self.dim,
            "decay": self.decay,
            "eta": self.eta,
            "writes": self.writes,
            "M": _copy_mat(self.M),
        }

    def restore(self, snap: Dict[str, Any]) -> None:
        if not isinstance(snap, dict):
            raise ValueError("snapshot must be a mapping")
        if type(snap.get("dim")) is not int or snap.get("dim") != self.dim:
            raise ValueError("snapshot dimension does not match")
        decay = _require_unit_interval(snap.get("decay"), "decay")
        eta = _require_finite(snap.get("eta"), "eta", nonnegative=True)
        writes = snap.get("writes")
        if isinstance(writes, bool) or not isinstance(writes, int) or writes < 0:
            raise ValueError("snapshot writes must be a nonnegative int")
        matrix = _require_matrix(snap.get("M"), self.dim, self.dim, "M")
        self.decay = decay
        self.eta = eta
        self.writes = writes
        self.M = matrix

    def report(self) -> Dict[str, Any]:
        return {
            "kind": "reactive-weights",
            "dim": self.dim,
            "writes": self.writes,
            "decay": self.decay,
            "norm": self.norm(),
            "digest": _digest(self.snapshot()),
        }

    def _normalized(self, hidden: Sequence[float]) -> Vec:
        hidden_v = _require_vec(hidden, self.dim, "hidden")
        norm = _l2(hidden_v)
        if norm == 0.0:
            return [0.0 for _ in range(self.dim)]
        return [value / norm for value in hidden_v]


class DynamicWeightState:
    """Adaptive residual plus reactive matrix for one transformer width."""

    def __init__(self, dim: int) -> None:
        self.dim = _require_dim(dim)
        self.adaptive = AdaptiveWeights(self.dim)
        self.reactive = ReactiveWeights(self.dim)

    def observe(self, hidden: Sequence[float], target: Sequence[float]) -> None:
        """Step the adaptive residual, then write the source hidden into the reactive matrix."""
        self.adaptive.step(hidden, target)
        self.reactive.write(hidden)

    def modulate(self, hidden: Sequence[float]) -> Vec:
        hidden_v = _require_vec(hidden, self.dim, "hidden")
        residual = self._residual(hidden_v)
        return [hidden_v[i] + residual[i] for i in range(self.dim)]

    def logit_bias(self, hidden: Sequence[float], embeddings: Sequence[Sequence[float]]) -> Vec:
        residual = self._residual(hidden)
        if isinstance(embeddings, (str, bytes)) or not isinstance(embeddings, Sequence):
            raise ValueError("embeddings must be a matrix")
        bias: Vec = []
        for row in embeddings:
            parsed = _require_vec(row, self.dim, "embedding")
            acc = 0.0
            for i in range(self.dim):
                acc += residual[i] * parsed[i]
            if not math.isfinite(acc):
                raise ValueError("logit bias must be finite")
            bias.append(acc)
        return bias

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": "dynamic-weights",
            "dim": self.dim,
            "adaptive": self.adaptive.snapshot(),
            "reactive": self.reactive.snapshot(),
        }

    def restore(self, snap: Dict[str, Any]) -> None:
        if not isinstance(snap, dict):
            raise ValueError("snapshot must be a mapping")
        if type(snap.get("dim")) is not int or snap.get("dim") != self.dim:
            raise ValueError("snapshot dimension does not match")
        adaptive_snap = snap.get("adaptive")
        reactive_snap = snap.get("reactive")
        if not isinstance(adaptive_snap, dict) or not isinstance(reactive_snap, dict):
            raise ValueError("snapshot is missing weight banks")
        adaptive = AdaptiveWeights(self.dim)
        reactive = ReactiveWeights(self.dim)
        adaptive.restore(adaptive_snap)
        reactive.restore(reactive_snap)
        self.adaptive = adaptive
        self.reactive = reactive

    def report(self) -> Dict[str, Any]:
        return {
            "kind": "dynamic-weights",
            "dim": self.dim,
            "adaptive": self.adaptive.report(),
            "reactive": self.reactive.report(),
            "digest": _digest(self.snapshot()),
        }

    def _residual(self, hidden: Sequence[float]) -> Vec:
        hidden_v = _require_vec(hidden, self.dim, "hidden")
        adaptive = self.adaptive.residual(hidden_v)
        reactive = self.reactive.read(hidden_v)
        residual = [adaptive[i] + reactive[i] for i in range(self.dim)]
        hidden_norm = _l2(hidden_v)
        residual_norm = _l2(residual)
        cap = 0.5 * hidden_norm
        if residual_norm > cap and residual_norm > 0.0:
            scale = cap / residual_norm
            residual = [value * scale for value in residual]
        return residual
