"""Posture library: named configurations and blending."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from skeleton.spine.chain import SpineChain, default_chain, rebind_segments
from skeleton.spine.range_of_motion import distribute_flexion
from skeleton.spine.segment import apply_relative_map
from skeleton.spine.taxonomy import Region, region_of
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class PostureSpec:
    name: str
    description: str
    builder: str  # key into BUILDERS


def _neutral(chain: SpineChain) -> SpineChain:
    return chain.with_name("neutral")


def _flexion_30(chain: SpineChain) -> SpineChain:
    rel = distribute_flexion(chain.segments, 30.0)
    return rebind_segments(chain, apply_relative_map(chain.segments, rel)).with_name("flexion_30")


def _flexion_60(chain: SpineChain) -> SpineChain:
    rel = distribute_flexion(chain.segments, 60.0)
    return rebind_segments(chain, apply_relative_map(chain.segments, rel)).with_name("flexion_60")


def _extension_20(chain: SpineChain) -> SpineChain:
    # negative rx
    from skeleton.spine.articulation import rom_for_segment

    rel: dict[str, Pose6] = {}
    caps = []
    for s in chain.segments:
        if s.locked:
            continue
        cap = max(0.0, -rom_for_segment(s).lo.rx)
        caps.append((s, cap))
    total = sum(c for _, c in caps) or 1.0
    target = 20.0
    for s, cap in caps:
        share = min(cap, target * (cap / total))
        rel[s.label] = Pose6(rx=-share)
    return rebind_segments(chain, apply_relative_map(chain.segments, rel)).with_name("extension_20")


def _lateral_15(chain: SpineChain, sign: float = 1.0) -> SpineChain:
    from skeleton.spine.articulation import rom_for_segment

    rel: dict[str, Pose6] = {}
    caps = []
    for s in chain.segments:
        if s.locked:
            continue
        b = rom_for_segment(s)
        cap = max(0.0, b.hi.ry if sign > 0 else -b.lo.ry)
        caps.append((s, cap))
    total = sum(c for _, c in caps) or 1.0
    target = 15.0
    for s, cap in caps:
        share = min(cap, target * (cap / total))
        rel[s.label] = Pose6(ry=sign * share)
    name = "lateral_right_15" if sign > 0 else "lateral_left_15"
    return rebind_segments(chain, apply_relative_map(chain.segments, rel)).with_name(name)


def _axial_10(chain: SpineChain, sign: float = 1.0) -> SpineChain:
    from skeleton.spine.articulation import rom_for_segment

    rel: dict[str, Pose6] = {}
    for s in chain.segments:
        if s.locked:
            continue
        b = rom_for_segment(s)
        # prefer cervical for rotation
        scale = 1.5 if region_of(s.sid.cranial) is Region.CERVICAL else 0.5
        span = b.hi.rz if sign > 0 else -b.lo.rz
        rel[s.label] = Pose6(rz=sign * min(span, 10.0 * scale / 7.0))
    name = "axial_cw_10" if sign > 0 else "axial_ccw_10"
    return rebind_segments(chain, apply_relative_map(chain.segments, rel)).with_name(name)


def _sitting(chain: SpineChain) -> SpineChain:
    # mild lumbar flexion + thoracic extension tendency
    rel: dict[str, Pose6] = {}
    for s in chain.segments:
        if s.locked:
            continue
        r = region_of(s.sid.cranial)
        if r is Region.LUMBAR:
            rel[s.label] = Pose6(rx=4.0)
        elif r is Region.THORACIC:
            rel[s.label] = Pose6(rx=-0.5)
        elif r is Region.CERVICAL:
            rel[s.label] = Pose6(rx=1.0)
    return rebind_segments(chain, apply_relative_map(chain.segments, rel)).with_name("sitting")


def _forward_bend(chain: SpineChain) -> SpineChain:
    return _flexion_60(chain).with_name("forward_bend")


BUILDERS: dict[str, Callable[[SpineChain], SpineChain]] = {
    "neutral": _neutral,
    "flexion_30": _flexion_30,
    "flexion_60": _flexion_60,
    "extension_20": _extension_20,
    "lateral_right_15": lambda c: _lateral_15(c, 1.0),
    "lateral_left_15": lambda c: _lateral_15(c, -1.0),
    "axial_cw_10": lambda c: _axial_10(c, 1.0),
    "axial_ccw_10": lambda c: _axial_10(c, -1.0),
    "sitting": _sitting,
    "forward_bend": _forward_bend,
}

CATALOG: tuple[PostureSpec, ...] = tuple(
    PostureSpec(name=k, description=k.replace("_", " "), builder=k) for k in BUILDERS
)


def list_postures() -> list[str]:
    return list(BUILDERS)


def build_posture(name: str, base: SpineChain | None = None) -> SpineChain:
    if name not in BUILDERS:
        raise KeyError(name)
    chain = base or default_chain()
    return BUILDERS[name](chain)


def blend_postures(
    a: SpineChain, b: SpineChain, t: float
) -> SpineChain:
    """Linear blend of segment relatives; t in [0,1]."""
    t = max(0.0, min(1.0, t))
    rel: dict[str, Pose6] = {}
    b_map = {s.label: s.relative for s in b.segments}
    for s in a.segments:
        pa = s.relative.as_tuple()
        pb = b_map[s.label].as_tuple()
        blended = tuple(pa[i] * (1 - t) + pb[i] * t for i in range(6))
        rel[s.label] = Pose6(*blended)
    return rebind_segments(a, apply_relative_map(a.segments, rel)).with_name(
        f"blend:{a.name}:{b.name}:{t:.2f}"
    )


def posture_energy_table(base: SpineChain | None = None) -> dict[str, float]:
    from skeleton.spine.stiffness import chain_energy

    chain = base or default_chain()
    out: dict[str, float] = {}
    for name in BUILDERS:
        p = build_posture(name, chain)
        out[name] = chain_energy(p.segments)
    return out


def assert_postures_rom_safe() -> list[str]:
    from skeleton.spine.articulation import all_rom_ok

    bad: list[str] = []
    base = default_chain()
    for name in BUILDERS:
        p = build_posture(name, base)
        if not all_rom_ok(p.segments):
            bad.append(name)
    return bad
