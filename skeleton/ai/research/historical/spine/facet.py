"""Zygapophyseal (facet) joint contact and orientation helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.segment import Segment
from skeleton.spine.taxonomy import Region, region_of
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class FacetPair:
    segment: str
    angle_deg: float  # facet plane vs transverse
    area_mm2: float
    gap_mm: float


# Typical facet orientations
_FACET_ANGLE: dict[Region, float] = {
    Region.CERVICAL: 45.0,
    Region.THORACIC: 60.0,
    Region.LUMBAR: 90.0,  # sagittal
    Region.SACRAL: 90.0,
    Region.COCCYX: 90.0,
}

_FACET_AREA: dict[Region, float] = {
    Region.CERVICAL: 80.0,
    Region.THORACIC: 100.0,
    Region.LUMBAR: 160.0,
    Region.SACRAL: 120.0,
    Region.COCCYX: 40.0,
}


def facet_for(seg: Segment) -> FacetPair:
    r = region_of(seg.sid.cranial)
    # gap closes with extension (negative rx in our convention? use abs)
    gap = max(0.0, 1.5 - 0.05 * abs(seg.relative.rx) - 0.03 * abs(seg.relative.ry))
    return FacetPair(seg.label, _FACET_ANGLE[r], _FACET_AREA[r], gap)


def contact_force_n(facet: FacetPair, extension_share_n: float) -> float:
    """Portion of load through facets when gap closed."""
    if facet.gap_mm > 0.2:
        return 0.0
    # more load as gap → 0
    close = max(0.0, 1.0 - facet.gap_mm / 0.2)
    return extension_share_n * close


def guides_rotation(facet: FacetPair, pose: Pose6) -> float:
    """Penalty for rotation against facet orientation."""
    # lumbar sagittal facets resist rotation
    resist = abs(math.sin(math.radians(facet.angle_deg)))
    return resist * abs(pose.rz)


def facet_map(segments: Sequence[Segment]) -> dict[str, FacetPair]:
    return {s.label: facet_for(s) for s in segments}


def total_facet_load(segments: Sequence[Segment], axial_n: float, share: float = 0.15) -> float:
    return sum(contact_force_n(facet_for(s), axial_n * share) for s in segments if not s.locked)


def facet_ok(seg: Segment, max_force_n: float = 800.0, axial_n: float = 400.0) -> bool:
    f = facet_for(seg)
    return contact_force_n(f, axial_n * 0.2) <= max_force_n and f.gap_mm >= 0.0
