# Advanced Game Physics — Continuous Dynamic Contacts and Rotation

**Implementation date:** 2026-10-12 (Europe/Oslo).  
**Parent implementation:** Game Builder PR #3642 → Physics PR #3661 → this stacked continuation.  
**Maturity:** Executable deterministic *reference* mechanics. Native engine parity and release checks are not certified.

## What materially changed

1. **Moving-body continuous collision detection.** A second deterministic solver computes time of impact for two original axis-aligned moving bodies using exact fractional relative swept-AABB intervals. It detects head-on passes even when no objects overlap at the end of the frame. It uses the same exact authored collision masks, mass values, materials and fracture thresholds as the discrete reference; low-cost paths with no encounter do nothing. The later portion of the colliding pair's substep is conservatively lost instead of fabricating post-impact future positions. Collision event receipts identify the actual elapsed substep, counters and authoritative state.
2. **High-speed static-fixture fix.** The original swept-fixture check incorrectly required the slab's exit time to occur during the current frame. Entry before the frame ends and exit later is still a collision. It is now correctly admitted, addressing thin-wall tunneling on short partial penetration.
3. **Angular state, not a decorative slider.** Every original body maintains source-replayed angular velocity and 0–359,999 millidegree orientation. Source-authorized clockwise/counterclockwise torque spends the existing finite impulse budget; actual mass and radius bound the inertial response. Air-independent angular damping, maximum spin rate, impact-spin transfer from off-axis moving-body contact, and real rotational braking now affect simulation and studio rendering.
4. **Radial cable constraint.** A physically meaningful Euclidean two/three-axis rope constraint replaces the earlier independent axis box limits. Its authored cable length and rupture strength cause genuine radial position correction, outward velocity reduction and snapped-cable evidence when tension exceeds the limit. The existing original authored anchor and source custody remain unchanged.
5. **A new authoring ceiling for this one family.** Six new validated controls—maximum angular speed, angular damping, torque strength, contact spin transfer, material restitution and enabling/disabling moving-pair CCD—extend the Physics editor to **32 typed settings**. Physics now has **27 distinct registered commands**. All are integrated in the existing scene/session/save and authenticated local game studio, not a second runtime.
6. **Adversarial regression coverage.** The continuation adds **14 focused tests** on top of the earlier Physics tests: crossing fast-moving bodies, source masks, depth-separated flights, off-center spin, angular braking, torque budgets, true radial cable response, true tension rupture, thin-fixture CCD, typed-source denial, replay tampering and portable saves. The original physics editor setting-count test is updated to the new source-defined control count.

## Verification contract

- Every gameplay command is reconstructed from source-bound editor settings and optionally an authored scene by the canonical `advanced_gameplay_runtime`.
- Neither position, monetary/energy stocks, orientation, impulse receipts nor cargo victory comes from the requesting browser. Replayed record equality is mandatory for durable saves.
- Windows and Ubuntu exact-head advanced system CI explicitly include the new dynamics module and focused adversarial suite in `.github/workflows/game-builder-advanced-system-engines.yml`.
- **Results not yet observed:** no green cross-platform test, native Godot or consumer-device qualification is asserted merely because the source, suite and workflow are published.

## Boundaries

The advanced reference treats every body as a center-and-half-extent rigid AABB. Rotations are real inertial *state*, but do **not yet rotate the collision geometry**. Dynamic CCD is translational, multi-pair contacts resolve in stable authored order, and contact correction is conservative. This is not SAT/GJK/EPA contact manifolds, quaternion 3D rigid bodies, commercial-grade joints, an engine-certified GPU/fluid simulation or a release-ready replacement for mature game physics engines.

## Timestamped implementation history

- **2026-10-12:** initial physics runtime #3661 (improvement: actual authored 2D/3D world physics replaced settings-only authoring).
- **2026-10-12:** moving-body CCD implementation (improvement: relative swept trajectories catch pass-through collisions that endpoint overlap misses).
- **2026-10-12:** true radial rope and finite rotation (improvement: anchor tension and orientation evolve physically and consume authored action budgets).
- **2026-10-12:** high-speed fixture patch (improvement: partial-frame thin-wall collisions detected).
- **2026-10-12:** consistent material restitution and impact path response (improvement: authored physical policies constrain both continuous and discrete contacts).
- **2026-10-12:** visual studio, native workflow integration and regression source (improvement: playtesters can observe and independently replay the changed mechanics).

## Next high-value milestone

Independent exact-head execution and repair of failed regression cases are mandatory before review. Then add deterministic *rotating oriented convex-body* collision manifolds and cross-system physics adapters for original platformer, flight, sailing and modular authored worlds, each with independent native parity checks and performance profiling at actual target-device budgets.
