"""Simple articulation constraint projection / satisfaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.articulation import (
    clamp_to_rom,
    rom_for_segment,
    soft_penalty,
    total_soft_penalty,
)
from skeleton.spine.chain import SpineChain, rebind_segments
from skeleton.spine.segment import Segment, apply_relative_map
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class SolverResult:
    chain: SpineChain
    iterations: int
    penalty_before: float
    penalty_after: float
    converged: bool


def project_rom(chain: SpineChain) -> SpineChain:
    rel: dict[str, Pose6] = {}
    for s in chain.segments:
        rel[s.label] = clamp_to_rom(s, s.relative)
    return rebind_segments(chain, apply_relative_map(chain.segments, rel))


def _gradient_penalty(seg: Segment, pose: Pose6, eps: float = 1e-4) -> Pose6:
    base = soft_penalty(seg, pose)
    parts = []
    t = list(pose.as_tuple())
    for i in range(6):
        t2 = list(t)
        t2[i] += eps
        parts.append((soft_penalty(seg, Pose6(*t2)) - base) / eps)
    return Pose6(*parts)


def gradient_descent_rom(
    chain: SpineChain,
    *,
    steps: int = 20,
    lr: float = 0.1,
    tol: float = 1e-6,
) -> SolverResult:
    """Project poses toward ROM via exterior-penalty gradient steps."""
    before = total_soft_penalty(chain.segments)
    segs = list(chain.segments)
    converged = False
    it = 0
    for it in range(1, steps + 1):
        rel: dict[str, Pose6] = {}
        max_g = 0.0
        for s in segs:
            if s.locked:
                rel[s.label] = s.relative
                continue
            g = _gradient_penalty(s, s.relative)
            gt = g.as_tuple()
            max_g = max(max_g, max(abs(x) for x in gt))
            pt = list(s.relative.as_tuple())
            updated = Pose6(*(pt[i] - lr * gt[i] for i in range(6)))
            rel[s.label] = clamp_to_rom(s, updated)
        segs = list(apply_relative_map(segs, rel))
        if max_g < tol:
            converged = True
            break
    after_chain = rebind_segments(chain, segs)
    after = total_soft_penalty(after_chain.segments)
    return SolverResult(after_chain, it, before, after, converged or after <= before)


def satisfy(chain: SpineChain) -> SpineChain:
    """Hard project then optional soft refine."""
    projected = project_rom(chain)
    if total_soft_penalty(projected.segments) == 0.0:
        return projected
    return gradient_descent_rom(projected, steps=10).chain


def feasible(chain: SpineChain, eps: float = 1e-9) -> bool:
    return total_soft_penalty(chain.segments) <= eps


def random_feasible_perturbation(
    chain: SpineChain, scale: float = 0.25, seed: int = 0
) -> SpineChain:
    """Deterministic pseudo-random feasible pose within ROM fractions."""
    # xorshift-ish
    state = seed & 0xFFFFFFFF or 1

    def rnd() -> float:
        nonlocal state
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= (state >> 17) & 0xFFFFFFFF
        state ^= (state << 5) & 0xFFFFFFFF
        return (state & 0xFFFFFFFF) / 0xFFFFFFFF

    rel: dict[str, Pose6] = {}
    for s in chain.segments:
        if s.locked:
            continue
        b = rom_for_segment(s)
        lo, hi = b.lo.as_tuple(), b.hi.as_tuple()
        parts = []
        for i in range(6):
            mid = 0.5 * (lo[i] + hi[i])
            half = 0.5 * (hi[i] - lo[i]) * scale
            parts.append(mid + (rnd() * 2 - 1) * half)
        rel[s.label] = Pose6(*parts)
    return project_rom(rebind_segments(chain, apply_relative_map(chain.segments, rel)))
