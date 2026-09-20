"""Axial load paths: force/moment transmission cranial→caudal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.chain import SpineChain
from skeleton.spine.law import MAX_LOAD_N, SEGMENT_N
from skeleton.spine.segment import Segment
from skeleton.spine.vertebra import Vertebra


@dataclass(frozen=True, slots=True)
class LoadSample:
    """Force (N) and moment (N·mm) at a station."""

    fx: float
    fy: float
    fz: float  # axial compression positive
    mx: float
    my: float
    mz: float

    def force_norm(self) -> float:
        return (self.fx ** 2 + self.fy ** 2 + self.fz ** 2) ** 0.5

    def moment_norm(self) -> float:
        return (self.mx ** 2 + self.my ** 2 + self.mz ** 2) ** 0.5

    def as_tuple(self) -> tuple[float, ...]:
        return (self.fx, self.fy, self.fz, self.mx, self.my, self.mz)

    def added(self, other: "LoadSample") -> "LoadSample":
        a, b = self.as_tuple(), other.as_tuple()
        return LoadSample(*(a[i] + b[i] for i in range(6)))

    def scaled(self, k: float) -> "LoadSample":
        return LoadSample(*(v * k for v in self.as_tuple()))


ZERO_LOAD = LoadSample(0, 0, 0, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class LoadPath:
    """Per-vertebra stations + per-segment transmissions."""

    stations: tuple[LoadSample, ...]  # len = VERTEBRA_N
    segment_loads: tuple[LoadSample, ...]  # len = SEGMENT_N
    cranial_applied: LoadSample

    def residual(self) -> float:
        """Kirchhoff-like residual: station[i] should equal segment[i-1] outflow."""
        if not self.stations:
            return 0.0
        err = 0.0
        # station 0 ≈ cranial_applied
        for a, b in zip(self.stations[0].as_tuple(), self.cranial_applied.as_tuple()):
            err += abs(a - b)
        for i, seg_l in enumerate(self.segment_loads):
            # outflow of station i through segment i arrives at station i+1
            # (no body forces in base model → stations equal along path)
            for a, b in zip(self.stations[i + 1].as_tuple(), seg_l.as_tuple()):
                err += abs(a - b)
        return err


def body_weight_contribution(vertebra: Vertebra, total_head_n: float = 50.0) -> float:
    """Approximate additional axial load from local mass (scaled)."""
    # mass_proxy roughly proportional to volume; convert to weight contribution
    from skeleton.spine.dimensions import mass_proxy_g

    g = mass_proxy_g(vertebra.label)
    return (g / 1000.0) * 9.81  # kg * g


def build_axial_path(
    chain: SpineChain,
    cranial_fz: float = 100.0,
    include_body_weights: bool = True,
) -> LoadPath:
    """Propagate axial compression with optional body-weight increments."""
    if cranial_fz > MAX_LOAD_N or cranial_fz < 0:
        raise ValueError("load-ceiling")
    applied = LoadSample(0, 0, cranial_fz, 0, 0, 0)
    stations: list[LoadSample] = []
    seg_loads: list[LoadSample] = []
    current = cranial_fz
    for i, v in enumerate(chain.vertebrae):
        stations.append(LoadSample(0, 0, current, 0, 0, 0))
        if i < len(chain.segments):
            if include_body_weights:
                current += body_weight_contribution(v)
            if current > MAX_LOAD_N:
                raise ValueError("load-ceiling-propagate")
            seg_loads.append(LoadSample(0, 0, current, 0, 0, 0))
    return LoadPath(
        stations=tuple(stations),
        segment_loads=tuple(seg_loads),
        cranial_applied=applied,
    )


def build_eccentric_path(
    chain: SpineChain,
    cranial_fz: float,
    lever_mm: float,
    plane: str = "sagittal",
) -> LoadPath:
    """Axial load with bending moment from eccentricity."""
    base = build_axial_path(chain, cranial_fz, include_body_weights=False)
    stations: list[LoadSample] = []
    seg_loads: list[LoadSample] = []
    for s in base.stations:
        if plane == "sagittal":
            stations.append(LoadSample(s.fx, s.fy, s.fz, s.fz * lever_mm, 0, 0))
        elif plane == "coronal":
            stations.append(LoadSample(s.fx, s.fy, s.fz, 0, s.fz * lever_mm, 0))
        else:
            raise ValueError("plane")
    for s in base.segment_loads:
        if plane == "sagittal":
            seg_loads.append(LoadSample(s.fx, s.fy, s.fz, s.fz * lever_mm, 0, 0))
        else:
            seg_loads.append(LoadSample(s.fx, s.fy, s.fz, 0, s.fz * lever_mm, 0))
    cranial = stations[0] if stations else ZERO_LOAD
    return LoadPath(tuple(stations), tuple(seg_loads), cranial)


def peak_axial(path: LoadPath) -> float:
    return max(s.fz for s in path.stations)


def peak_moment(path: LoadPath) -> float:
    return max(s.moment_norm() for s in path.stations)


def is_conserved(path: LoadPath, tol: float = 1e-6) -> bool:
    """Without body weights, all stations share the same axial load."""
    if not path.stations:
        return True
    f0 = path.cranial_applied.fz
    return all(abs(s.fz - f0) <= tol for s in path.stations)


def shear_components(path: LoadPath) -> list[float]:
    return [(s.fx ** 2 + s.fy ** 2) ** 0.5 for s in path.stations]


def safety_factor(path: LoadPath, ultimate_n: float = 4000.0) -> float:
    peak = peak_axial(path)
    if peak <= 0:
        return float("inf")
    return ultimate_n / peak


def load_card_payload(path: LoadPath) -> dict[str, float]:
    return {
        "peak_axial": peak_axial(path),
        "peak_moment": peak_moment(path),
        "residual": path.residual(),
        "safety": safety_factor(path),
        "n_stations": float(len(path.stations)),
    }


def assert_segment_count(path: LoadPath) -> None:
    if len(path.segment_loads) != SEGMENT_N:
        raise AssertionError("segment_loads_n")
