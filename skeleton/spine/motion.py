"""Motion sequences: trajectories over postures and time."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Sequence

from skeleton.spine.chain import SpineChain, default_chain
from skeleton.spine.posture import blend_postures, build_posture, list_postures
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class Keyframe:
    time_s: float
    posture: str
    chain: SpineChain | None = None


@dataclass
class MotionClip:
    name: str
    keyframes: list[Keyframe] = field(default_factory=list)

    def add(self, time_s: float, posture: str, chain: SpineChain | None = None) -> None:
        self.keyframes.append(Keyframe(time_s, posture, chain))
        self.keyframes.sort(key=lambda k: k.time_s)

    def duration(self) -> float:
        if not self.keyframes:
            return 0.0
        return self.keyframes[-1].time_s - self.keyframes[0].time_s

    def sample(self, time_s: float, base: SpineChain | None = None) -> SpineChain:
        if not self.keyframes:
            return base or default_chain()
        base = base or default_chain()
        if time_s <= self.keyframes[0].time_s:
            kf = self.keyframes[0]
            return kf.chain or build_posture(kf.posture, base)
        if time_s >= self.keyframes[-1].time_s:
            kf = self.keyframes[-1]
            return kf.chain or build_posture(kf.posture, base)
        for i in range(len(self.keyframes) - 1):
            a, b = self.keyframes[i], self.keyframes[i + 1]
            if a.time_s <= time_s <= b.time_s:
                span = b.time_s - a.time_s
                t = 0.0 if span <= 0 else (time_s - a.time_s) / span
                ca = a.chain or build_posture(a.posture, base)
                cb = b.chain or build_posture(b.posture, base)
                return blend_postures(ca, cb, t)
        return base


def make_sit_to_stand() -> MotionClip:
    clip = MotionClip("sit_to_stand")
    clip.add(0.0, "sitting")
    clip.add(0.5, "flexion_30")
    clip.add(1.0, "neutral")
    clip.add(1.2, "extension_20")
    clip.add(1.5, "neutral")
    return clip


def make_look_left_right() -> MotionClip:
    clip = MotionClip("look_left_right")
    clip.add(0.0, "neutral")
    clip.add(0.4, "axial_ccw_10")
    clip.add(0.8, "neutral")
    clip.add(1.2, "axial_cw_10")
    clip.add(1.6, "neutral")
    return clip


def make_side_bend() -> MotionClip:
    clip = MotionClip("side_bend")
    clip.add(0.0, "neutral")
    clip.add(0.5, "lateral_left_15")
    clip.add(1.0, "neutral")
    clip.add(1.5, "lateral_right_15")
    clip.add(2.0, "neutral")
    return clip


def sample_timeline(clip: MotionClip, fps: float = 10.0) -> list[tuple[float, SpineChain]]:
    if clip.duration() <= 0:
        return [(0.0, clip.sample(0.0))]
    n = max(1, int(clip.duration() * fps) + 1)
    out: list[tuple[float, SpineChain]] = []
    t0 = clip.keyframes[0].time_s
    for i in range(n):
        t = t0 + i / fps
        if t > clip.keyframes[-1].time_s:
            t = clip.keyframes[-1].time_s
        out.append((t, clip.sample(t)))
    return out


def motion_jerk_proxy(samples: Sequence[SpineChain]) -> float:
    """Sum of second differences of mean rx across samples."""
    if len(samples) < 3:
        return 0.0
    xs = [s.mean_pose().rx for s in samples]
    jerk = 0.0
    for i in range(1, len(xs) - 1):
        d2 = xs[i + 1] - 2 * xs[i] + xs[i - 1]
        jerk += abs(d2)
    return jerk


def library() -> dict[str, MotionClip]:
    return {
        "sit_to_stand": make_sit_to_stand(),
        "look_left_right": make_look_left_right(),
        "side_bend": make_side_bend(),
    }


def validate_library_rom() -> dict[str, bool]:
    from skeleton.spine.articulation import all_rom_ok

    out: dict[str, bool] = {}
    for name, clip in library().items():
        ok = True
        for _, chain in sample_timeline(clip, fps=5.0):
            if not all_rom_ok(chain.segments):
                ok = False
                break
        out[name] = ok
    return out
