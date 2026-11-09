"""Mixture-of-depths inference for the owned pure-Python transformer.

The router freezes tokens whose residual update has converged while keeping
those frozen states available as key/value context for tokens that still need
depth. Training remains full-depth: this module is an inference controller and
does not alter :class:`TinyTransformer` backpropagation or snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
import random
from typing import Dict, List, Sequence, Tuple

from skeleton.cortex.attn import (
    add,
    apply_rope,
    cached_mha,
    gelu,
    matvec,
    sample_logits,
    softmax,
    swiglu,
)
from skeleton.cortex.transformer import TinyTransformer, TransformerBlock


__all__ = ["DepthMetrics", "MixtureOfDepths"]


def _percentile(values: Sequence[int], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(int(v) for v in values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = max(0.0, min(1.0, float(q))) * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(ordered[lo])
    weight = pos - lo
    return float(ordered[lo] * (1.0 - weight) + ordered[hi] * weight)


def _threshold_schedule(value: Real | Sequence[Real]) -> Tuple[float, ...]:
    """Normalize a numeric threshold schedule without lossy type coercion."""
    if isinstance(value, bool):
        raise TypeError("threshold must be a real number or numeric sequence")
    if isinstance(value, Real):
        raw = (value,)
    else:
        if isinstance(value, (str, bytes, bytearray)):
            raise TypeError("threshold must be a real number or numeric sequence")
        try:
            raw = tuple(value)
        except TypeError as exc:
            raise TypeError("threshold must be a real number or numeric sequence") from exc
    if not raw:
        raise ValueError("threshold schedule cannot be empty")
    if any(isinstance(item, bool) or not isinstance(item, Real) for item in raw):
        raise TypeError("threshold schedule must contain only real numbers")
    try:
        thresholds = tuple(float(item) for item in raw)
    except (OverflowError, ValueError) as exc:
        raise ValueError("threshold schedule contains an unsupported number") from exc
    if any(math.isnan(item) for item in thresholds):
        raise ValueError("threshold schedule cannot contain NaN")
    return thresholds


@dataclass(frozen=True)
class DepthMetrics:
    """Per-forward routing telemetry.

    ``layer_token_fraction`` is the number of token/block updates executed
    divided by the full-depth token/block budget. ``estimated_block_savings``
    is therefore a model-level proxy, not a claim about wall-clock speed or
    exact hardware FLOPs; K/V context projection remains necessary for frozen
    tokens while any token is still active.
    """

    token_depths: Tuple[int, ...]
    mean_depth: float
    p50_depth: float
    p90_depth: float
    p95_depth: float
    max_depth: int
    active_token_updates: int
    full_token_updates: int
    layer_token_fraction: float
    estimated_block_savings: float

    def as_dict(self) -> Dict[str, object]:
        return {
            "token_depths": list(self.token_depths),
            "mean_depth": self.mean_depth,
            "p50_depth": self.p50_depth,
            "p90_depth": self.p90_depth,
            "p95_depth": self.p95_depth,
            "max_depth": self.max_depth,
            "active_token_updates": self.active_token_updates,
            "full_token_updates": self.full_token_updates,
            "layer_token_fraction": self.layer_token_fraction,
            "estimated_block_savings": self.estimated_block_savings,
        }


class MixtureOfDepths:
    """Residual-RMS token routing for :class:`TinyTransformer` inference.

    Parameters
    ----------
    model:
        Owned transformer to route. Its weights are never copied or mutated.
    threshold:
        Residual-RMS exit threshold, or a per-layer threshold schedule. A
        one-element sequence behaves like a scalar; shorter schedules hold
        their final value for later layers. Negative thresholds intentionally
        force tokens to full depth and are useful for calibration. Positive
        infinity intentionally forces every eligible token to exit.
    min_depth:
        Minimum number of blocks every token must execute.
    enabled:
        When false, call the transformer's original full-depth path exactly.
    """

    def __init__(
        self,
        model: TinyTransformer,
        *,
        threshold: Real | Sequence[Real] = 0.015,
        min_depth: int = 1,
        enabled: bool = True,
    ) -> None:
        if not isinstance(model, TinyTransformer):
            raise TypeError("model must be a TinyTransformer")
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool")
        if isinstance(min_depth, bool) or not isinstance(min_depth, int):
            raise TypeError("min_depth must be an int")

        thresholds = _threshold_schedule(threshold)
        if min_depth < 1 or min_depth > model.n_layers:
            raise ValueError("min_depth must be between 1 and model.n_layers")

        self.model = model
        self.thresholds = thresholds
        self.min_depth = min_depth
        self.enabled = enabled
        self.last_metrics = self._metrics([model.n_layers], token_count=1)

    def _threshold(self, layer_index: int) -> float:
        return self.thresholds[min(int(layer_index), len(self.thresholds) - 1)]

    def _metrics(self, depths: Sequence[int], *, token_count: int) -> DepthMetrics:
        clean = tuple(int(depth) for depth in depths)
        count = max(1, int(token_count))
        full_updates = max(1, count * self.model.n_layers)
        active_updates = sum(clean)
        fraction = min(1.0, max(0.0, active_updates / full_updates))
        return DepthMetrics(
            token_depths=clean,
            mean_depth=sum(clean) / max(1, len(clean)),
            p50_depth=_percentile(clean, 0.50),
            p90_depth=_percentile(clean, 0.90),
            p95_depth=_percentile(clean, 0.95),
            max_depth=max(clean) if clean else 0,
            active_token_updates=active_updates,
            full_token_updates=full_updates,
            layer_token_fraction=fraction,
            estimated_block_savings=1.0 - fraction,
        )

    def metrics(self) -> Dict[str, object]:
        """Return a copy-friendly dictionary for the most recent forward."""
        return self.last_metrics.as_dict()

    def _selective_layer(
        self,
        layer: TransformerBlock,
        hidden: Sequence[Sequence[float]],
        active: Sequence[int],
    ) -> List[List[float]]:
        """Run one block only for active queries, preserving full K/V context."""
        if len(active) == len(hidden):
            out, _cache = layer.forward([list(row) for row in hidden], self.model.n_heads)
            return out

        normalized: List[List[float]] = []
        for row in hidden:
            normed, _hat, _inv = layer._norm(list(row), layer.ln1_g, layer.ln1_b)
            normalized.append(normed)

        keys = [apply_rope(matvec(layer.Wk, row), pos) for pos, row in enumerate(normalized)]
        values = [matvec(layer.Wv, row) for row in normalized]
        output = [list(row) for row in hidden]

        for pos in active:
            query = apply_rope(matvec(layer.Wq, normalized[pos]), pos)
            context, _weights = cached_mha(
                query,
                keys[: pos + 1],
                values[: pos + 1],
                self.model.n_heads,
            )
            residual = add(list(hidden[pos]), matvec(layer.Wo, context))
            if layer.d_ff:
                normed, _hat, _inv = layer._norm(residual, layer.ln2_g, layer.ln2_b)
                if layer.ffn_kind == "swiglu":
                    activation, _gate, _up = swiglu(
                        normed,
                        layer.W1,
                        layer.Wu,
                        layer.b1,
                        layer.bu,
                    )
                else:
                    activation = gelu(add(matvec(layer.W1, normed), layer.b1))
                residual = add(residual, add(matvec(layer.W2, activation), layer.b2))
            output[pos] = residual
        return output

    def forward_ids(self, ids: Sequence[int]) -> List[List[float]]:
        """Return fixed-shape hidden states and record per-token effective depth."""
        token_ids = list(ids) or [self.model.unk]
        hidden = self.model._encode(token_ids)
        token_count = len(hidden)

        if not self.enabled:
            hidden, _caches = self.model._forward(token_ids)
            self.last_metrics = self._metrics(
                [self.model.n_layers] * token_count,
                token_count=token_count,
            )
            return [list(row) for row in hidden]

        active = list(range(token_count))
        depths = [self.model.n_layers] * token_count

        for layer_index, layer in enumerate(self.model.layers):
            if not active:
                break
            before = hidden
            hidden = self._selective_layer(layer, before, active)
            depth = layer_index + 1
            if depth < self.min_depth:
                continue

            threshold = self._threshold(layer_index)
            survivors: List[int] = []
            for pos in active:
                delta = hidden[pos]
                prior = before[pos]
                residual_rms = math.sqrt(
                    sum((delta[i] - prior[i]) ** 2 for i in range(self.model.dim))
                    / self.model.dim
                )
                if residual_rms <= threshold:
                    depths[pos] = depth
                else:
                    survivors.append(pos)
            active = survivors

        self.last_metrics = self._metrics(depths, token_count=token_count)
        return [list(row) for row in hidden]

    def logits_ids(self, ids: Sequence[int]) -> List[float]:
        hidden = self.forward_ids(list(ids)[-self.model.ctx :])
        last = hidden[-1] if hidden else [0.0] * self.model.dim
        return self.model._unembed(last)

    def hidden_seq(self, prefix: str) -> List[List[float]]:
        ids = self.model._ids(prefix)[-self.model.ctx :]
        return self.forward_ids(ids)

    def hidden(self, prefix: str) -> List[float]:
        sequence = self.hidden_seq(prefix)
        return list(sequence[-1]) if sequence else [0.0] * self.model.dim

    def token_prob(self, prefix: str, token: str) -> float:
        ids = self.model._ids(prefix)[-self.model.ctx :]
        probabilities = softmax(self.logits_ids(ids))
        return float(probabilities[self.model._id(token)])

    def generate(
        self,
        prefix: str | Sequence[str],
        n: int = 12,
        *,
        seed: int = 0,
        temperature: float = 1.0,
        top_k: int = 0,
        top_p: float = 1.0,
    ) -> Tuple[str, ...]:
        """Decode without KV cache so routing decisions remain layer-local."""
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        if isinstance(prefix, str):
            ids = self.model._ids(prefix)
        else:
            ids = [self.model._id(str(token)) for token in prefix] or [self.model.unk]
        output = list(ids)
        for _ in range(max(1, int(n))):
            logits = self.logits_ids(output[-self.model.ctx :])
            nxt = sample_logits(
                logits,
                rng,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
            )
            output.append(int(nxt))
        return tuple(
            self.model.itos[idx] if 0 <= idx < len(self.model.itos) else "__unk__"
            for idx in output[:n]
        )
