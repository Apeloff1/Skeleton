"""Region-scoped operations on the spine chain."""

from __future__ import annotations

from typing import Callable

from skeleton.spine.chain import SpineChain, rebind_segments
from skeleton.spine.segment import apply_relative_map
from skeleton.spine.taxonomy import Region, labels_in_region, region_of, region_span
from skeleton.spine.vertebra import Pose6


def segments_in_region(chain: SpineChain, region: Region) -> list:
    return [s for s in chain.segments if region_of(s.sid.cranial) is region and not s.locked]


def map_region_rx(chain: SpineChain, region: Region, rx: float) -> SpineChain:
    rel = {s.label: Pose6(rx, s.relative.ry, s.relative.rz, s.relative.tx, s.relative.ty, s.relative.tz)
           for s in segments_in_region(chain, region)}
    return rebind_segments(chain, apply_relative_map(chain.segments, rel))


def scale_region_poses(chain: SpineChain, region: Region, k: float) -> SpineChain:
    rel = {s.label: s.relative.scaled(k) for s in segments_in_region(chain, region)}
    return rebind_segments(chain, apply_relative_map(chain.segments, rel))


def region_energy(chain: SpineChain, region: Region) -> float:
    from skeleton.spine.stiffness import segment_stiffness

    return sum(segment_stiffness(s).energy(s.relative) for s in segments_in_region(chain, region))


def region_summary(chain: SpineChain, region: Region) -> dict[str, float]:
    segs = segments_in_region(chain, region)
    labels = labels_in_region(region)
    start, end = region_span(region)
    rx = [s.relative.rx for s in segs]
    return {
        "n_vertebrae": float(len(labels)),
        "n_mobile_segments": float(len(segs)),
        "ordinal_start": float(start),
        "ordinal_end": float(end),
        "sum_rx": float(sum(rx)),
        "mean_rx": float(sum(rx) / len(rx)) if rx else 0.0,
        "energy": region_energy(chain, region),
    }


def all_region_summaries(chain: SpineChain) -> dict[str, dict[str, float]]:
    return {r.value: region_summary(chain, r) for r in Region}


def transform_region(
    chain: SpineChain, region: Region, fn: Callable[[Pose6], Pose6]
) -> SpineChain:
    rel = {s.label: fn(s.relative) for s in segments_in_region(chain, region)}
    return rebind_segments(chain, apply_relative_map(chain.segments, rel))
