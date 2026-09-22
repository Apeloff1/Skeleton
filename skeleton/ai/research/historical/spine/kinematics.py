"""Forward kinematics along the vertebral chain."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.chain import SpineChain
from skeleton.spine.segment import Segment
from skeleton.spine.vertebra import Pose6, Vertebra


@dataclass(frozen=True, slots=True)
class Frame3:
    """Orientation (Rz*Ry*Rx intrinsic) + origin (mm)."""

    x: float
    y: float
    z: float
    roll: float  # rx
    pitch: float  # ry
    yaw: float  # rz

    def origin(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def distance_to(self, other: "Frame3") -> float:
        return math.sqrt(
            (self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2
        )


def _rot_matrix(rx: float, ry: float, rz: float) -> list[list[float]]:
    """Degrees → 3x3 rotation Rz*Ry*Rx."""
    ax, ay, az = map(math.radians, (rx, ry, rz))
    cx, sx = math.cos(ax), math.sin(ax)
    cy, sy = math.cos(ay), math.sin(ay)
    cz, sz = math.cos(az), math.sin(az)
    # Rx
    rxm = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    rym = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    rzm = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    return _mmul(_mmul(rzm, rym), rxm)


def _mmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    out = [[0.0] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            out[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j]
    return out


def _mv(m: list[list[float]], v: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    )


def forward_frames(chain: SpineChain) -> list[Frame3]:
    """Accumulate frames cranial→caudal. Local +Z is caudal axis."""
    frames: list[Frame3] = []
    x = y = z = 0.0
    roll = pitch = yaw = 0.0
    R = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
    for i, v in enumerate(chain.vertebrae):
        frames.append(Frame3(x, y, z, roll, pitch, yaw))
        # advance by vertebral body height along local Z
        step = (0.0, 0.0, v.dims.height_mm)
        dx, dy, dz = _mv(R, step)
        x += dx
        y += dy
        z += dz
        if i < len(chain.segments):
            seg = chain.segments[i]
            # disc height
            dstep = (0.0, 0.0, seg.disc.height_mm)
            ddx, ddy, ddz = _mv(R, dstep)
            x += ddx
            y += ddy
            z += ddz
            # apply relative articulation
            rel = seg.relative
            x += rel.tx
            y += rel.ty
            z += rel.tz
            r_local = _rot_matrix(rel.rx, rel.ry, rel.rz)
            R = _mmul(R, r_local)
            roll += rel.rx
            pitch += rel.ry
            yaw += rel.rz
    return frames


def end_effector(chain: SpineChain) -> Frame3:
    frames = forward_frames(chain)
    return frames[-1]


def path_length_mm(chain: SpineChain) -> float:
    frames = forward_frames(chain)
    total = 0.0
    for i in range(1, len(frames)):
        total += frames[i - 1].distance_to(frames[i])
    return round(total, 6)


def chord_length_mm(chain: SpineChain) -> float:
    frames = forward_frames(chain)
    return round(frames[0].distance_to(frames[-1]), 6)


def jacobian_numeric(
    chain: SpineChain, seg_index: int, axis: int, eps: float = 1e-3
) -> tuple[float, float, float]:
    """Numeric translational Jacobian column for one segment DOF."""
    from skeleton.spine.segment import apply_relative_map
    from skeleton.spine.chain import rebind_segments

    base = end_effector(chain)
    seg = chain.segments[seg_index]
    t = list(seg.relative.as_tuple())
    t[axis] += eps
    bumped = Pose6(*t)
    new_segs = apply_relative_map(chain.segments, {seg.label: bumped})
    chain2 = rebind_segments(chain, new_segs)
    tip = end_effector(chain2)
    return ((tip.x - base.x) / eps, (tip.y - base.y) / eps, (tip.z - base.z) / eps)


def stack_height_error(chain: SpineChain) -> float:
    """Difference between path length and sum of component heights."""
    expected = sum(v.dims.height_mm for v in chain.vertebrae) + sum(
        s.disc.height_mm for s in chain.segments
    )
    return abs(path_length_mm(chain) - expected)
