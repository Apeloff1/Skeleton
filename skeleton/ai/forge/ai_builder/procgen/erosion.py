"""Erosion-lite: a few passes of thermal slumping plus cheap droplet erosion.

Neither pass tries to be physically faithful. Thermal erosion moves material
from a cell to lower neighbours when the slope exceeds a talus angle;
droplet erosion walks droplets downhill, picking up and dropping sediment.
Both conserve total mass up to float rounding, and both iterate in a fixed
cell order so they are deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.simulation.ecs.rng import DeterministicRng

from .errors import ProcgenError
from .heightmap import Heightmap


@dataclass(frozen=True)
class ErosionReport:
    thermal_moved: float
    droplet_eroded: float
    droplet_deposited: float
    droplets: int

    def as_dict(self) -> dict:
        from .canonical import q
        return {"thermal_moved": q(self.thermal_moved), "droplet_eroded": q(self.droplet_eroded),
                "droplet_deposited": q(self.droplet_deposited), "droplets": self.droplets}


def thermal(hm: Heightmap, *, iterations: int = 8, talus: float = 0.02,
            rate: float = 0.5) -> tuple[Heightmap, float]:
    if not 0 <= iterations <= 200:
        raise ProcgenError("iterations must be in [0, 200]")
    if not 0.0 <= talus < 1.0 or not 0.0 < rate <= 1.0:
        raise ProcgenError("talus in [0, 1), rate in (0, 1]")
    w, h = hm.width, hm.height
    g = list(hm.cells)
    moved_total = 0.0
    for _ in range(iterations):
        delta = [0.0] * len(g)
        for y in range(h):
            for x in range(w):
                i = y * w + x
                here = g[i]
                lower: list[tuple[int, float]] = []
                total = 0.0
                biggest = 0.0
                for nx, ny in hm.neighbours(x, y):
                    j = ny * w + nx
                    d = here - g[j]
                    if d > talus:
                        lower.append((j, d))
                        total += d
                        biggest = max(biggest, d)
                if not lower:
                    continue
                amount = rate * (biggest - talus) / 2.0
                for j, d in lower:
                    share = amount * d / total
                    delta[i] -= share
                    delta[j] += share
                moved_total += amount
        g = [a + b for a, b in zip(g, delta)]
    return Heightmap(w, h, tuple(g)), moved_total


def droplets(hm: Heightmap, rng: DeterministicRng, *, count: int = 256, max_steps: int = 32,
             capacity: float = 0.05, erode: float = 0.3, deposit: float = 0.3) -> tuple[Heightmap, float, float]:
    """Steepest-descent droplets on the 8-neighbourhood."""
    if not 0 <= count <= 100_000 or not 1 <= max_steps <= 1024:
        raise ProcgenError("count in [0, 100000], max_steps in [1, 1024]")
    for name, v in (("capacity", capacity), ("erode", erode), ("deposit", deposit)):
        if not 0.0 <= v <= 1.0:
            raise ProcgenError(f"{name} must be in [0, 1]")
    w, h = hm.width, hm.height
    g = list(hm.cells)
    eroded = deposited = 0.0
    for _ in range(count):
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
        sediment = 0.0
        for _step in range(max_steps):
            i = y * w + x
            best, best_drop = None, 0.0
            for nx, ny in hm.neighbours(x, y, diagonal=True):
                d = g[i] - g[ny * w + nx]
                if d > best_drop:
                    best, best_drop = (nx, ny), d
            if best is None:  # pit: drop everything
                g[i] += sediment
                deposited += sediment
                sediment = 0.0
                break
            cap = capacity * best_drop
            if sediment > cap:
                drop = (sediment - cap) * deposit
                g[i] += drop
                deposited += drop
                sediment -= drop
            else:
                take = min((cap - sediment) * erode, best_drop * 0.5)
                g[i] -= take
                eroded += take
                sediment += take
            x, y = best
        else:
            i = y * w + x
            g[i] += sediment
            deposited += sediment
    return Heightmap(w, h, tuple(g)), eroded, deposited


def erode(hm: Heightmap, rng: DeterministicRng, *, thermal_iterations: int = 6, talus: float = 0.02,
          droplet_count: int = 200) -> tuple[Heightmap, ErosionReport]:
    t, moved = thermal(hm, iterations=thermal_iterations, talus=talus)
    d, er, de = droplets(t, rng, count=droplet_count)
    return d.normalized(), ErosionReport(moved, er, de, droplet_count)
