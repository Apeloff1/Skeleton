"""Measured visual continuity, occlusion, viewpoint revisit, and drift.

Each evaluator returns the quantity it measured and a pass/fail against a
bound the caller supplied. The same inputs produce the same measurement.
No score is invented, no frame is rendered, and no sample is drawn.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

from skeleton.frontier_temporal.record import (
    CameraPose,
    TemporalMemoryError,
    _finite,
    _sha256_hex,
    pose_distance,
)


@dataclass(frozen=True)
class Measurement:
    """A measured quantity and whether it satisfies the caller-supplied bound."""

    evaluator: str
    measured: float
    bound: float
    comparison: str
    passed: bool

    def __post_init__(self) -> None:
        if not math.isfinite(self.measured) or not math.isfinite(self.bound):
            raise TemporalMemoryError("measurement must be finite")
        if self.comparison == "gte":
            expected = self.measured >= self.bound
        elif self.comparison == "lte":
            expected = self.measured <= self.bound
        else:
            raise TemporalMemoryError("comparison must be gte or lte")
        if self.passed is not expected:
            raise TemporalMemoryError("pass/fail does not match the measured bound")


def _bound_unit(bound: float, label: str) -> float:
    number = _finite(bound, label, limit=1.0)
    if not 0.0 <= number <= 1.0:
        raise TemporalMemoryError(f"{label} must be in [0, 1]")
    return number


def _digests(values: Sequence[str], label: str) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise TemporalMemoryError(f"{label} must be a sequence of observation digests")
    if len(values) > 10_000:
        raise TemporalMemoryError(f"{label} exceeds 10000 digests")
    return tuple(_sha256_hex(item, label) for item in values)


def evaluate_visual_continuity(
    before: Sequence[str],
    after: Sequence[str],
    *,
    bound: float,
) -> Measurement:
    """Fraction of post-cut observation digests that already appear before the cut.

    ``measured`` is in ``[0, 1]``. The bound is a minimum fraction: the cut
    passes when the measured fraction is greater than or equal to ``bound``.
    """
    limit = _bound_unit(bound, "continuity bound")
    earlier = _digests(before, "before")
    later = _digests(after, "after")
    if not later:
        raise TemporalMemoryError("visual continuity requires at least one digest after the cut")
    seen = set(earlier)
    repeated = sum(1 for digest in later if digest in seen)
    measured = repeated / len(later)
    return Measurement(
        "visual_continuity",
        measured,
        limit,
        "gte",
        measured >= limit,
    )


@dataclass(frozen=True)
class StoredAABB:
    """Caller-supplied axis-aligned box. Not a renderer acceleration structure."""

    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def __post_init__(self) -> None:
        mins = (
            _finite(self.min_x, "min_x"),
            _finite(self.min_y, "min_y"),
            _finite(self.min_z, "min_z"),
        )
        maxs = (
            _finite(self.max_x, "max_x"),
            _finite(self.max_y, "max_y"),
            _finite(self.max_z, "max_z"),
        )
        object.__setattr__(self, "min_x", mins[0])
        object.__setattr__(self, "min_y", mins[1])
        object.__setattr__(self, "min_z", mins[2])
        object.__setattr__(self, "max_x", maxs[0])
        object.__setattr__(self, "max_y", maxs[1])
        object.__setattr__(self, "max_z", maxs[2])
        if mins[0] > maxs[0] or mins[1] > maxs[1] or mins[2] > maxs[2]:
            raise TemporalMemoryError("AABB minimum must not exceed maximum")


def _point(value: Sequence[float], label: str) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise TemporalMemoryError(f"{label} must be an xyz triple")
    return (
        _finite(value[0], f"{label}.x"),
        _finite(value[1], f"{label}.y"),
        _finite(value[2], f"{label}.z"),
    )


def _segment_entry(
    origin: tuple[float, float, float],
    target: tuple[float, float, float],
    box: StoredAABB,
) -> float | None:
    """Return the segment parameter where the ray enters ``box``, or None on a miss.

    The segment is ``origin + t * (target - origin)`` for ``t`` in ``[0, 1]``.
    A value of ``0`` means the segment starts inside the box. A miss, or a box
    that begins only at the subject (``t == 1``), returns None.
    """
    bounds = (
        (box.min_x, box.max_x),
        (box.min_y, box.max_y),
        (box.min_z, box.max_z),
    )
    t_min = 0.0
    t_max = 1.0
    for axis in range(3):
        start = origin[axis]
        delta = target[axis] - start
        low, high = bounds[axis]
        if delta == 0.0:
            if start < low or start > high:
                return None
            continue
        inv = 1.0 / delta
        t1 = (low - start) * inv
        t2 = (high - start) * inv
        if t1 > t2:
            t1, t2 = t2, t1
        if t1 > t_min:
            t_min = t1
        if t2 < t_max:
            t_max = t2
        if t_min > t_max:
            return None
    if t_max <= 0.0 or t_min >= 1.0:
        return None
    if t_min <= 0.0:
        return 0.0
    return t_min


def evaluate_occlusion(
    camera: CameraPose,
    subject: Sequence[float],
    aabbs: Sequence[StoredAABB],
    *,
    bound: float,
) -> Measurement:
    """Clear fraction of the segment from the camera to the subject.

    The ray is tested against the stored AABBs. ``measured`` is ``0`` when the
    segment starts inside an occluder, the entry parameter of the first hit
    when a box lies strictly between the camera and the subject, and ``1`` when
    no stored box blocks that open segment. The bound is the minimum clear
    fraction required to pass.
    """
    if not isinstance(camera, CameraPose):
        raise TemporalMemoryError("camera pose required")
    limit = _bound_unit(bound, "occlusion bound")
    origin = (camera.x, camera.y, camera.z)
    target = _point(subject, "subject")
    if origin == target:
        raise TemporalMemoryError("camera and subject must be distinct")
    if not isinstance(aabbs, Sequence) or isinstance(aabbs, (str, bytes)):
        raise TemporalMemoryError("occluders must be a sequence of AABBs")
    if len(aabbs) > 10_000:
        raise TemporalMemoryError("occluder count exceeds 10000")
    measured = 1.0
    for box in aabbs:
        if not isinstance(box, StoredAABB):
            raise TemporalMemoryError("occluder must be a StoredAABB")
        entry = _segment_entry(origin, target, box)
        if entry is not None and entry < measured:
            measured = entry
    return Measurement("occlusion", measured, limit, "gte", measured >= limit)


def evaluate_viewpoint_revisit(
    pose: CameraPose,
    stored: CameraPose,
    *,
    bound: float,
) -> Measurement:
    """Distance from ``pose`` to a stored camera pose.

    The bound is the declared distance threshold. The revisit passes when the
    measured distance is less than or equal to that threshold.
    """
    if not isinstance(pose, CameraPose) or not isinstance(stored, CameraPose):
        raise TemporalMemoryError("camera poses required")
    limit = _finite(bound, "viewpoint bound", limit=1e6)
    if limit < 0.0:
        raise TemporalMemoryError("viewpoint bound must be non-negative")
    measured = pose_distance(pose, stored)
    return Measurement("viewpoint_revisit", measured, limit, "lte", measured <= limit)


def evaluate_long_horizon_drift(
    estimated: Sequence[CameraPose],
    ground_truth: Sequence[CameraPose],
    *,
    bound: float,
) -> Measurement:
    """Growth of pose error against a scripted ground-truth pose list.

    Error at each step is the camera-pose distance to the caller-supplied
    ground truth. ``measured`` is the last error minus the first error. The
    bound is the maximum growth allowed. Lists must be the same length and
    contain at least two poses; a mismatch is rejected instead of scored.
    """
    if not isinstance(estimated, Sequence) or isinstance(estimated, (str, bytes)):
        raise TemporalMemoryError("estimated poses must be a sequence")
    if not isinstance(ground_truth, Sequence) or isinstance(ground_truth, (str, bytes)):
        raise TemporalMemoryError("ground truth poses must be a sequence")
    if len(estimated) != len(ground_truth):
        raise TemporalMemoryError("estimated and ground-truth pose lists must be the same length")
    if not 2 <= len(estimated) <= 100_000:
        raise TemporalMemoryError("long-horizon drift requires 2..100000 pose pairs")
    limit = _finite(bound, "drift bound", limit=1e6)
    errors: list[float] = []
    for index, (pose, truth) in enumerate(zip(estimated, ground_truth)):
        if not isinstance(pose, CameraPose) or not isinstance(truth, CameraPose):
            raise TemporalMemoryError(f"pose pair {index} must be camera poses")
        errors.append(pose_distance(pose, truth))
    measured = errors[-1] - errors[0]
    return Measurement("long_horizon_drift", measured, limit, "lte", measured <= limit)
