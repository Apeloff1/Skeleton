"""Seeded value noise (fBm) and diamond-square heightmaps.

Both draw only from a ``DeterministicRng`` handed in by the caller, so the
same substream gives the same field bit for bit.
"""
from __future__ import annotations

import math

from skeleton.simulation.ecs.rng import DeterministicRng

from .errors import ProcgenError
from .heightmap import Heightmap, _check_dims


def _smooth(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)  # quintic fade


def _lattice(rng: DeterministicRng, cols: int, rows: int) -> list[list[float]]:
    return [[rng.random() for _ in range(cols)] for _ in range(rows)]


def value_noise(width: int, height: int, rng: DeterministicRng, *, scale: float = 16.0,
                octaves: int = 4, persistence: float = 0.5, lacunarity: float = 2.0,
                wrap: bool = False) -> Heightmap:
    """Fractal value noise normalised to [0, 1].

    ``scale`` is the lattice spacing in cells of the first octave. Each octave
    draws its own lattice in order, so octave ``k`` is fixed regardless of how
    many octaves follow it. ``wrap`` makes the field tile horizontally and
    vertically.
    """
    _check_dims(width, height)
    if not 1 <= octaves <= 12:
        raise ProcgenError("octaves must be in [1, 12]")
    if not (scale >= 1.0 and math.isfinite(scale)):
        raise ProcgenError("scale must be >= 1")
    if not 0.0 < persistence <= 1.0 or not 1.0 < lacunarity <= 4.0:
        raise ProcgenError("persistence in (0, 1], lacunarity in (1, 4]")
    acc = [0.0] * (width * height)
    amp, spacing, total = 1.0, scale, 0.0
    for _ in range(octaves):
        cols = max(2, int(math.ceil(width / spacing)) + 1)
        rows = max(2, int(math.ceil(height / spacing)) + 1)
        if wrap:
            cols, rows = cols - 1, rows - 1
        grid = _lattice(rng, cols, rows)
        for y in range(height):
            fy = y / spacing
            y0 = int(fy)
            ty = _smooth(fy - y0)
            if wrap:
                ya, yb = y0 % rows, (y0 + 1) % rows
            else:
                ya, yb = min(y0, rows - 1), min(y0 + 1, rows - 1)
            ra, rb = grid[ya], grid[yb]
            base = y * width
            for x in range(width):
                fx = x / spacing
                x0 = int(fx)
                tx = _smooth(fx - x0)
                if wrap:
                    xa, xb = x0 % cols, (x0 + 1) % cols
                else:
                    xa, xb = min(x0, cols - 1), min(x0 + 1, cols - 1)
                top = ra[xa] + (ra[xb] - ra[xa]) * tx
                bot = rb[xa] + (rb[xb] - rb[xa]) * tx
                acc[base + x] += amp * (top + (bot - top) * ty)
        total += amp
        amp *= persistence
        spacing = max(1.0, spacing / lacunarity)
    return Heightmap(width, height, tuple(v / total for v in acc)).normalized()


def diamond_square(exponent: int, rng: DeterministicRng, *, roughness: float = 0.55,
                   corners: tuple[float, float, float, float] | None = None) -> Heightmap:
    """Classic midpoint displacement on a ``(2**exponent + 1)`` square, normalised to [0, 1].

    ``roughness`` in (0, 1) scales the displacement each halving (Hurst-like).
    """
    if isinstance(exponent, bool) or not isinstance(exponent, int) or not 1 <= exponent <= 10:
        raise ProcgenError("exponent must be an int in [1, 10]")
    if not 0.0 < roughness < 1.0:
        raise ProcgenError("roughness must be in (0, 1)")
    n = (1 << exponent) + 1
    g = [0.0] * (n * n)
    c = corners or tuple(rng.random() for _ in range(4))
    if len(c) != 4:
        raise ProcgenError("need four corner values")
    last = n - 1
    g[0], g[last], g[last * n], g[last * n + last] = c
    step, mag = last, 1.0
    while step > 1:
        half = step // 2
        # diamond step: square centres
        for y in range(half, n, step):
            for x in range(half, n, step):
                avg = (g[(y - half) * n + x - half] + g[(y - half) * n + x + half]
                       + g[(y + half) * n + x - half] + g[(y + half) * n + x + half]) / 4.0
                g[y * n + x] = avg + (rng.random() * 2 - 1) * mag
        # square step: edge midpoints
        for y in range(0, n, half):
            for x in range((y + half) % step, n, step):
                s, k = 0.0, 0
                for dx, dy in ((-half, 0), (half, 0), (0, -half), (0, half)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < n and 0 <= ny < n:
                        s += g[ny * n + nx]
                        k += 1
                g[y * n + x] = s / k + (rng.random() * 2 - 1) * mag
        step = half
        mag *= roughness
    return Heightmap(n, n, tuple(g)).normalized()


def resample(hm: Heightmap, width: int, height: int) -> Heightmap:
    """Bilinear resample to new dimensions (e.g. fit diamond-square to a world size)."""
    _check_dims(width, height)
    cells = []
    for y in range(height):
        v = y / (height - 1)
        for x in range(width):
            cells.append(hm.sample(x / (width - 1), v))
    return Heightmap(width, height, tuple(cells))


def ridged(hm: Heightmap) -> Heightmap:
    """Fold a [0, 1] field around 0.5 to make sharp ridgelines."""
    return hm.map(lambda v: 1.0 - abs(2.0 * v - 1.0)).normalized()


def radial_falloff(hm: Heightmap, *, strength: float = 1.0, power: float = 2.0) -> Heightmap:
    """Push edges down so the map reads as an island / bounded region."""
    if not 0.0 <= strength <= 1.0 or power <= 0:
        raise ProcgenError("strength in [0, 1], power > 0")
    cx, cy = (hm.width - 1) / 2.0, (hm.height - 1) / 2.0
    out = []
    for y in range(hm.height):
        for x in range(hm.width):
            d = math.hypot((x - cx) / max(cx, 1e-9), (y - cy) / max(cy, 1e-9)) / math.sqrt(2.0)
            out.append(hm.cells[y * hm.width + x] * (1.0 - strength * min(1.0, d) ** power))
    return Heightmap(hm.width, hm.height, tuple(out)).normalized()
