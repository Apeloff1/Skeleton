"""Sagittal curvatures: lordosis / kyphosis estimates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.chain import SpineChain
from skeleton.spine.kinematics import Frame3, forward_frames
from skeleton.spine.taxonomy import Region, labels_in_region


@dataclass(frozen=True, slots=True)
class CurveMeasure:
    region: str
    cobb_deg: float
    arc_mm: float
    chord_mm: float

    @property
    def apex_ratio(self) -> float:
        if self.chord_mm <= 1e-9:
            return 0.0
        return self.arc_mm / self.chord_mm


def _frames_for_labels(chain: SpineChain, labels: Sequence[str]) -> list[Frame3]:
    all_f = forward_frames(chain)
    idx = {v.label: i for i, v in enumerate(chain.vertebrae)}
    return [all_f[idx[lb]] for lb in labels]


def cobb_angle(frames: Sequence[Frame3]) -> float:
    """Approximate Cobb as difference in roll between end frames."""
    if len(frames) < 2:
        return 0.0
    return frames[-1].roll - frames[0].roll


def arc_and_chord(frames: Sequence[Frame3]) -> tuple[float, float]:
    if len(frames) < 2:
        return 0.0, 0.0
    arc = 0.0
    for i in range(1, len(frames)):
        arc += frames[i - 1].distance_to(frames[i])
    chord = frames[0].distance_to(frames[-1])
    return arc, chord


def measure_region(chain: SpineChain, region: Region) -> CurveMeasure:
    labels = labels_in_region(region)
    frames = _frames_for_labels(chain, labels)
    arc, chord = arc_and_chord(frames)
    return CurveMeasure(region.value, cobb_angle(frames), arc, chord)


def cervical_lordosis(chain: SpineChain) -> CurveMeasure:
    return measure_region(chain, Region.CERVICAL)


def thoracic_kyphosis(chain: SpineChain) -> CurveMeasure:
    return measure_region(chain, Region.THORACIC)


def lumbar_lordosis(chain: SpineChain) -> CurveMeasure:
    return measure_region(chain, Region.LUMBAR)


def apply_neutral_curves(chain: SpineChain) -> SpineChain:
    """Bake gentle physiological curves into segment relatives."""
    from skeleton.spine.range_of_motion import coupled_pose
    from skeleton.spine.segment import apply_relative_map
    from skeleton.spine.chain import rebind_segments
    from skeleton.spine.taxonomy import region_of

    relatives: dict[str, object] = {}
    # Distribute small sagittal angles
    targets = {
        Region.CERVICAL: -2.0,  # lordosis → extension negative in our rx?
        Region.THORACIC: 1.5,   # kyphosis flexion
        Region.LUMBAR: -2.5,
    }
    for s in chain.segments:
        if s.locked:
            continue
        r = region_of(s.sid.cranial)
        if r in targets:
            from skeleton.spine.vertebra import Pose6

            relatives[s.label] = Pose6(rx=targets[r])
    new_segs = apply_relative_map(chain.segments, relatives)  # type: ignore[arg-type]
    return rebind_segments(chain, new_segs)


def curvature_card_payload(chain: SpineChain) -> dict[str, float]:
    c = cervical_lordosis(chain)
    t = thoracic_kyphosis(chain)
    l = lumbar_lordosis(chain)
    return {
        "cervical_cobb": c.cobb_deg,
        "thoracic_cobb": t.cobb_deg,
        "lumbar_cobb": l.cobb_deg,
        "cervical_arc": c.arc_mm,
        "thoracic_arc": t.arc_mm,
        "lumbar_arc": l.arc_mm,
    }


def curvature_sign_ok(chain: SpineChain) -> bool:
    """After neutral curves: cervical/lumbar lordotic (neg), thoracic kyphotic (pos)."""
    curved = apply_neutral_curves(chain)
    c = cervical_lordosis(curved).cobb_deg
    t = thoracic_kyphosis(curved).cobb_deg
    l = lumbar_lordosis(curved).cobb_deg
    return c <= 0 and t >= 0 and l <= 0
