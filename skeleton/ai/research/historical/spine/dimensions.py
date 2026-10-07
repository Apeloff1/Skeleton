"""Geometric dimensions (mm) for each vertebra. Deterministic tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from skeleton.spine.taxonomy import CATALOG, Region, VertebraId, region_of


@dataclass(frozen=True, slots=True)
class VertebraDims:
    """Body height, AP depth, ML width, pedicle width (mm)."""

    height_mm: float
    depth_mm: float
    width_mm: float
    pedicle_mm: float

    @property
    def volume_approx_mm3(self) -> float:
        # Ellipsoid approximation of vertebral body
        return (4.0 / 3.0) * 3.141592653589793 * (self.width_mm / 2.0) * (
            self.depth_mm / 2.0
        ) * (self.height_mm / 2.0)

    @property
    def cross_section_mm2(self) -> float:
        return 3.141592653589793 * (self.width_mm / 2.0) * (self.depth_mm / 2.0)


# Base dimensions by region (population means, simplified)
_BASE: dict[Region, VertebraDims] = {
    Region.CERVICAL: VertebraDims(14.0, 16.0, 22.0, 5.0),
    Region.THORACIC: VertebraDims(18.0, 28.0, 30.0, 7.0),
    Region.LUMBAR: VertebraDims(25.0, 35.0, 45.0, 10.0),
    Region.SACRAL: VertebraDims(20.0, 30.0, 50.0, 8.0),
    Region.COCCYX: VertebraDims(8.0, 10.0, 12.0, 3.0),
}

# Gradients: caudal vertebrae within a region grow slightly
_HEIGHT_STEP: dict[Region, float] = {
    Region.CERVICAL: 0.4,
    Region.THORACIC: 0.35,
    Region.LUMBAR: 0.5,
    Region.SACRAL: -0.3,
    Region.COCCYX: -0.5,
}


def dims_for(vid: VertebraId) -> VertebraDims:
    base = _BASE[vid.region]
    step = _HEIGHT_STEP[vid.region]
    k = vid.index - 1
    return VertebraDims(
        height_mm=round(base.height_mm + k * step, 3),
        depth_mm=round(base.depth_mm + k * step * 0.6, 3),
        width_mm=round(base.width_mm + k * step * 0.8, 3),
        pedicle_mm=round(base.pedicle_mm + k * 0.15, 3),
    )


def dims_by_label(label: str) -> VertebraDims:
    from skeleton.spine.taxonomy import BY_LABEL

    return dims_for(BY_LABEL[label])


def all_dims() -> dict[str, VertebraDims]:
    return {v.label: dims_for(v) for v in CATALOG}


def total_column_height_mm() -> float:
    """Sum of body heights plus nominal disc heights (interbody)."""
    bodies = sum(dims_for(v).height_mm for v in CATALOG)
    # Disc height approx: cervical 5, thoracic 4, lumbar 10, sacral/coccyx fused ~0
    disc = 0.0
    for v in CATALOG[:-1]:
        r = v.region
        if r is Region.CERVICAL:
            disc += 5.0
        elif r is Region.THORACIC:
            disc += 4.0
        elif r is Region.LUMBAR:
            disc += 10.0
        else:
            disc += 0.5
    return round(bodies + disc, 3)


def mass_proxy_g(label: str, density_g_cm3: float = 1.1) -> float:
    """Rough vertebral mass from ellipsoid volume."""
    d = dims_by_label(label)
    vol_cm3 = d.volume_approx_mm3 / 1000.0
    return round(vol_cm3 * density_g_cm3, 4)


def region_height_mm(region: Region) -> float:
    from skeleton.spine.taxonomy import labels_in_region

    return round(sum(dims_by_label(lb).height_mm for lb in labels_in_region(region)), 3)


def assert_monotonic_lumbar_widths() -> bool:
    """Lumbar widths should increase caudalward."""
    from skeleton.spine.taxonomy import labels_in_region

    widths = [dims_by_label(lb).width_mm for lb in labels_in_region(Region.LUMBAR)]
    return all(widths[i] <= widths[i + 1] + 1e-9 for i in range(len(widths) - 1))


def dimension_card_payload() -> Mapping[str, float]:
    return {
        "column_height_mm": total_column_height_mm(),
        "cervical_h": region_height_mm(Region.CERVICAL),
        "thoracic_h": region_height_mm(Region.THORACIC),
        "lumbar_h": region_height_mm(Region.LUMBAR),
        "n": float(len(CATALOG)),
    }
