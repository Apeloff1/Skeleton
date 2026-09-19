"""Vertebra state: pose, dims binding, mobility flags."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Mapping

from skeleton.spine.dimensions import VertebraDims, dims_for
from skeleton.spine.taxonomy import CATALOG, Region, VertebraId, BY_LABEL, is_mobile


@dataclass(frozen=True, slots=True)
class Pose6:
    """SE(3)-lite: rotations (deg) + translations (mm)."""

    rx: float = 0.0  # flexion(+)/extension(-)
    ry: float = 0.0  # lateral bend
    rz: float = 0.0  # axial rotation
    tx: float = 0.0
    ty: float = 0.0
    tz: float = 0.0

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        return (self.rx, self.ry, self.rz, self.tx, self.ty, self.tz)

    def scaled(self, k: float) -> "Pose6":
        return Pose6(*(v * k for v in self.as_tuple()))

    def added(self, other: "Pose6") -> "Pose6":
        a, b = self.as_tuple(), other.as_tuple()
        return Pose6(*(a[i] + b[i] for i in range(6)))

    def norm(self) -> float:
        return sum(v * v for v in self.as_tuple()) ** 0.5

    def clamped(self, lo: "Pose6", hi: "Pose6") -> "Pose6":
        a, l, h = self.as_tuple(), lo.as_tuple(), hi.as_tuple()
        return Pose6(*(min(max(a[i], l[i]), h[i]) for i in range(6)))


ZERO_POSE = Pose6()


@dataclass(frozen=True, slots=True)
class Vertebra:
    """One vertebra in the chain."""

    vid: VertebraId
    dims: VertebraDims
    pose: Pose6 = ZERO_POSE
    fused: bool = False
    tags: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return self.vid.label

    @property
    def region(self) -> Region:
        return self.vid.region

    @property
    def mobile(self) -> bool:
        return is_mobile(self.label) and not self.fused

    def with_pose(self, pose: Pose6) -> "Vertebra":
        return replace(self, pose=pose)

    def with_tags(self, *tags: str) -> "Vertebra":
        return replace(self, tags=tuple(dict.fromkeys(self.tags + tags)))

    def digest_parts(self) -> tuple[str, ...]:
        p = self.pose
        return (
            self.label,
            f"{self.dims.height_mm:.3f}",
            f"{p.rx:.4f}",
            f"{p.ry:.4f}",
            f"{p.rz:.4f}",
            f"{p.tx:.4f}",
            f"{p.ty:.4f}",
            f"{p.tz:.4f}",
            "1" if self.fused else "0",
        )


def make_vertebra(label: str, pose: Pose6 | None = None, fused: bool | None = None) -> Vertebra:
    vid = BY_LABEL[label]
    if fused is None:
        fused = vid.region in (Region.SACRAL, Region.COCCYX)
    return Vertebra(vid=vid, dims=dims_for(vid), pose=pose or ZERO_POSE, fused=fused)


def default_column() -> tuple[Vertebra, ...]:
    return tuple(make_vertebra(v.label) for v in CATALOG)


def by_label(column: Iterable[Vertebra]) -> dict[str, Vertebra]:
    return {v.label: v for v in column}


def filter_region(column: Iterable[Vertebra], region: Region) -> list[Vertebra]:
    return [v for v in column if v.region is region]


def mobile_subset(column: Iterable[Vertebra]) -> list[Vertebra]:
    return [v for v in column if v.mobile]


def apply_pose_map(column: Iterable[Vertebra], poses: Mapping[str, Pose6]) -> tuple[Vertebra, ...]:
    out: list[Vertebra] = []
    for v in column:
        if v.label in poses:
            out.append(v.with_pose(poses[v.label]))
        else:
            out.append(v)
    return tuple(out)


def mean_pose(column: Iterable[Vertebra]) -> Pose6:
    items = list(column)
    if not items:
        return ZERO_POSE
    n = float(len(items))
    acc = [0.0] * 6
    for v in items:
        t = v.pose.as_tuple()
        for i in range(6):
            acc[i] += t[i]
    return Pose6(*(a / n for a in acc))


def pose_energy(column: Iterable[Vertebra], weights: tuple[float, ...] = (1, 1, 1, 0.1, 0.1, 0.1)) -> float:
    """Quadratic pose energy (neutral = 0)."""
    e = 0.0
    for v in column:
        t = v.pose.as_tuple()
        for i in range(6):
            e += weights[i] * t[i] * t[i]
    return e
