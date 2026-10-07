"""Stress / pressure estimates on discs and vertebral bodies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.chain import SpineChain
from skeleton.spine.load_path import LoadPath, LoadSample
from skeleton.spine.segment import Segment


@dataclass(frozen=True, slots=True)
class DiscStress:
    segment: str
    pressure_mpa: float
    shear_mpa: float
    moment_mpa_mm: float

    @property
    def ok(self) -> bool:
        # Soft tissue / disc pressure heuristic ceilings
        return self.pressure_mpa < 5.0 and self.shear_mpa < 2.0


@dataclass(frozen=True, slots=True)
class BodyStress:
    label: str
    compressive_mpa: float
    ok: bool


def disc_pressure(seg: Segment, load: LoadSample) -> DiscStress:
    area = max(seg.disc.area_mm2, 1.0)
    # N / mm^2 = MPa
    pressure = load.fz / area
    shear = ((load.fx ** 2 + load.fy ** 2) ** 0.5) / area
    moment = load.moment_norm() / area
    return DiscStress(seg.label, pressure, shear, moment)


def body_stress(chain: SpineChain, path: LoadPath) -> list[BodyStress]:
    out: list[BodyStress] = []
    for v, load in zip(chain.vertebrae, path.stations):
        area = max(v.dims.cross_section_mm2, 1.0)
        p = load.fz / area
        # cortical bone compressive strength ~150 MPa; trabecular much less —
        # use 20 MPa as conservative cancellous ceiling
        out.append(BodyStress(v.label, p, p < 20.0))
    return out


def all_disc_stresses(chain: SpineChain, path: LoadPath) -> list[DiscStress]:
    return [
        disc_pressure(seg, load)
        for seg, load in zip(chain.segments, path.segment_loads)
    ]


def worst_disc(stresses: Sequence[DiscStress]) -> DiscStress | None:
    if not stresses:
        return None
    return max(stresses, key=lambda s: s.pressure_mpa)


def stress_ok(chain: SpineChain, path: LoadPath) -> bool:
    discs = all_disc_stresses(chain, path)
    bodies = body_stress(chain, path)
    return all(d.ok for d in discs) and all(b.ok for b in bodies)


def pressure_profile(chain: SpineChain, path: LoadPath) -> list[tuple[str, float]]:
    return [(d.segment, d.pressure_mpa) for d in all_disc_stresses(chain, path)]


def mean_disc_pressure(chain: SpineChain, path: LoadPath) -> float:
    discs = all_disc_stresses(chain, path)
    if not discs:
        return 0.0
    return sum(d.pressure_mpa for d in discs) / len(discs)


def nachemson_estimate(body_weight_n: float, posture: str = "standing") -> float:
    """Classic Nachemson-style L3 disc pressure multipliers."""
    mult = {
        "lying": 0.25,
        "standing": 1.0,
        "sitting": 1.4,
        "forward_bend": 2.2,
        "lift_20kg": 3.5,
    }.get(posture, 1.0)
    return body_weight_n * mult
