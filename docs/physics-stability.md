# Physics fixed-step stability: sleeping and energy-drift guard

Module: `skeleton/simulation/physics/stability.py`, wired into `PhysicsWorld.step`
(`skeleton/simulation/physics/world.py`). Tests:
`skeleton/testing/test_simulation_physics_stability.py`.

## Sleep / wake policy

An island (connected set of dynamic bodies via contacts/joints) sleeps only when
**every** body in it has been quiet for `PhysicsSettings.sleep_after_steps`
consecutive fixed steps (`ceil(sleep_after_seconds / fixed_dt)`; 0.75 s → 45
steps at 60 Hz). A body is quiet when, for that step:

- linear speed < `sleep_linear_speed` and angular speed < `sleep_angular_speed`;
- no live external force or torque is applied;
- its in-step velocity change (impulse / mass) < `sleep_velocity_change`
  (catches solver jitter that flips sign while staying under the speed limit);
- no *moving* kinematic body touches or is jointed to its island.

The counter is kept in whole steps (`round(sleep_time / dt)`), so the sleep tick
is exact and identical across worlds and replays.

Sleeping islands are **frozen**: `solve_islands` skips any island with no awake
dynamic body, so resting position correction cannot drift or wake them, and
they cost nothing per step.

Wake triggers: `RigidBody.wake()` (impulses/forces), contact with an awake
dynamic body (island propagation wakes the whole island), and contact with a
moving kinematic body (`wake_kinematic_driven_islands`), so moving platforms and
doors never pass through sleeping crates.

## Energy-drift guard

`PhysicsSettings.energy_guard` (`EnergyGuardMode`) monitors kinetic +
gravitational potential energy of the monitored dynamic bodies each step:

| Mode     | Behaviour on runaway                                                     |
|----------|---------------------------------------------------------------------------|
| `OFF`    | No monitoring (default).                                                  |
| `REPORT` | Records `runaway=True` and `energy_excess` in the step's `StabilityReport`.|
| `CLAMP`  | Removes the excess kinetic energy by uniformly scaling awake velocities.  |
| `RAISE`  | Raises `PhysicsStabilityError`; the world rolls the step back exactly.    |

Allowance per step = bounded work from live external forces/torques
+ `energy_growth_tolerance` × start-of-step kinetic energy + `energy_absolute_slack`
+ `m·|g|·energy_position_slop` per monitored body (contact/joint position correction).

Islands driven by moving kinematic bodies, springs, or motorised hinge/slider
joints exchange energy with unmodelled reservoirs and are **excluded** from the
check (`unmonitored_bodies` in the report) instead of raising false alarms.

Each `StepReceipt` carries a `StabilityReport` (`energy_before/after`,
`energy_allowance`, `energy_excess`, `runaway`, `clamped`, `velocity_scale`,
`bodies_put_to_sleep`, `bodies_woken_by_kinematic`).

## Drift monitoring over many steps

`EnergyDriftMonitor(world)` samples `world.measure().mechanical_energy` after each
`observe()` call and exposes `max_gain`, `max_loss`, `final_drift` and
`bounded(gain_tolerance=...)`. A quiet stack with no external input must stay
within a small gain tolerance.

## Determinism

All loops run in sorted body-id order with plain float arithmetic. Sleep timers
are part of snapshots, so replay and snapshot-restore across a sleep boundary are
bit-identical. Total solver iterations per step are capped at
`MAX_TOTAL_SOLVER_ITERATIONS` (256).
