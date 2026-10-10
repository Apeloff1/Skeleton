"""Fixed-step stability policy: deterministic sleeping and energy-drift guard.

Two concerns live here so the world step loop stays readable:

* **Sleep / wake policy.** A dynamic island may only sleep after every body
  in it has stayed quiet for ``PhysicsSettings.sleep_after_steps`` consecutive
  fixed steps.  "Quiet" means speed below the linear/angular limits, no live
  external force/torque, a per-step velocity change (impulse per unit mass)
  below ``sleep_velocity_change``, and no moving kinematic body touching or
  jointed to the island.  Sleeping islands are woken by impulses/forces
  (``RigidBody.wake``), by contact with any awake dynamic body (island
  propagation) and by contact with a moving kinematic body (see
  :func:`wake_kinematic_driven_islands`).  Solver-internal impulses and
  position corrections do *not* reset the quiet counter; only the policy does.

* **Energy guard.** Optional per-step monitor of kinetic + gravitational
  potential energy over the monitored dynamic bodies.  The guard allows the
  energy that external forces could legitimately inject plus a positional
  slop budget for contact/joint position correction; anything above that is a
  runaway.  ``REPORT`` records it, ``CLAMP`` removes the excess kinetic energy
  by uniformly scaling awake monitored velocities, ``RAISE`` aborts the step
  (the world rolls the step back exactly).

Everything is computed in sorted body-id order with plain float arithmetic, so
results are bit-identical across replays of the same inputs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .body import BodyType, RigidBody
from .calculations import gravitational_potential_energy, kinetic_energy
from .constraints import HingeJoint, JointConstraint, SliderJoint, SpringJoint
from .errors import PhysicsValidationError
from .islands import IslandGraph
from .math3d import Vec3

MAX_TOTAL_SOLVER_ITERATIONS = 256


class EnergyGuardMode(str, Enum):
    OFF = "off"
    REPORT = "report"
    CLAMP = "clamp"
    RAISE = "raise"


@dataclass(frozen=True, slots=True)
class StabilityReport:
    """Per-step sleep and energy-guard evidence attached to step receipts."""

    guard_mode: str = EnergyGuardMode.OFF.value
    monitored_bodies: int = 0
    unmonitored_bodies: int = 0
    energy_before: float = 0.0
    energy_after: float = 0.0
    energy_allowance: float = 0.0
    energy_excess: float = 0.0
    runaway: bool = False
    clamped: bool = False
    velocity_scale: float = 1.0
    bodies_put_to_sleep: int = 0
    bodies_woken_by_kinematic: int = 0

    @property
    def energy_delta(self) -> float:
        return self.energy_after - self.energy_before

    def state_record(self) -> dict[str, object]:
        return {
            "guard_mode": self.guard_mode,
            "monitored_bodies": self.monitored_bodies,
            "unmonitored_bodies": self.unmonitored_bodies,
            "energy_before": self.energy_before,
            "energy_after": self.energy_after,
            "energy_allowance": self.energy_allowance,
            "energy_excess": self.energy_excess,
            "runaway": self.runaway,
            "clamped": self.clamped,
            "velocity_scale": self.velocity_scale,
            "bodies_put_to_sleep": self.bodies_put_to_sleep,
            "bodies_woken_by_kinematic": self.bodies_woken_by_kinematic,
        }


@dataclass(frozen=True, slots=True)
class BodyMotionSample:
    """Velocity/timer state captured at the start of a fixed step."""

    linear_velocity: Vec3
    angular_velocity: Vec3
    sleep_time: float


def is_moving_kinematic(
    body: RigidBody,
    *,
    linear_limit_sq: float,
    angular_limit_sq: float,
) -> bool:
    return body.body_type is BodyType.KINEMATIC and (
        body.linear_velocity.length_squared() > linear_limit_sq
        or body.angular_velocity.length_squared() > angular_limit_sq
    )


def kinematic_driven_island_ids(
    graph: IslandGraph,
    bodies: dict[str, RigidBody],
    *,
    linear_limit_sq: float,
    angular_limit_sq: float,
) -> frozenset[str]:
    """Islands anchored (by contact or joint) to a moving kinematic body."""

    driven: set[str] = set()
    for island in graph.islands:
        for anchor_id in island.anchors:
            if is_moving_kinematic(
                bodies[anchor_id],
                linear_limit_sq=linear_limit_sq,
                angular_limit_sq=angular_limit_sq,
            ):
                driven.add(island.island_id)
                break
    return frozenset(driven)


def wake_kinematic_driven_islands(
    graph: IslandGraph,
    bodies: dict[str, RigidBody],
    *,
    linear_limit_sq: float,
    angular_limit_sq: float,
) -> int:
    """Wake sleeping islands that a moving kinematic body touches.

    Island propagation only links dynamic bodies, so without this a moving
    platform or door would sink straight through a sleeping crate.
    """

    driven = kinematic_driven_island_ids(
        graph,
        bodies,
        linear_limit_sq=linear_limit_sq,
        angular_limit_sq=angular_limit_sq,
    )
    woken = 0
    for island in graph.islands:
        if island.island_id not in driven:
            continue
        for body_id in island.dynamic_bodies:
            body = bodies[body_id]
            if not body.awake:
                body.wake()
                woken += 1
    return woken


def joint_exchanges_energy(joint: JointConstraint) -> bool:
    """Joints with an internal energy reservoir or actuator."""

    if isinstance(joint, SpringJoint):
        return True
    if isinstance(joint, (HingeJoint, SliderJoint)) and joint.motor_speed is not None:
        return True
    return False


def unmonitored_body_ids(
    graphs: tuple[IslandGraph, ...],
    bodies: dict[str, RigidBody],
    *,
    linear_limit_sq: float,
    angular_limit_sq: float,
) -> frozenset[str]:
    """Bodies whose energy legitimately exchanges with unmodelled reservoirs.

    Moving kinematic anchors, springs and motors can add mechanical energy
    without any accounting in K + U, so those islands are excluded from the
    runaway check instead of producing false alarms.
    """

    excluded: set[str] = set()
    for graph in graphs:
        driven = kinematic_driven_island_ids(
            graph,
            bodies,
            linear_limit_sq=linear_limit_sq,
            angular_limit_sq=angular_limit_sq,
        )
        for island in graph.islands:
            if island.island_id in driven or any(
                joint_exchanges_energy(joint) for joint in island.joints
            ):
                excluded.update(island.dynamic_bodies)
    return frozenset(excluded)


def body_mechanical_energy(body: RigidBody, gravity: Vec3) -> float:
    return kinetic_energy(body) + gravitational_potential_energy(body, gravity)


def external_work_bound(
    body: RigidBody,
    before: BodyMotionSample | None,
    dt: float,
) -> float:
    """Upper bound on work done by the body's live force/torque in one step."""

    force = body.force.length()
    torque = body.torque.length()
    if force == 0.0 and torque == 0.0:
        return 0.0
    v_before = before.linear_velocity.length() if before else 0.0
    w_before = before.angular_velocity.length() if before else 0.0
    v_peak = max(v_before, body.linear_velocity.length())
    w_peak = max(w_before, body.angular_velocity.length())
    work = dt * (force * v_peak + torque * w_peak)
    # Work accrued while accelerating from the start-of-step speed.
    work += 0.5 * dt * dt * force * force * body.inverse_mass
    return work


def clamp_scale(kinetic_after: float, excess: float) -> float:
    if kinetic_after <= 0.0:
        return 1.0
    target = max(0.0, kinetic_after - excess)
    return math.sqrt(target / kinetic_after)


class EnergyDriftMonitor:
    """Track mechanical-energy drift of a world across many fixed steps.

    ``observe`` is called after each ``PhysicsWorld.step``.  ``max_gain`` is
    the largest rise of K + U above the reference sample; a stable scene with
    no external input must keep it within a small tolerance.
    """

    def __init__(self, world: object) -> None:
        measure = getattr(world, "measure", None)
        if not callable(measure):
            raise PhysicsValidationError("EnergyDriftMonitor requires a PhysicsWorld")
        self._world = world
        self._samples: list[float] = [self._energy()]

    def _energy(self) -> float:
        return float(self._world.measure().mechanical_energy)

    @property
    def reference(self) -> float:
        return self._samples[0]

    @property
    def samples(self) -> tuple[float, ...]:
        return tuple(self._samples)

    def observe(self) -> float:
        energy = self._energy()
        if not math.isfinite(energy):
            raise PhysicsValidationError("mechanical energy became non-finite")
        self._samples.append(energy)
        return energy

    @property
    def max_gain(self) -> float:
        return max(sample - self.reference for sample in self._samples)

    @property
    def max_loss(self) -> float:
        return max(self.reference - sample for sample in self._samples)

    @property
    def final_drift(self) -> float:
        return self._samples[-1] - self.reference

    def bounded(self, *, gain_tolerance: float) -> bool:
        if not math.isfinite(gain_tolerance) or gain_tolerance < 0.0:
            raise PhysicsValidationError("gain_tolerance must be finite and non-negative")
        return self.max_gain <= gain_tolerance
