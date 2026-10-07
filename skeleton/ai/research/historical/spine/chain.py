"""Ordered vertebral chain: primary spine topology container."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterator, Mapping, Sequence

from skeleton.spine.law import SEGMENT_N, VERTEBRA_N
from skeleton.spine.segment import Segment, build_segments, mobile_segments
from skeleton.spine.taxonomy import Region, junction_labels
from skeleton.spine.vertebra import (
    Pose6,
    Vertebra,
    apply_pose_map,
    by_label,
    default_column,
    filter_region,
    mean_pose,
    pose_energy,
)


@dataclass(frozen=True, slots=True)
class SpineChain:
    """Immutable cranial→caudal chain with matching segments."""

    vertebrae: tuple[Vertebra, ...]
    segments: tuple[Segment, ...]
    name: str = "default"

    def __post_init__(self) -> None:
        if len(self.vertebrae) != VERTEBRA_N:
            raise ValueError("vertebra_n")
        if len(self.segments) != SEGMENT_N:
            raise ValueError("segment_n")
        for i, seg in enumerate(self.segments):
            if seg.sid.cranial != self.vertebrae[i].label:
                raise ValueError(f"seg cranial mismatch at {i}")
            if seg.sid.caudal != self.vertebrae[i + 1].label:
                raise ValueError(f"seg caudal mismatch at {i}")

    def __len__(self) -> int:
        return len(self.vertebrae)

    def __iter__(self) -> Iterator[Vertebra]:
        return iter(self.vertebrae)

    def labels(self) -> list[str]:
        return [v.label for v in self.vertebrae]

    def get(self, label: str) -> Vertebra:
        return by_label(self.vertebrae)[label]

    def region(self, region: Region) -> list[Vertebra]:
        return filter_region(self.vertebrae, region)

    def with_poses(self, poses: Mapping[str, Pose6]) -> "SpineChain":
        return replace(self, vertebrae=apply_pose_map(self.vertebrae, poses))

    def with_name(self, name: str) -> "SpineChain":
        return replace(self, name=name)

    def mobile_segment_count(self) -> int:
        return len(mobile_segments(self.segments))

    def energy(self) -> float:
        return pose_energy(self.vertebrae)

    def mean_pose(self) -> Pose6:
        return mean_pose(self.vertebrae)

    def junctions(self) -> list[tuple[str, str]]:
        return junction_labels()

    def cranial(self) -> Vertebra:
        return self.vertebrae[0]

    def caudal(self) -> Vertebra:
        return self.vertebrae[-1]

    def slice_ordinals(self, start: int, end: int) -> tuple[Vertebra, ...]:
        if start < 0 or end >= VERTEBRA_N or start > end:
            raise IndexError("slice")
        return self.vertebrae[start : end + 1]


def default_chain(name: str = "default") -> SpineChain:
    col = default_column()
    segs = build_segments(col)
    return SpineChain(vertebrae=col, segments=segs, name=name)


def assert_chain_integrity(chain: SpineChain) -> None:
    labels = chain.labels()
    if len(set(labels)) != VERTEBRA_N:
        raise AssertionError("duplicate labels")
    for i in range(SEGMENT_N):
        s = chain.segments[i]
        if s.sid.index != i:
            raise AssertionError("segment index")
        if labels[i] != s.sid.cranial or labels[i + 1] != s.sid.caudal:
            raise AssertionError("segment endpoints")


def chain_height_mm(chain: SpineChain) -> float:
    bodies = sum(v.dims.height_mm for v in chain.vertebrae)
    discs = sum(s.disc.height_mm for s in chain.segments)
    return round(bodies + discs, 3)


def rebind_segments(chain: SpineChain, segments: Sequence[Segment]) -> SpineChain:
    return SpineChain(vertebrae=chain.vertebrae, segments=tuple(segments), name=chain.name)
