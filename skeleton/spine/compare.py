"""Compare two spine chains: diffs, distances, reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeleton.spine.chain import SpineChain
from skeleton.spine.digest import chain_digest, digest_drift
from skeleton.spine.kinematics import end_effector, path_length_mm
from skeleton.spine.metrics import compute_metrics
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class ChainDiff:
    pose_l2: float
    tip_delta_mm: float
    path_delta_mm: float
    digest_hamming: int
    changed_segments: tuple[str, ...]


def pose_l2(a: Pose6, b: Pose6) -> float:
    x, y = a.as_tuple(), b.as_tuple()
    return sum((x[i] - y[i]) ** 2 for i in range(6)) ** 0.5


def segment_pose_distance(a: SpineChain, b: SpineChain) -> float:
    total = 0.0
    b_map = {s.label: s.relative for s in b.segments}
    for s in a.segments:
        total += pose_l2(s.relative, b_map[s.label])
    return total


def changed_segment_labels(a: SpineChain, b: SpineChain, tol: float = 1e-9) -> list[str]:
    out = []
    b_map = {s.label: s.relative for s in b.segments}
    for s in a.segments:
        if pose_l2(s.relative, b_map[s.label]) > tol:
            out.append(s.label)
    return out


def diff_chains(a: SpineChain, b: SpineChain) -> ChainDiff:
    tip_a, tip_b = end_effector(a), end_effector(b)
    tip_delta = (
        (tip_a.x - tip_b.x) ** 2 + (tip_a.y - tip_b.y) ** 2 + (tip_a.z - tip_b.z) ** 2
    ) ** 0.5
    return ChainDiff(
        pose_l2=segment_pose_distance(a, b),
        tip_delta_mm=tip_delta,
        path_delta_mm=abs(path_length_mm(a) - path_length_mm(b)),
        digest_hamming=digest_drift(a, b),
        changed_segments=tuple(changed_segment_labels(a, b)),
    )


def metric_delta(a: SpineChain, b: SpineChain) -> dict[str, float]:
    ma, mb = compute_metrics(a), compute_metrics(b)
    out: dict[str, float] = {}
    for k, va in ma.items():
        vb = mb.get(k)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            out[k] = float(va) - float(vb)
    return out


def similarity(a: SpineChain, b: SpineChain) -> float:
    """0..1 similarity from pose distance."""
    d = segment_pose_distance(a, b)
    return 1.0 / (1.0 + d)


def same_topology(a: SpineChain, b: SpineChain) -> bool:
    return a.labels() == b.labels() and [s.label for s in a.segments] == [
        s.label for s in b.segments
    ]


def report(a: SpineChain, b: SpineChain) -> dict[str, Any]:
    d = diff_chains(a, b)
    return {
        "pose_l2": d.pose_l2,
        "tip_delta_mm": d.tip_delta_mm,
        "path_delta_mm": d.path_delta_mm,
        "digest_hamming": d.digest_hamming,
        "n_changed": len(d.changed_segments),
        "similarity": similarity(a, b),
        "same_topology": int(same_topology(a, b)),
        "digest_a": chain_digest(a),
        "digest_b": chain_digest(b),
    }
