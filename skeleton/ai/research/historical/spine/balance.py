"""Center of mass and balance / equilibrium helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.chain import SpineChain
from skeleton.spine.dimensions import mass_proxy_g
from skeleton.spine.kinematics import Frame3, forward_frames


@dataclass(frozen=True, slots=True)
class Com3:
    x: float
    y: float
    z: float
    mass_g: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


def vertebra_com(chain: SpineChain) -> list[Com3]:
    frames = forward_frames(chain)
    out: list[Com3] = []
    for v, f in zip(chain.vertebrae, frames):
        m = mass_proxy_g(v.label)
        # COM at geometric center of body ≈ frame + half height along z
        out.append(Com3(f.x, f.y, f.z + v.dims.height_mm * 0.5, m))
    return out


def chain_com(chain: SpineChain) -> Com3:
    parts = vertebra_com(chain)
    mt = sum(p.mass_g for p in parts)
    if mt <= 0:
        return Com3(0, 0, 0, 0)
    x = sum(p.x * p.mass_g for p in parts) / mt
    y = sum(p.y * p.mass_g for p in parts) / mt
    z = sum(p.z * p.mass_g for p in parts) / mt
    return Com3(x, y, z, mt)


def plumb_offset_mm(chain: SpineChain) -> tuple[float, float]:
    """C7–S1 style horizontal offset of cranial vs caudal origins."""
    frames = forward_frames(chain)
    # C7 ordinal = 6, S1 ordinal = 24
    c7, s1 = frames[6], frames[24]
    return (c7.x - s1.x, c7.y - s1.y)


def balance_score(chain: SpineChain) -> float:
    """0 = perfect plumb; grows with offset magnitude."""
    dx, dy = plumb_offset_mm(chain)
    return (dx * dx + dy * dy) ** 0.5


def support_polygon_ok(chain: SpineChain, half_width_mm: float = 50.0) -> bool:
    com = chain_com(chain)
    return abs(com.x) <= half_width_mm and abs(com.y) <= half_width_mm


def sagittal_vertical_axis(chain: SpineChain) -> float:
    """SVA-like: horizontal offset of C7 from sacral posterior (x)."""
    dx, _ = plumb_offset_mm(chain)
    return dx
