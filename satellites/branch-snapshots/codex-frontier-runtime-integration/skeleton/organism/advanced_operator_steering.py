"""Advanced operator steering — high-dimensional control surface for operators.

Provides steering vectors, interpolation, and constraint surfaces
that let operators guide generation along semantic axes (style,
mood, complexity, safety, etc.) with fine-grained control and
composition.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SteeringVector:
    name: str
    dims: List[float]
    strength: float = 1.0
    constraints: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    def normalize(self) -> "SteeringVector":
        norm = math.sqrt(sum(d * d for d in self.dims))
        if norm == 0:
            return self
        return SteeringVector(
            name=self.name,
            dims=[d / norm for d in self.dims],
            strength=self.strength,
            constraints=self.constraints,
        )

    def scaled(self, factor: float) -> "SteeringVector":
        return SteeringVector(
            name=self.name,
            dims=[d * factor for d in self.dims],
            strength=self.strength * factor,
            constraints=self.constraints,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "dims": [round(d, 6) for d in self.dims],
            "strength": round(self.strength, 4),
            "constraints": self.constraints,
        }


class AdvancedOperatorSteering:
    """Composable steering with interpolation and constraint enforcement."""

    def __init__(self, dim: int = 64):
        self.dim = dim
        self._vectors: Dict[str, SteeringVector] = {}
        self._active: List[str] = []
        self._blend_weights: Dict[str, float] = {}

    def register(self, name: str, dims: Optional[List[float]] = None, strength: float = 1.0) -> SteeringVector:
        if dims is None:
            # Random unit vector
            import random
            raw = [random.gauss(0, 1) for _ in range(self.dim)]
            norm = math.sqrt(sum(d * d for d in raw))
            dims = [d / norm for d in raw]
        vec = SteeringVector(name=name, dims=dims[:self.dim], strength=strength)
        self._vectors[name] = vec
        return vec

    def activate(self, name: str, weight: float = 1.0) -> None:
        if name not in self._vectors:
            raise KeyError(f"Unknown steering vector: {name}")
        if name not in self._active:
            self._active.append(name)
        self._blend_weights[name] = weight

    def deactivate(self, name: str) -> None:
        if name in self._active:
            self._active.remove(name)
        self._blend_weights.pop(name, None)

    def set_constraint(self, name: str, axis: str, low: float, high: float) -> None:
        vec = self._vectors.get(name)
        if vec is None:
            raise KeyError(f"Unknown steering vector: {name}")
        vec.constraints[axis] = (low, high)

    def composite_vector(self) -> List[float]:
        """Blend all active vectors by weight, then enforce constraints."""
        result = [0.0] * self.dim
        total_weight = 0.0
        for name in self._active:
            vec = self._vectors[name]
            w = self._blend_weights.get(name, 1.0)
            for i in range(self.dim):
                result[i] += vec.dims[i] * w * vec.strength
            total_weight += w
        if total_weight > 0:
            result = [v / total_weight for v in result]
        # Enforce constraints by clamping affected dimensions
        for name in self._active:
            vec = self._vectors[name]
            for axis, (low, high) in vec.constraints.items():
                # Map axis name to dimension index via hash
                idx = hash(axis) % self.dim
                result[idx] = max(low, min(high, result[idx]))
        return result

    def interpolate(self, a: str, b: str, t: float) -> List[float]:
        """Interpolate between two steering vectors."""
        va = self._vectors.get(a)
        vb = self._vectors.get(b)
        if va is None or vb is None:
            raise KeyError(f"Unknown vectors: {a}, {b}")
        return [
            va.dims[i] * (1 - t) + vb.dims[i] * t
            for i in range(self.dim)
        ]

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "advanced-operator-steering-card",
            "dim": self.dim,
            "registered_vectors": list(self._vectors.keys()),
            "active_vectors": self._active,
            "blend_weights": {k: round(v, 4) for k, v in self._blend_weights.items()},
            "stored_prose": 0,
        }
