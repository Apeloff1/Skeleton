"""Parametric LoRA write-back — lightweight adapter fusion and checkpointing.

Provides a parameter-efficient fine-tuning layer that can merge LoRA
(low-rank adaptation) weights back into base parameters, with
selective rank pruning, magnitude gating, and versioned checkpoint
serialization.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class LoRALayer:
    name: str
    rank: int
    alpha: float
    lora_A: List[List[float]]  # shape [rank, in_features]
    lora_B: List[List[float]]  # shape [out_features, rank]
    scale: float = 1.0
    frozen: bool = False

    def effective_weight(self) -> List[List[float]]:
        # W_eff = W_base + (lora_B @ lora_A) * (alpha / rank)
        # Return the delta only
        out = len(self.lora_B)
        rank = self.rank
        alpha_over_rank = self.alpha / max(1, rank)
        delta = [[0.0] * len(self.lora_A[0]) for _ in range(out)]
        for i in range(out):
            for j in range(rank):
                b_ij = self.lora_B[i][j]
                for k in range(len(self.lora_A[0])):
                    delta[i][k] += b_ij * self.lora_A[j][k] * alpha_over_rank * self.scale
        return delta

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "rank": self.rank,
            "alpha": self.alpha,
            "scale": round(self.scale, 6),
            "frozen": self.frozen,
            "A_shape": [len(self.lora_A), len(self.lora_A[0])] if self.lora_A else [0, 0],
            "B_shape": [len(self.lora_B), len(self.lora_B[0])] if self.lora_B else [0, 0],
        }


class ParametricLoRAWriteBack:
    """Manages LoRA adapter fusion, pruning, and checkpointing."""

    def __init__(self, base_dim: int = 768, default_rank: int = 8, default_alpha: float = 16.0):
        self.base_dim = base_dim
        self.default_rank = default_rank
        self.default_alpha = default_alpha
        self._layers: Dict[str, LoRALayer] = {}
        self._checkpoints: List[Dict[str, Any]] = []

    def add_layer(self, name: str, lora_A: List[List[float]], lora_B: List[List[float]], rank: Optional[int] = None, alpha: Optional[float] = None) -> LoRALayer:
        layer = LoRALayer(
            name=name,
            rank=rank or self.default_rank,
            alpha=alpha or self.default_alpha,
            lora_A=lora_A,
            lora_B=lora_B,
        )
        self._layers[name] = layer
        return layer

    def prune_rank(self, name: str, target_rank: int) -> LoRALayer:
        """Prune a layer to a lower rank by truncating singular dimensions."""
        layer = self._layers.get(name)
        if layer is None:
            raise KeyError(f"No LoRA layer named {name}")
        if target_rank >= layer.rank:
            return layer
        # Truncate A and B to target_rank
        layer.lora_A = layer.lora_A[:target_rank]
        layer.lora_B = [[v[i] for i in range(target_rank)] for v in layer.lora_B]
        layer.rank = target_rank
        return layer

    def magnitude_gate(self, name: str, threshold: float = 1e-4) -> int:
        """Zero out small-magnitude updates and return count of pruned cells."""
        layer = self._layers.get(name)
        if layer is None:
            return 0
        pruned = 0
        for i in range(len(layer.lora_A)):
            for j in range(len(layer.lora_A[i])):
                if abs(layer.lora_A[i][j]) < threshold:
                    layer.lora_A[i][j] = 0.0
                    pruned += 1
        for i in range(len(layer.lora_B)):
            for j in range(len(layer.lora_B[i])):
                if abs(layer.lora_B[i][j]) < threshold:
                    layer.lora_B[i][j] = 0.0
                    pruned += 1
        return pruned

    def merge_into_base(self, base_weights: Dict[str, List[List[float]]]) -> Dict[str, List[List[float]]]:
        """Return base weights with LoRA deltas merged in."""
        merged = {}
        for name, w in base_weights.items():
            layer = self._layers.get(name)
            if layer is None or layer.frozen:
                merged[name] = [row[:] for row in w]
                continue
            delta = layer.effective_weight()
            out_rows = len(w)
            in_cols = len(w[0]) if w else 0
            merged[name] = [
                [w[i][j] + (delta[i][j] if i < len(delta) and j < len(delta[0]) else 0.0) for j in range(in_cols)]
                for i in range(out_rows)
            ]
        return merged

    def checkpoint(self, tag: str = "") -> Dict[str, Any]:
        cp = {
            "tag": tag or f"cp-{int(time.time())}",
            "at": int(time.time() * 1000),
            "layers": {name: layer.to_dict() for name, layer in self._layers.items()},
            "layer_count": len(self._layers),
        }
        self._checkpoints.append(cp)
        # Keep last 16
        if len(self._checkpoints) > 16:
            self._checkpoints = self._checkpoints[-16:]
        return cp

    def save(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "base_dim": self.base_dim,
            "default_rank": self.default_rank,
            "default_alpha": self.default_alpha,
            "layers": {name: layer.to_dict() for name, layer in self._layers.items()},
            "checkpoints": self._checkpoints,
        }
        p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def load(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        self.base_dim = data.get("base_dim", self.base_dim)
        self.default_rank = data.get("default_rank", self.default_rank)
        self.default_alpha = data.get("default_alpha", self.default_alpha)
        # Note: full matrix reload omitted for brevity; would reconstruct LoRALayer objects

    def card(self) -> Dict[str, Any]:
        total_params = sum(
            (len(l.lora_A) * len(l.lora_A[0]) if l.lora_A else 0) +
            (len(l.lora_B) * len(l.lora_B[0]) if l.lora_B else 0)
            for l in self._layers.values()
        )
        return {
            "kind": "parametric-lora-card",
            "layers": len(self._layers),
            "total_params": total_params,
            "default_rank": self.default_rank,
            "default_alpha": self.default_alpha,
            "checkpoints": len(self._checkpoints),
            "stored_prose": 0,
        }
