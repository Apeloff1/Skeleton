"""Inter-segment coupling rules and enforced coordination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.chain import SpineChain, rebind_segments
from skeleton.spine.range_of_motion import fryette_type1, fryette_type2
from skeleton.spine.segment import Segment, apply_relative_map
from skeleton.spine.taxonomy import Region, region_of
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class CouplingRule:
    name: str
    region: Region
    kind: str  # type1 | type2 | proportional
    gain: float


DEFAULT_RULES: tuple[CouplingRule, ...] = (
    CouplingRule("cervical_type2", Region.CERVICAL, "type2", 0.7),
    CouplingRule("thoracic_type1", Region.THORACIC, "type1", 0.4),
    CouplingRule("lumbar_type1", Region.LUMBAR, "type1", 0.5),
)


def apply_coupling_to_pose(region: Region, pose: Pose6, gain: float, kind: str) -> Pose6:
    ry, rz = pose.ry, pose.rz
    if kind == "type1":
        # enforce opposite signs: rz := -gain * ry
        new_rz = -gain * ry
        return Pose6(pose.rx, pose.ry, new_rz, pose.tx, pose.ty, pose.tz)
    if kind == "type2":
        new_rz = gain * ry
        return Pose6(pose.rx, pose.ry, new_rz, pose.tx, pose.ty, pose.tz)
    if kind == "proportional":
        new_rz = gain * rz + (1 - gain) * (-ry)
        return Pose6(pose.rx, pose.ry, new_rz, pose.tx, pose.ty, pose.tz)
    return pose


def rule_for_region(region: Region, rules: Sequence[CouplingRule] = DEFAULT_RULES) -> CouplingRule | None:
    for r in rules:
        if r.region is region:
            return r
    return None


def enforce_coupling(chain: SpineChain, rules: Sequence[CouplingRule] = DEFAULT_RULES) -> SpineChain:
    rel: dict[str, Pose6] = {}
    for s in chain.segments:
        if s.locked:
            continue
        region = region_of(s.sid.cranial)
        rule = rule_for_region(region, rules)
        if rule is None:
            continue
        rel[s.label] = apply_coupling_to_pose(region, s.relative, rule.gain, rule.kind)
    return rebind_segments(chain, apply_relative_map(chain.segments, rel))


def coupling_violations(chain: SpineChain) -> list[str]:
    bad: list[str] = []
    for s in chain.segments:
        if s.locked:
            continue
        region = region_of(s.sid.cranial)
        ry, rz, rx = s.relative.ry, s.relative.rz, s.relative.rx
        if abs(ry) < 1e-6 and abs(rz) < 1e-6:
            continue
        if region is Region.LUMBAR or region is Region.THORACIC:
            if not fryette_type1(ry, rz):
                bad.append(s.label)
        elif region is Region.CERVICAL:
            flexed = abs(rx) > 1.0
            if flexed and not fryette_type2(ry, rz, True):
                bad.append(s.label)
    return bad


def neighbor_smoothness(chain: SpineChain) -> float:
    """Mean absolute difference of rx between adjacent mobile segments."""
    mob = [s for s in chain.segments if not s.locked]
    if len(mob) < 2:
        return 0.0
    acc = 0.0
    for i in range(len(mob) - 1):
        acc += abs(mob[i].relative.rx - mob[i + 1].relative.rx)
    return acc / (len(mob) - 1)


def smooth_rx(chain: SpineChain, passes: int = 2, alpha: float = 0.5) -> SpineChain:
    segs = list(chain.segments)
    for _ in range(passes):
        rel: dict[str, Pose6] = {}
        for i, s in enumerate(segs):
            if s.locked:
                continue
            left = segs[i - 1].relative.rx if i > 0 and not segs[i - 1].locked else s.relative.rx
            right = segs[i + 1].relative.rx if i + 1 < len(segs) and not segs[i + 1].locked else s.relative.rx
            new_rx = (1 - alpha) * s.relative.rx + alpha * 0.5 * (left + right)
            p = s.relative
            rel[s.label] = Pose6(new_rx, p.ry, p.rz, p.tx, p.ty, p.tz)
        segs = list(apply_relative_map(segs, rel))
    return rebind_segments(chain, segs)


def coordination_score(chain: SpineChain) -> float:
    """Higher is better: inverse of violations + smoothness."""
    v = len(coupling_violations(chain))
    s = neighbor_smoothness(chain)
    return 1.0 / (1.0 + v + 0.1 * s)
