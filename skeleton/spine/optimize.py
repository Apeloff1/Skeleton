"""Posture optimization: minimize energy subject to ROM + task targets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from skeleton.spine.articulation import clamp_to_rom, total_soft_penalty
from skeleton.spine.chain import SpineChain, rebind_segments
from skeleton.spine.constraint_solver import project_rom
from skeleton.spine.ligament import chain_ligament_energy
from skeleton.spine.segment import apply_relative_map
from skeleton.spine.stiffness import chain_energy
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class OptResult:
    chain: SpineChain
    cost: float
    iterations: int
    feasible: bool


def total_cost(chain: SpineChain, task_weight: float = 1.0, task: float = 0.0) -> float:
    return (
        chain_energy(chain.segments)
        + 0.25 * chain_ligament_energy(chain.segments)
        + 100.0 * total_soft_penalty(chain.segments)
        + task_weight * task
    )


def _set_rx(chain: SpineChain, label: str, rx: float) -> SpineChain:
    for s in chain.segments:
        if s.label == label:
            p = s.relative
            rel = {label: Pose6(rx, p.ry, p.rz, p.tx, p.ty, p.tz)}
            return project_rom(rebind_segments(chain, apply_relative_map(chain.segments, rel)))
    return chain


def optimize_flexion_target(
    chain: SpineChain,
    target_sum_rx: float,
    *,
    steps: int = 40,
    lr: float = 0.15,
) -> OptResult:
    """Distribute flexion to match target sum rx while minimizing energy."""
    current = project_rom(chain)
    for it in range(1, steps + 1):
        mob = [s for s in current.segments if not s.locked]
        if not mob:
            break
        ssum = sum(s.relative.rx for s in mob)
        err = ssum - target_sum_rx
        if abs(err) < 1e-3:
            return OptResult(current, total_cost(current, task=err * err), it, True)
        # proportional correction
        rel: dict[str, Pose6] = {}
        for s in mob:
            corr = -lr * err / len(mob)
            p = s.relative
            cand = Pose6(p.rx + corr, p.ry, p.rz, p.tx, p.ty, p.tz)
            rel[s.label] = clamp_to_rom(s, cand)
        current = rebind_segments(current, apply_relative_map(current.segments, rel))
    mob = [s for s in current.segments if not s.locked]
    ssum = sum(s.relative.rx for s in mob)
    err = ssum - target_sum_rx
    return OptResult(current, total_cost(current, task=err * err), steps, abs(err) < 0.5)


def coordinate_descent(
    chain: SpineChain,
    cost_fn: Callable[[SpineChain], float] | None = None,
    *,
    axes: tuple[int, ...] = (0, 1, 2),
    sweeps: int = 3,
    delta: float = 0.5,
) -> OptResult:
    """Simple coordinate descent over segment rotational DOF."""
    cost_fn = cost_fn or (lambda c: total_cost(c))
    current = project_rom(chain)
    best_cost = cost_fn(current)
    it = 0
    for _ in range(sweeps):
        for s in list(current.segments):
            if s.locked:
                continue
            for axis in axes:
                it += 1
                base = list(s.relative.as_tuple())
                improved = False
                for sign in (-1.0, 1.0):
                    trial = list(base)
                    trial[axis] += sign * delta
                    rel = {s.label: clamp_to_rom(s, Pose6(*trial))}
                    cand_chain = rebind_segments(
                        current, apply_relative_map(current.segments, rel)
                    )
                    c = cost_fn(cand_chain)
                    if c + 1e-9 < best_cost:
                        current = cand_chain
                        best_cost = c
                        # refresh s from current
                        for ns in current.segments:
                            if ns.label == s.label:
                                s = ns
                                base = list(s.relative.as_tuple())
                        improved = True
                if not improved:
                    continue
    return OptResult(current, best_cost, it, total_soft_penalty(current.segments) == 0.0)
