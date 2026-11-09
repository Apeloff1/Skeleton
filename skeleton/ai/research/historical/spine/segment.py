"""Intervertebral segment: disc + facet pair between two vertebrae."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Sequence

from skeleton.spine.law import SEGMENT_N, VERTEBRA_N
from skeleton.spine.taxonomy import CATALOG, Region, region_of
from skeleton.spine.vertebra import Pose6, ZERO_POSE, Vertebra


@dataclass(frozen=True, slots=True)
class SegmentId:
    cranial: str
    caudal: str
    index: int  # 0-based along chain

    @property
    def label(self) -> str:
        return f"{self.cranial}-{self.caudal}"


@dataclass(frozen=True, slots=True)
class DiscProps:
    height_mm: float
    radius_mm: float
    young_mpa: float  # effective compressive modulus
    shear_mpa: float

    @property
    def area_mm2(self) -> float:
        return 3.141592653589793 * self.radius_mm * self.radius_mm

    def axial_stiffness_n_per_mm(self) -> float:
        # k = EA / L ; convert MPa*mm^2 / mm -> N/mm
        return (self.young_mpa * self.area_mm2) / max(self.height_mm, 0.1)


@dataclass(frozen=True, slots=True)
class Segment:
    sid: SegmentId
    disc: DiscProps
    relative: Pose6 = ZERO_POSE
    locked: bool = False

    @property
    def label(self) -> str:
        return self.sid.label

    def with_relative(self, pose: Pose6) -> "Segment":
        return replace(self, relative=pose)


def _disc_for(cranial: str, caudal: str) -> DiscProps:
    r = region_of(cranial)
    if r is Region.CERVICAL:
        return DiscProps(5.0, 8.0, 8.0, 2.0)
    if r is Region.THORACIC:
        return DiscProps(4.0, 12.0, 10.0, 2.5)
    if r is Region.LUMBAR:
        return DiscProps(10.0, 18.0, 12.0, 3.0)
    if r is Region.SACRAL:
        return DiscProps(1.0, 15.0, 50.0, 10.0)
    return DiscProps(0.5, 5.0, 40.0, 8.0)


def build_segments(column: Sequence[Vertebra] | None = None) -> tuple[Segment, ...]:
    if column is None:
        labels = [v.label for v in CATALOG]
    else:
        labels = [v.label for v in column]
    if len(labels) != VERTEBRA_N:
        raise ValueError(f"need {VERTEBRA_N} vertebrae, got {len(labels)}")
    segs: list[Segment] = []
    for i in range(len(labels) - 1):
        cr, ca = labels[i], labels[i + 1]
        locked = region_of(cr) in (Region.SACRAL, Region.COCCYX) and region_of(ca) in (
            Region.SACRAL,
            Region.COCCYX,
        )
        segs.append(
            Segment(
                sid=SegmentId(cranial=cr, caudal=ca, index=i),
                disc=_disc_for(cr, ca),
                locked=locked,
            )
        )
    if len(segs) != SEGMENT_N:
        raise RuntimeError(f"segment count {len(segs)} != {SEGMENT_N}")
    return tuple(segs)


def segment_by_label(segments: Iterable[Segment]) -> dict[str, Segment]:
    return {s.label: s for s in segments}


def mobile_segments(segments: Iterable[Segment]) -> list[Segment]:
    return [s for s in segments if not s.locked]


def total_disc_height_mm(segments: Iterable[Segment]) -> float:
    return round(sum(s.disc.height_mm for s in segments), 3)


def mean_axial_stiffness(segments: Iterable[Segment]) -> float:
    mob = mobile_segments(segments)
    if not mob:
        return 0.0
    return sum(s.disc.axial_stiffness_n_per_mm() for s in mob) / len(mob)


def apply_relative_map(
    segments: Sequence[Segment], relatives: dict[str, Pose6]
) -> tuple[Segment, ...]:
    out: list[Segment] = []
    for s in segments:
        if s.label in relatives and not s.locked:
            out.append(s.with_relative(relatives[s.label]))
        else:
            out.append(s)
    return tuple(out)


def segment_index_of(cranial: str, caudal: str, segments: Sequence[Segment]) -> int:
    for s in segments:
        if s.sid.cranial == cranial and s.sid.caudal == caudal:
            return s.sid.index
    raise KeyError(f"{cranial}-{caudal}")
