"""Simplified muscle path recruitment for posture support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from skeleton.spine.chain import SpineChain
from skeleton.spine.vertebra import Pose6


@dataclass(frozen=True, slots=True)
class Muscle:
    name: str
    pcs_a_mm2: float  # physiological cross section
    sigma_mpa: float  # specific tension
    moment_arm_mm: float
    side: str  # left|right|mid
    action: str  # flex|ext|lat|rot


    def max_force_n(self) -> float:
        return self.pcs_a_mm2 * self.sigma_mpa

    def max_moment_nmm(self) -> float:
        return self.max_force_n() * self.moment_arm_mm


MUSCLE_SET: tuple[Muscle, ...] = (
    Muscle("erector_spinae_L", 1200, 0.5, 50, "left", "ext"),
    Muscle("erector_spinae_R", 1200, 0.5, 50, "right", "ext"),
    Muscle("rectus_abdominis", 800, 0.5, 80, "mid", "flex"),
    Muscle("oblique_ext_L", 600, 0.5, 60, "left", "rot"),
    Muscle("oblique_ext_R", 600, 0.5, 60, "right", "rot"),
    Muscle("oblique_int_L", 550, 0.5, 55, "left", "lat"),
    Muscle("oblique_int_R", 550, 0.5, 55, "right", "lat"),
    Muscle("multifidus_L", 400, 0.55, 30, "left", "ext"),
    Muscle("multifidus_R", 400, 0.55, 30, "right", "ext"),
    Muscle("psoas_L", 700, 0.5, 40, "left", "flex"),
    Muscle("psoas_R", 700, 0.5, 40, "right", "flex"),
    Muscle("ql_L", 500, 0.5, 45, "left", "lat"),
    Muscle("ql_R", 500, 0.5, 45, "right", "lat"),
)


def recruit_for_pose(pose: Pose6) -> dict[str, float]:
    """Return activation 0..1 per muscle for a global pose proxy."""
    act: dict[str, float] = {m.name: 0.0 for m in MUSCLE_SET}
    # extension demand
    if pose.rx < 0:
        demand = min(1.0, abs(pose.rx) / 30.0)
        for m in MUSCLE_SET:
            if m.action == "ext":
                act[m.name] = demand
    elif pose.rx > 0:
        demand = min(1.0, pose.rx / 40.0)
        for m in MUSCLE_SET:
            if m.action == "flex":
                act[m.name] = demand
    if abs(pose.ry) > 1e-6:
        demand = min(1.0, abs(pose.ry) / 20.0)
        side = "left" if pose.ry < 0 else "right"
        for m in MUSCLE_SET:
            if m.action == "lat" and m.side == side:
                act[m.name] = max(act[m.name], demand)
    if abs(pose.rz) > 1e-6:
        demand = min(1.0, abs(pose.rz) / 25.0)
        side = "left" if pose.rz < 0 else "right"
        for m in MUSCLE_SET:
            if m.action == "rot" and m.side == side:
                act[m.name] = max(act[m.name], demand)
    return act


def support_moment(activations: dict[str, float]) -> dict[str, float]:
    """Net moment components from recruitment."""
    mx = my = mz = 0.0
    for m in MUSCLE_SET:
        a = activations.get(m.name, 0.0)
        f = a * m.max_force_n()
        mom = f * m.moment_arm_mm
        if m.action == "flex":
            mx += mom
        elif m.action == "ext":
            mx -= mom
        elif m.action == "lat":
            my += mom if m.side == "right" else -mom
        elif m.action == "rot":
            mz += mom if m.side == "right" else -mom
    return {"mx": mx, "my": my, "mz": mz}


def co_contraction_index(activations: dict[str, float]) -> float:
    flex = sum(activations[m.name] for m in MUSCLE_SET if m.action == "flex")
    ext = sum(activations[m.name] for m in MUSCLE_SET if m.action == "ext")
    return min(flex, ext)


def chain_mean_pose(chain: SpineChain) -> Pose6:
    return chain.mean_pose()


def recruit_for_chain(chain: SpineChain) -> dict[str, float]:
    return recruit_for_pose(chain_mean_pose(chain))


def metabolic_proxy(activations: dict[str, float]) -> float:
    """Sum a^2 * PCSA as metabolic cost proxy."""
    cost = 0.0
    by_name = {m.name: m for m in MUSCLE_SET}
    for name, a in activations.items():
        cost += a * a * by_name[name].pcs_a_mm2
    return cost
