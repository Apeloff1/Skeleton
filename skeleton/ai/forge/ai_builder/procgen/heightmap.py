"""A small immutable float grid used by the terrain generators."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Sequence

from .canonical import digest, q
from .errors import ProcgenError

MAX_SIDE = 1025


def _check_dims(width: int, height: int) -> None:
    for name, v in (("width", width), ("height", height)):
        if isinstance(v, bool) or not isinstance(v, int) or not 2 <= v <= MAX_SIDE:
            raise ProcgenError(f"{name} must be an int in [2, {MAX_SIDE}]")


@dataclass(frozen=True)
class Heightmap:
    width: int
    height: int
    cells: tuple[float, ...]  # row-major, len == width * height

    def __post_init__(self) -> None:
        _check_dims(self.width, self.height)
        if len(self.cells) != self.width * self.height:
            raise ProcgenError("cell count does not match dimensions")

    @classmethod
    def from_rows(cls, rows: Sequence[Sequence[float]]) -> "Heightmap":
        if not rows or not rows[0]:
            raise ProcgenError("empty rows")
        w = len(rows[0])
        if any(len(r) != w for r in rows):
            raise ProcgenError("ragged rows")
        return cls(w, len(rows), tuple(float(v) for r in rows for v in r))

    @classmethod
    def filled(cls, width: int, height: int, value: float = 0.0) -> "Heightmap":
        _check_dims(width, height)
        return cls(width, height, (float(value),) * (width * height))

    def at(self, x: int, y: int) -> float:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ProcgenError(f"({x}, {y}) outside {self.width}x{self.height}")
        return self.cells[y * self.width + x]

    def clamped(self, x: int, y: int) -> float:
        x = min(max(x, 0), self.width - 1)
        y = min(max(y, 0), self.height - 1)
        return self.cells[y * self.width + x]

    def sample(self, u: float, v: float) -> float:
        """Bilinear sample at normalised coordinates ``u, v`` in [0, 1]."""
        fx = min(max(u, 0.0), 1.0) * (self.width - 1)
        fy = min(max(v, 0.0), 1.0) * (self.height - 1)
        x0, y0 = int(fx), int(fy)
        x1, y1 = min(x0 + 1, self.width - 1), min(y0 + 1, self.height - 1)
        tx, ty = fx - x0, fy - y0
        a = self.at(x0, y0) * (1 - tx) + self.at(x1, y0) * tx
        b = self.at(x0, y1) * (1 - tx) + self.at(x1, y1) * tx
        return a * (1 - ty) + b * ty

    def rows(self) -> list[list[float]]:
        w = self.width
        return [list(self.cells[i * w:(i + 1) * w]) for i in range(self.height)]

    def coords(self) -> Iterator[tuple[int, int]]:
        for y in range(self.height):
            for x in range(self.width):
                yield x, y

    def neighbours(self, x: int, y: int, *, diagonal: bool = False) -> Iterator[tuple[int, int]]:
        steps = ((1, 0), (-1, 0), (0, 1), (0, -1))
        if diagonal:
            steps += ((1, 1), (1, -1), (-1, 1), (-1, -1))
        for dx, dy in steps:
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                yield nx, ny

    @property
    def low(self) -> float:
        return min(self.cells)

    @property
    def high(self) -> float:
        return max(self.cells)

    def mean(self) -> float:
        return sum(self.cells) / len(self.cells)

    def map(self, fn: Callable[[float], float]) -> "Heightmap":
        return Heightmap(self.width, self.height, tuple(fn(v) for v in self.cells))

    def normalized(self) -> "Heightmap":
        lo, hi = self.low, self.high
        if hi - lo < 1e-12:
            return Heightmap.filled(self.width, self.height, 0.5)
        span = hi - lo
        return self.map(lambda v: (v - lo) / span)

    def quantized(self) -> "Heightmap":
        return self.map(q)

    def blend(self, other: "Heightmap", weight: float) -> "Heightmap":
        if (other.width, other.height) != (self.width, self.height):
            raise ProcgenError("blend needs equal dimensions")
        return Heightmap(self.width, self.height,
                         tuple(a * (1 - weight) + b * weight for a, b in zip(self.cells, other.cells)))

    def digest(self) -> str:
        return digest({"w": self.width, "h": self.height, "cells": list(self.quantized().cells)})

    def to_dict(self, *, include_cells: bool = False) -> dict:
        out = {"width": self.width, "height": self.height, "min": q(self.low), "max": q(self.high),
               "mean": q(self.mean()), "digest": self.digest()}
        if include_cells:
            out["cells"] = [q(v) for v in self.cells]
        return out
