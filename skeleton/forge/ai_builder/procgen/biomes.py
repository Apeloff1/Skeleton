"""Biome classification by height and moisture thresholds (Whittaker-style table)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from .canonical import digest
from .errors import ProcgenError
from .heightmap import Heightmap


@dataclass(frozen=True)
class BiomeBand:
    """Heights up to ``max_height`` map to the first ``(max_moisture, biome)`` that fits."""
    max_height: float
    by_moisture: tuple[tuple[float, str], ...]

    def __post_init__(self) -> None:
        if not 0.0 <= self.max_height <= 1.0:
            raise ProcgenError("band max_height must be in [0, 1]")
        if not self.by_moisture:
            raise ProcgenError("band needs at least one biome")
        last = -1.0
        for m, name in self.by_moisture:
            if not isinstance(name, str) or not name.isidentifier():
                raise ProcgenError(f"invalid biome name {name!r}")
            if not last < m <= 1.0:
                raise ProcgenError("moisture thresholds must increase and end at <= 1")
            last = m
        if self.by_moisture[-1][0] != 1.0:
            raise ProcgenError("last moisture threshold must be 1.0")


@dataclass(frozen=True)
class BiomeTable:
    bands: tuple[BiomeBand, ...]
    walkable: frozenset[str]

    def __post_init__(self) -> None:
        if not self.bands:
            raise ProcgenError("biome table is empty")
        last = -1.0
        for b in self.bands:
            if not last < b.max_height:
                raise ProcgenError("band heights must increase")
            last = b.max_height
        if self.bands[-1].max_height != 1.0:
            raise ProcgenError("last band must reach height 1.0")
        unknown = set(self.walkable) - self.names()
        if unknown:
            raise ProcgenError(f"walkable lists unknown biomes {sorted(unknown)}")

    def names(self) -> set[str]:
        return {n for b in self.bands for _, n in b.by_moisture}

    def classify(self, height: float, moisture: float) -> str:
        h = min(max(height, 0.0), 1.0)
        m = min(max(moisture, 0.0), 1.0)
        for band in self.bands:
            if h <= band.max_height:
                for limit, name in band.by_moisture:
                    if m <= limit:
                        return name
        raise ProcgenError("unreachable: thresholds cover [0, 1]")  # pragma: no cover

    def as_dict(self) -> dict:
        return {"bands": [{"max_height": b.max_height, "by_moisture": [list(x) for x in b.by_moisture]}
                          for b in self.bands], "walkable": sorted(self.walkable)}

    def digest(self) -> str:
        return digest(self.as_dict())


DEFAULT_BIOMES = BiomeTable(
    bands=(
        BiomeBand(0.30, ((1.0, "water"),)),
        BiomeBand(0.36, ((1.0, "shore"),)),
        BiomeBand(0.60, ((0.25, "desert"), (0.55, "grassland"), (1.0, "forest"))),
        BiomeBand(0.78, ((0.33, "scrub"), (0.70, "woodland"), (1.0, "taiga"))),
        BiomeBand(0.90, ((1.0, "rock"),)),
        BiomeBand(1.00, ((0.50, "tundra"), (1.0, "snow"))),
    ),
    walkable=frozenset({"shore", "desert", "grassland", "forest", "scrub", "woodland", "taiga", "tundra", "snow"}),
)


@dataclass(frozen=True)
class BiomeMap:
    width: int
    height: int
    cells: tuple[str, ...]

    def at(self, x: int, y: int) -> str:
        return self.cells[y * self.width + x]

    def counts(self) -> dict[str, int]:
        return dict(sorted(Counter(self.cells).items()))

    def fractions(self) -> dict[str, float]:
        n = len(self.cells)
        return {k: v / n for k, v in self.counts().items()}

    def walkable_mask(self, table: BiomeTable) -> tuple[bool, ...]:
        return tuple(c in table.walkable for c in self.cells)

    def dominant(self, x0: int, y0: int, x1: int, y1: int) -> str:
        """Most common biome in the half-open box, ties broken by name."""
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(self.width, max(x1, x0 + 1)), min(self.height, max(y1, y0 + 1))
        c = Counter(self.cells[y * self.width + x] for y in range(y0, y1) for x in range(x0, x1))
        if not c:
            return self.at(min(x0, self.width - 1), min(y0, self.height - 1))
        return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    def digest(self) -> str:
        return digest({"w": self.width, "h": self.height, "cells": list(self.cells)})


def classify(height: Heightmap, moisture: Heightmap, table: BiomeTable = DEFAULT_BIOMES) -> BiomeMap:
    if (height.width, height.height) != (moisture.width, moisture.height):
        raise ProcgenError("height and moisture must share dimensions")
    return BiomeMap(height.width, height.height,
                    tuple(table.classify(h, m) for h, m in zip(height.cells, moisture.cells)))


def table_from(spec: Sequence[tuple[float, Sequence[tuple[float, str]]]], walkable: Sequence[str]) -> BiomeTable:
    """Build a table from plain data, e.g. a config file."""
    return BiomeTable(tuple(BiomeBand(float(h), tuple((float(m), str(n)) for m, n in row)) for h, row in spec),
                      frozenset(walkable))
