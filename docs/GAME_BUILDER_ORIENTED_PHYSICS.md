# Advanced Physics — Authored Rotating Geometry & Contact Manifolds

**Date:** 2026-10-12 (Europe/Oslo)  
**Dependency chain:** Game Builder #3642 → Advanced Physics #3661 → Moving-Body CCD #3662 → this oriented-geometry milestone.  
**Runtime maturity:** source-bound reference mechanics. No native Godot parity or hardware certification is claimed.

## Actual mechanics

- **Rotated original geometry:** physics authoring now accepts exact optional 2-axis `shape_half` for every dynamic body, a source-bound `initial_orientation` in millidegrees, and an optional fixture `orientation`. These fields are validated with the same collision procedure used by the runtime. Source changes produce new scene digests; clients cannot mutate collider dimensions or signed originals through replay.
- **Deterministic rotation:** orientations are evolved by the previous finite angular impulse system. A hard-coded 91-value quarter-wave integer lookup supplies sine and cosine in fixed-point at 1-degree resolution. Runtime trig does not depend on operating-system libm; canvas trig is strictly visual and not authoritative.
- **Four-axis SAT narrow phase:** rotating 2D rectangles use both face normals from each shape to test separating axes, derive penetration and a plausible support-point contact. Manifolds have frame, kind, signed normal, penetration depth and point, retained as the latest 16 records (bounded replay payload).
- **Actual contacts:** oriented dynamic bodies exchange mass-weighted impulses, are separated along the SAT normal, and can transfer impact spin and experience break thresholds. Authored oriented static fixtures deflect and apply tangential contact friction. Rotated corners are constrained to the floor and authored world limits, not a fake bounding-circle position check.
- **3D limitation:** bodies are z-extruded oriented XY rectangles with real depth gating. This is *not* free-rotation 3D hull SAT or a quaternion solver.
- **Opt-in compatibility:** the `collision_geometry` choice remains `aabb` by default. Existing reference physics scenes and dynamic/static sweep paths keep their prior semantics. Opting into `oriented_box` activates the SAT narrow phase. **Continuous swept collision for rotating boxes remains unimplemented**; rotated contacts are sampled by authored substeps. Do not assert certified rotational CCD.
- **User experience:** the original game studio now draws rectangles at verified body orientation and shows the count of actual SAT contacts. Browser rendering cannot rewrite authoritative simulation state.
- **Controls:** Physics has **34 typed settings** and 27 registered commands; new settings are the collision geometry policy and tangential contact-friction coefficient.

## Test evidence versus results

- A new 12-case adversarial `tests/test_game_builder_advanced_physics_oriented.py` suite covers true rotated SAT separation, real torque/contact reactions, geometry identity/source digests, z-separated extruded 3D hulls, fixture rotation, tamper rejection, bounded contact receipts and backwards-compatible AABB.
- Exact-head Windows/Ubuntu Game Builder Advanced System Engines workflow explicitly includes the source module, tests, Python compilation and full existing reference engine suite.
- The earlier #3662 CI finished on both platforms with the **same six failures outside the SAT changes**: stale fixed engine-count assertion, invalid fighting stamina/parry exception assumption, stale guard AI expectations, wrong rollback config source and quest event-rule test using a trigger excluded by the one-rule setup. They are corrected in this stacked milestone with actual normalized source invariants and event paths, not with catch-all skips. CI for this new commit must establish whether the corrections are sufficient.
- Tests are not certified green until exact head run completes; PR must remain draft.

## Timestamped change history

- **2026-10-12:** original fixed-point physics (improvement: tangible bodies, impulses and gameplay objective instead of configuration-only authoring).
- **2026-10-12:** moving-body swept CCD and angular impulse path (improvement: crossing bodies and finite spin).
- **2026-10-12:** fixed-point rotating SAT boxes, contact record and fixture response (improvement: non-axis-aligned original geometry now changes gameplay).
- **2026-10-12:** authored collider custody and scene validation (improvement: clients cannot inject a free collider or overlap a signed starting asset).
- **2026-10-12:** six independently observed CI regressions addressed (improvement: current game families measured against actual AI behavior, normalized source and semantic event rules).

## Next high-value work

Run exact-head CI, repair actual regressions, then implement continuous **rotating** convex narrow phase, broad-phase acceleration, proper resting-contact stabilization, certified Godot reference parity and cross-family physics coupling. Production claims require real-device benchmarks and original-asset rights review.
