"""Vertebra taxonomy: C1-C7, T1-T12, L1-L5, S1-S5, Co1-Co4."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from skeleton.spine.law import (
    CERVICAL_N,
    COCCYX_N,
    LUMBAR_N,
    SACRAL_N,
    THORACIC_N,
    VERTEBRA_N,
)


class Region(str, Enum):
    CERVICAL = "cervical"
    THORACIC = "thoracic"
    LUMBAR = "lumbar"
    SACRAL = "sacral"
    COCCYX = "coccyx"


REGION_COUNTS: dict[Region, int] = {
    Region.CERVICAL: CERVICAL_N,
    Region.THORACIC: THORACIC_N,
    Region.LUMBAR: LUMBAR_N,
    Region.SACRAL: SACRAL_N,
    Region.COCCYX: COCCYX_N,
}

REGION_ORDER: tuple[Region, ...] = (
    Region.CERVICAL,
    Region.THORACIC,
    Region.LUMBAR,
    Region.SACRAL,
    Region.COCCYX,
)

PREFIX: dict[Region, str] = {
    Region.CERVICAL: "C",
    Region.THORACIC: "T",
    Region.LUMBAR: "L",
    Region.SACRAL: "S",
    Region.COCCYX: "Co",
}


@dataclass(frozen=True, slots=True)
class VertebraId:
    """Canonical vertebra identity."""

    region: Region
    index: int  # 1-based within region
    ordinal: int  # 0-based along full chain cranial→caudal

    @property
    def label(self) -> str:
        return f"{PREFIX[self.region]}{self.index}"

    def __str__(self) -> str:
        return self.label


def _build_catalog() -> tuple[VertebraId, ...]:
    out: list[VertebraId] = []
    ordinal = 0
    for region in REGION_ORDER:
        for i in range(1, REGION_COUNTS[region] + 1):
            out.append(VertebraId(region=region, index=i, ordinal=ordinal))
            ordinal += 1
    if len(out) != VERTEBRA_N:
        raise RuntimeError(f"catalog size {len(out)} != {VERTEBRA_N}")
    return tuple(out)


CATALOG: tuple[VertebraId, ...] = _build_catalog()
BY_LABEL: dict[str, VertebraId] = {v.label: v for v in CATALOG}
BY_ORDINAL: dict[int, VertebraId] = {v.ordinal: v for v in CATALOG}


def all_labels() -> list[str]:
    return [v.label for v in CATALOG]


def region_of(label: str) -> Region:
    return BY_LABEL[label].region


def ordinal_of(label: str) -> int:
    return BY_LABEL[label].ordinal


def labels_in_region(region: Region) -> list[str]:
    return [v.label for v in CATALOG if v.region is region]


def region_span(region: Region) -> tuple[int, int]:
    """Inclusive ordinal span (start, end) for a region."""
    members = [v.ordinal for v in CATALOG if v.region is region]
    return members[0], members[-1]


def is_mobile(label: str) -> bool:
    """True for movable (non-fused) vertebrae: C/T/L only."""
    return region_of(label) in (Region.CERVICAL, Region.THORACIC, Region.LUMBAR)


def mobile_labels() -> list[str]:
    return [v.label for v in CATALOG if is_mobile(v.label)]


def junction_labels() -> list[tuple[str, str]]:
    """Region boundary pairs (caudal of A, cranial of B)."""
    pairs: list[tuple[str, str]] = []
    for i in range(len(REGION_ORDER) - 1):
        a, b = REGION_ORDER[i], REGION_ORDER[i + 1]
        a_end = labels_in_region(a)[-1]
        b_start = labels_in_region(b)[0]
        pairs.append((a_end, b_start))
    return pairs


def validate_catalog() -> dict[str, int]:
    counts = {r.value: 0 for r in Region}
    for v in CATALOG:
        counts[v.region.value] += 1
    expected = {r.value: n for r, n in REGION_COUNTS.items()}
    if counts != expected:
        raise AssertionError(f"counts {counts} != {expected}")
    if len(CATALOG) != VERTEBRA_N:
        raise AssertionError("vertebra_n")
    return counts


def iter_cranial_to_caudal() -> Iterable[VertebraId]:
    return iter(CATALOG)


def neighbor_labels(label: str) -> tuple[str | None, str | None]:
    """Return (cranial_neighbor, caudal_neighbor) labels."""
    o = ordinal_of(label)
    cranial = BY_ORDINAL[o - 1].label if o > 0 else None
    caudal = BY_ORDINAL[o + 1].label if o < VERTEBRA_N - 1 else None
    return cranial, caudal
