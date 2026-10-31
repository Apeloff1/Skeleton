"""Mass-distribution, balance and dynamic loading for skeleton game characters.

All positions and forces are SI. Body mass is derived from segment weights,
COM and inertia about the resulting center. The floor support polygon uses a
convex hull rather than an invented sum-of-weights balancing score. This is
a CPU candidate reference; authoritative physics remains the host engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math

from .game_frontier_production import Vec3


class BodyBalanceError(ValueError):
    pass


def finite(v: float, name: str, low: float, high: float) -> float:
    if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
        raise BodyBalanceError(f"{name} outside finite bounds")
    return float(v)


@dataclass(frozen=True)
class BodyMass:
    segment_id: str
    mass_kg: float
    location: Vec3
    bulk_radius_m: float = .1
    carried: bool = False

    def __post_init__(self) -> None:
        if not self.segment_id or len(self.segment_id) > 128:
            raise BodyBalanceError("segment identity required")
        finite(self.mass_kg, "segment mass", .001, 100000)
        finite(self.bulk_radius_m, "bulk radius", .001, 100)


@dataclass(frozen=True)
class SupportFoot:
    foot_id: str
    position: Vec3
    capacity_n: float
    friction_coefficient: float

    def __post_init__(self) -> None:
        if not self.foot_id or len(self.foot_id) > 128:
            raise BodyBalanceError("foot ID required")
        finite(self.capacity_n, "support capacity", 0, 1e7)
        finite(self.friction_coefficient, "support friction", 0, 3)


@dataclass(frozen=True)
class LoadDistribution:
    total_mass_kg: float
    carried_mass_kg: float
    center_of_mass: Vec3
    inertia_tensor_kg_m2: tuple[tuple[float, float, float], ...]
    effective_balance_point: Vec3
    support_margin_m: float
    stable: bool
    load_per_foot_n: tuple[tuple[str, float], ...]
    available_tangential_grip_n: float
    required_tangential_force_n: float
    momentum_kg_m_s: Vec3
    pitch_torque_nm: float
    roll_torque_nm: float
    evidence_digest: str
    authority: str = "reference_mass_balance_not_native_solver"


def _cross(o: tuple[float, float], a: tuple[float, float],
           b: tuple[float, float]) -> float:
    return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])


def _hull(points: tuple[tuple[float, float], ...]) -> list[tuple[float, float]]:
    ordered = sorted(set(points))
    if len(ordered) < 3:
        raise BodyBalanceError("support needs three non-collinear points")
    lower = []
    for p in ordered:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(ordered):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        raise BodyBalanceError("collinear stance cannot create an area")
    return hull


def _polygon_margin(point: tuple[float, float],
                    hull: list[tuple[float, float]]) -> float:
    distances = []
    for a, b in zip(hull, hull[1:] + hull[:1]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        edge_len = math.hypot(dx, dy)
        if edge_len <= 1e-9:
            continue
        distances.append(_cross(a, b, point) / edge_len)
    return min(distances) if distances else -1e9


def distribute_character_weight(
    segments: tuple[BodyMass, ...], supports: tuple[SupportFoot, ...], *,
    acceleration_mps2: Vec3 = Vec3(0, 0, 0),
    velocity_mps: Vec3 = Vec3(0, 0, 0),
    ground_z_m: float = 0.,
    gravity_mps2: float = 9.80665,
) -> LoadDistribution:
    """Calculate COM, inertia tensor, support margin and per-foot load.

    Load sharing uses a normalized nearest-support inverse-distance weighting.
    True contact forces require constrained multi-contact engine solving.
    """
    if not 1 <= len(segments) <= 256 or not 3 <= len(supports) <= 32:
        raise BodyBalanceError("1..256 segments and 3..32 support points required")
    if len({s.segment_id for s in segments}) != len(segments):
        raise BodyBalanceError("duplicate body segments")
    if len({f.foot_id for f in supports}) != len(supports):
        raise BodyBalanceError("duplicate supports")
    finite(gravity_mps2, "gravity", .001, 100)
    finite(ground_z_m, "ground elevation", -1e5, 1e5)
    total = sum(s.mass_kg for s in segments)
    carried = sum(s.mass_kg for s in segments if s.carried)
    center = Vec3(sum(s.location.x*s.mass_kg for s in segments)/total,
                  sum(s.location.y*s.mass_kg for s in segments)/total,
                  sum(s.location.z*s.mass_kg for s in segments)/total)
    xx=yy=zz=xy=xz=yz=0.
    for mass in segments:
        p = mass.location - center
        m = mass.mass_kg
        intrinsic = .4*m*mass.bulk_radius_m**2
        xx += m*(p.y**2 + p.z**2)+intrinsic
        yy += m*(p.x**2 + p.z**2)+intrinsic
        zz += m*(p.x**2 + p.y**2)+intrinsic
        xy -= m*p.x*p.y
        xz -= m*p.x*p.z
        yz -= m*p.y*p.z
    inertia = ((xx,xy,xz),(xy,yy,yz),(xz,yz,zz))
    height = max(0., center.z-ground_z_m)
    # Required acceleration leans effective center of pressure opposite
    # its force vector (quasi-static inverted-pendulum approximation).
    shift = acceleration_mps2.scaled(-height/gravity_mps2)
    balance = Vec3(center.x+shift.x,center.y+shift.y,ground_z_m)
    hull = _hull(tuple((s.position.x,s.position.y) for s in supports))
    margin = _polygon_margin((balance.x,balance.y),hull)
    loads = [1 / max(.05, math.hypot(balance.x-f.position.x,
                                     balance.y-f.position.y)) for f in supports]
    norm = sum(loads)
    weighted = tuple((f.foot_id,total*gravity_mps2*w/norm)
                     for f,w in zip(supports,loads))
    available = sum(f.friction_coefficient*force for f,(_,force) in zip(supports,weighted))
    requested = total*math.hypot(acceleration_mps2.x,acceleration_mps2.y)
    stable = margin >= -1e-8 and requested <= available + 1e-8 and (
        all(force <= f.capacity_n for f,(_,force) in zip(supports,weighted)))
    evidence = {
        "total":total,"carried":carried,"com":(center.x,center.y,center.z),
        "inertia":inertia,"balance":(balance.x,balance.y,balance.z),
        "margin":margin,"load":weighted,
        "grip":available,"required":requested,"stable":stable,
    }
    digest=sha256(json.dumps(evidence,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return LoadDistribution(
        total,carried,center,inertia,balance,margin,stable,weighted,
        available,requested,velocity_mps.scaled(total),
        total*acceleration_mps2.x*height,
        total*acceleration_mps2.y*height,
        digest,
    )
