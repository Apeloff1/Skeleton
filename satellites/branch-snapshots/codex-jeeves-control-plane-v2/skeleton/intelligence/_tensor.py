"""Shared tensor interface — split from the intelligence monolith (v16.2)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

# =============================================================================
# COMMON TENSOR INTERFACE
# =============================================================================

@dataclass
class Tensor:
    """Simple tensor for internal operations (no external deps)."""
    data: List[float]
    shape: Tuple[int, ...]
    grad: Optional[List[float]] = None

    def __post_init__(self):
        expected = math.prod(self.shape)
        if len(self.data) != expected:
            raise ValueError(f"Data length {len(self.data)} != shape product {expected}")

    @classmethod
    def zeros(cls, *shape: int) -> "Tensor":
        return cls(data=[0.0] * math.prod(shape), shape=shape)

    @classmethod
    def ones(cls, *shape: int) -> "Tensor":
        return cls(data=[1.0] * math.prod(shape), shape=shape)

    @classmethod
    def random(cls, *shape: int) -> "Tensor":
        return cls(data=[random.random() for _ in range(math.prod(shape))], shape=shape)

    def __add__(self, other: "Tensor") -> "Tensor":
        if self.shape != other.shape:
            raise ValueError("Shape mismatch")
        return Tensor([a + b for a, b in zip(self.data, other.data)], self.shape)

    def __mul__(self, scalar: float) -> "Tensor":
        return Tensor([a * scalar for a in self.data], self.shape)

    def dot(self, other: "Tensor") -> float:
        if len(self.data) != len(other.data):
            raise ValueError("Length mismatch")
        return sum(a * b for a, b in zip(self.data, other.data))

    def mean(self) -> float:
        return sum(self.data) / len(self.data) if self.data else 0.0

    def std(self) -> float:
        if len(self.data) < 2:
            return 0.0
        m = self.mean()
        variance = sum((x - m) ** 2 for x in self.data) / (len(self.data) - 1)
        return math.sqrt(variance)
