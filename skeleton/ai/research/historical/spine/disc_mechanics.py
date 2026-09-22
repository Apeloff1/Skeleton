"""Intervertebral disc constitutive helpers and creep/relaxation proxies."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.segment import DiscProps, Segment
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class DiscState:
    segment: str
    pressure_mpa: float
    height_mm: float
    hydration: float  # 0..1
    damage: float  # 0..1


def hydrostatic_pressure(disc: DiscProps, axial_n: float) -> float:
    return axial_n / max(disc.area_mm2, 1.0)


def height_under_load(disc: DiscProps, axial_n: float) -> float:
    """Linear spring height reduction; clamped to 50% of unloaded."""
    k = disc.axial_stiffness_n_per_mm()
    delta = axial_n / max(k, 1e-9)
    return max(disc.height_mm * 0.5, disc.height_mm - delta)


def poisson_radial_strain(disc: DiscProps, axial_strain: float, nu: float = 0.45) -> float:
    return -nu * axial_strain


def axial_strain(disc: DiscProps, axial_n: float) -> float:
    h1 = height_under_load(disc, axial_n)
    return (h1 - disc.height_mm) / max(disc.height_mm, 1e-9)


def bulging_mm(disc: DiscProps, axial_n: float) -> float:
    eps_a = axial_strain(disc, axial_n)
    eps_r = poisson_radial_strain(disc, eps_a)
    return disc.radius_mm * abs(eps_r)


def creep_height(disc: DiscProps, axial_n: float, hours: float, tau_h: float = 4.0) -> float:
    """Exponential creep toward loaded height."""
    h_inf = height_under_load(disc, axial_n)
    h0 = disc.height_mm
    return h_inf + (h0 - h_inf) * math.exp(-hours / tau_h)


def recovery_height(h_crept: float, disc: DiscProps, hours: float, tau_h: float = 6.0) -> float:
    return disc.height_mm + (h_crept - disc.height_mm) * math.exp(-hours / tau_h)


def fatigue_damage(cycles: int, stress_mpa: float, ultimate_mpa: float = 5.0, b: float = 4.0) -> float:
    """Simple Basquin-like damage accumulation (not for clinical use)."""
    if stress_mpa <= 0 or ultimate_mpa <= 0:
        return 0.0
    ratio = stress_mpa / ultimate_mpa
    n_f = (1.0 / max(ratio, 1e-6)) ** b * 1e6
    return min(1.0, cycles / max(n_f, 1.0))


def disc_state(seg: Segment, axial_n: float, hydration: float = 0.8) -> DiscState:
    p = hydrostatic_pressure(seg.disc, axial_n)
    h = height_under_load(seg.disc, axial_n)
    # hydration modulates effective pressure
    p_eff = p / max(hydration, 0.2)
    dmg = 0.0 if p_eff < 2.0 else min(1.0, (p_eff - 2.0) / 5.0)
    return DiscState(seg.label, p_eff, h, hydration, dmg)


def diurnal_cycle(
    seg: Segment, day_load_n: float, night_hours: float = 8.0, day_hours: float = 16.0
) -> tuple[float, float]:
    """Return (end_of_day_height, end_of_night_height)."""
    h_day = creep_height(seg.disc, day_load_n, day_hours)
    h_night = recovery_height(h_day, seg.disc, night_hours)
    return h_day, h_night


def shear_from_pose(seg: Segment, pose: Pose6) -> float:
    """Approximate shear strain from translational DOF."""
    return math.sqrt(pose.tx ** 2 + pose.ty ** 2) / max(seg.disc.height_mm, 0.1)


def combined_risk(seg: Segment, axial_n: float, pose: Pose6) -> float:
    st = disc_state(seg, axial_n)
    shear = shear_from_pose(seg, pose)
    return st.damage + 0.2 * shear + 0.1 * abs(pose.rx) / 20.0


def rank_discs_by_risk(
    segments: Sequence[Segment], axial_loads: Sequence[float], poses: Sequence[Pose6] | None = None
) -> list[tuple[str, float]]:
    poses = poses or [s.relative for s in segments]
    scored = [
        (s.label, combined_risk(s, load, pose))
        for s, load, pose in zip(segments, axial_loads, poses)
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def hydrate_modulate(disc: DiscProps, hydration: float) -> DiscProps:
    """Scale moduli with hydration."""
    f = 0.5 + 0.5 * max(0.0, min(1.0, hydration))
    return DiscProps(
        disc.height_mm,
        disc.radius_mm,
        disc.young_mpa * f,
        disc.shear_mpa * f,
    )
