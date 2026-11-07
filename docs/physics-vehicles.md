# Raycast vehicles (`skeleton.simulation.physics.vehicle`)

Deterministic wheeled-vehicle dynamics on top of the fixed-step `PhysicsWorld`.

```python
from skeleton.simulation.physics import (
    BoxShape, PhysicsWorld, PlaneShape, RaycastVehicle, RigidBody, Vec3,
    VehicleControl, VehicleSettings, WheelSettings, step_vehicles,
)

world = PhysicsWorld()
world.add_body(RigidBody.static("ground", PlaneShape()))
world.add_body(RigidBody.dynamic(
    "car", BoxShape(Vec3(0.9, 0.3, 2.0)), density=250.0,
    position=Vec3(0.0, 1.0, 0.0), continuous=True,
))
wheels = tuple(
    WheelSettings(f"w{i}", Vec3(x, -0.3, z), steerable=z > 0, driven=z < 0, handbrake=z < 0)
    for i, (x, z) in enumerate(((0.8, 1.4), (-0.8, 1.4), (0.8, -1.4), (-0.8, -1.4)))
)
car = RaycastVehicle("car", VehicleSettings(wheels))
car.validate_stability(world)          # rejects springs/dampers the fixed step can't integrate
step_vehicles(world, ((car, VehicleControl(throttle=1.0, steer=0.3)),), steps=60)
```

## Model

Each tick, `RaycastVehicle.update(world, control)` runs before `world.step(1)`:

1. **Rays.** One ray per wheel from the chassis hardpoint along chassis-down
   (`rest_length + radius`), ignoring the chassis itself.
2. **Suspension.** Spring/damper impulse along the hit normal (never pulls),
   clamped to `max_suspension_force`. A fully compressed strut acts as a
   **bump stop** and removes its share of the closing speed, so hard landings
   don't push the chassis into the ground.
3. **Tires.** Drive, brake, handbrake, idle brake, rolling resistance and
   lateral grip impulses in the contact plane. Each wheel is limited by the
   friction circle `friction * suspension_impulse` (scaled by `handbrake_grip`
   while the handbrake is on). Resistive impulses can stop a wheel but never
   reverse it.
4. **Newton's third law.** Dynamic ground bodies get the opposite impulse.

Suspension and tire impulses are computed from **one shared velocity
snapshot (Jacobi)** and applied in fixed wheel order. A sequential solve picks
up a yaw bias from wheel order, and a symmetric car launched straight would
drift sideways. With this order it drives perfectly straight.

Axes: chassis forward is `+Z`, up is `+Y`. A positive steer input yaws
positively about up (toward `+X`). Steering is rate-limited (`steer_rate`).

## Determinism, rollback, sleeping

- Every step is plain float math in a fixed order. Independent worlds fed the
  same inputs produce identical `world.state_digest` and `vehicle.state_digest`.
- `vehicle.capture_state()` / `restore_state()` save and restore the
  vehicle-side state (steering, wheel spin, settle timer, last grounded count)
  alongside `world.capture_snapshot()` / `restore_snapshot()` for rollback.
- Vehicles use impulses, not force accumulators. So an idle, fully grounded,
  quiet vehicle parks: after `settle_after_seconds` the chassis sleeps and
  does no work until it gets non-idle input or something wakes it.

## Anti-tunneling

Mark the chassis `continuous=True`. The world's convex CCD then stops a
360 m/s chassis at a 0.1 m wall. Without CCD the same chassis skips the wall.
This PR also fixes a default-settings CCD crash: convex TOI stops within
`CONVEX_TOI_DISTANCE_TOLERANCE` (1e-6) of contact, but the default
`ccd_contact_slop` is 1e-7. So a box hitting a box face-on raised
"CCD TOI failed to produce a resolvable contact manifold". The world now closes
that leftover gap once, deterministically, before it gives up.
