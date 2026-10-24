# Jeeves Frontier Advanced Physics: P0→P3 assurance dossier

Date: 2026-10-19. Source branch: `feature/game-frontier-p0-p3-20261019`.
This extends the canonical game-owner planes rather than establishing a new
service, checkpoint trainer, durable store, or owner. It is a deterministic
**candidate reference** simulation; model/GPU/native acceptance remains open.

## L00 — intent and reference physics

- Terminal velocity uses SI `sqrt(2 m g / (rho Cd A))`. Character weight,
  aerodynamic area, posture-dependent drag and altitude-dependent wet-air
  density are explicit quantities.
- Drafting is downwind shelter behind a 3D wake source with finite width,
  attenuation and depth. It is not an arbitrary speed buff or free energy.
- Rising/sinking thermal columns depend on 3D location and distance from
  the ground patch; turbulence is deterministic in seed, space and time.
- Climbing is evaluated from normal force, slope gravity, wet/icy friction,
  loose rock, deformable surface, footwear, stamina, strength, carried
  equipment and foothold/rope force. Vertical climbing requires support.
- Contact response uses mass, sphere inertia, relative normal and tangential
  velocities (including spin), normal restitution, Coulomb friction, positional
  correction, measured energy loss and linear momentum residual.
- Continuous swept-sphere and sphere-plane contact time detects faster-moving
  actors and objects even when the discrete endpoints do not overlap.
- Microclimate evolves ground water, ice, sediment, pressure-gradient wind
  and temperature-driven uplift. Reference dynamics do not claim real weather.

## L01 — ownership and path

`skeleton/jeeves/game_frontier_advanced_physics.py` owns bounded physics
candidate helpers. `game_frontier_weather_physics.py` supplies optional
microclimate parameters; existing `game_frontier_motion.py` continues
handling previous character/material references. `game_frontier_realism.py`
audits cross-domain scene receipts without changing their authority.
`game_frontier.py` opts into advanced simulation through explicitly typed
body/aero/traction/climber arguments. Godot export stays in
`skeleton/forge/game_frontier_godot.py`. No provider calls.

## L02 — data contracts and schema

- `RigidBody`: mass, radius, position, velocity, angular velocity, material
  restitution and friction.
- `AeroProfile`: aerodynamic area, drag/lift coefficients and acceleration
  cap; `WakeSource`, `UpdraftColumn`, `Airflow` include explicit units.
- `TractionSurface`, `Climber`, `TractionDecision` separate environment
  fact, character ability and advisory movement proposal.
- `CollisionContact`, `CollisionResolution`, `SweptContact` provide
  geometry, impulse, energy, momentum and ToI evidence.
- `Microclimate` and `WeatherTerrainStep` bind physically derived ground
  wetness, ice and erosion to traction.
- `advanced_physics` scene manifest remains optional and
  `authority=candidate_only_no_native_mutation`.

## L03 — runtime sequencing

1. Resolve canonical game world/weather and legal source assets.
2. Construct deterministic wind/wake/updraft/microclimate fields.
3. Advance aero body through bounded physics substeps using wet-air density,
   quadratic drag, gravity and lift.
4. Evaluate climbing from updated terrain and character input.
5. Resolve explicit contact impulses; swept collision detection is currently
   a library helper awaiting canonical native integration.
6. Aggregate physics invariants and source-evidence digest.
7. Export source scene and native preview without authorizing main-level
   mutation, introducing secondary engines or claiming model weights.
8. Canonical engine import, user review and source-validation gates precede
   promotion to live gameplay.

## L04 — physics invariants

`mass>0`; `drag_coefficient>0`; `area>0`; density positive; all numerical
states finite/bounded. Dual-body contacts must conserve total linear momentum
within the validated floating-point tolerance. Restitution is bounded 0..1;
friction impulses may not reverse tangential relative motion beyond the
Coulomb limit. Reference collision kinetic energy must not increase.
Wind-driven systems can **exchange** energy with ambient air, so their kinetic
energy is not globally required to decrease. Aerodynamic dissipation is
evaluated in the relative-flow frame. Surface traction and ice fractions
stay within their declared bounds. Mass of the separate liquid grid is
verified through rain/evaporation receipts. GPU tests remain unexecuted.

## L05 — data governance and rights

No model weights are loaded; no external SDK calls; no copyrighted ROM asset
import. Native platform target data, user-generated world contents and all
later training sets must pass existing provider/rights/provenance owner gates.
Physics source alone is not evidence of license or generated-world legality.

## L06 — failure and recovery

Every finite bound fails closed. Invalid unit normal, negative mass, out-of-
envelope timestep, malformed contact, corrupt input body or absent required
opt-in class raises typed/validated error. Long-duration active runs subdivide
into bounded substeps with maximum 1024; exceed that and request host-level
chunking, never silently truncate simulation. Statelesness allows replay
using the original seed and typed state; durable checkpointing is the
existing engine's responsibility, not a new mutable store.

## L07 — verification

Focused regressions cover mass/area/altitude terminal speed effects, wake
shadow direction, thermal uplift, gust determinism, wet/ice/gravel
climbability, cargo load/wind forces, weighted impacts, spin and friction,
energy loss, head-on momentum, collision with static ground, high-speed
sphere-sphere and sphere-plane ToI, unobserved optional scene backward
compatibility, rain/freeze/thaw and ground convection. The opt-in source scene
must also retain hashed candidate, environment and Godot export identity.
Exact-head focused CI must pass; passing unit tests alone is **not** evidence
of verified real 3D native physics, Godot compiler, console or GPU frames.

## L08 — performance and economics

CPU reference complexity: `O(wakes+thermals)` per body/tick, small constant
per isolated contact and `O(microclimate fields)` per patch. The 14-domain
audit scans bounded manifest collections. Optional physics runs are
explicitly off for ordinary scene candidates. Per-call wake and thermal
counts are limited to 128 each; contacts and numerical timesteps are bounded.
Native broadphase acceleration, GPU particle advection and CCD manifold
scale benchmarks remain P1–P3.

## L09 — operational control

Physics is opt-in per candidate request. Distinct sources for initial
position, weather, climber capability, terrain material, motion proposal
and contact geometry; no autonomous input injection. Debug Godot body uses
its own native collision material and re-evaluates relative wind drag per
engine physics tick, but cannot assert downstream simulation correctness.
Fail-closed absence of source rights and model/runtime readiness remains.

## L10 — metrics and telemetry

The realism ledger exposes up to fourteen participating/missing domains:
aerodynamics, climbing, collision, atmosphere, liquid, tides, light,
leaf_shadow, characters, environment, structures, biome, audio and chunks.
Its output contains unit-labeled measurements, explicit invariant names,
pass/fail booleans, source-evidence identity and missing-domain disclosure.
It never turns an absent domain into a zero-valued implied measurement or
a fictitious aggregate `100% realism` grade. True solver residuals,
native profiler captures, device temperature and frame latency must be
measured separately.

## L11 — user experience and inspectability

The scene manifest exposes current body mass/radius, 3D velocity and spin,
air density, wake shelter, updraft and turbulence vectors, drag dissipation,
slope and climb result, collision impulse and energy, terrain wet/ice,
friction, environmental motion and hashed source receipts. Future Jeeves
and Galaxy Studio UI should render a 3D vector field, collision normal,
force vector, contact manifold, climb foothold and timeline scrubbing.

## L12 — deployment and canary

Native Godot render physics, Windows installer, era engines and console
targets stay unqualified until they import source scenes with actual
fixed-timestep playback, no collisions tunneling, and profiled CPU/GPU
budgets. Compare against deterministic baseline and preserve rollback.
Prototype Godot viewer is separate from authoritative production controls.

## L13 — research, adversarial and release signoff

Held-out slopes, changing weather, different densities/body shapes, high-
velocity bodies, multibody contacts, terrain deformation and 6-month world
states require independent adversarial validation. Determine exact native
fixed-step replay equivalence across 30/50/60/120 presentation modes.
Adopt published/controlled physical benchmark scenes and document
precision, numerical convergence, CPU/GPU tradeoffs and acceptable error.
Do not sign P0–P3 production closure based on reference-only code.

## P0–P3 open edges

P0 must still connect CCD/manifold, physics contact callbacks and chunk
verification into *each actual native engine*, verify Godot runtime import,
and expose scoped controls. P1 needs advanced broadphase, measured updraft
field resolution, aerodynamics/cloth/liquid coupling and IK. P2 adds actor
perception, autonomous traversal and multiactor adversarial tests. P3 is
long-horizon state parity, native benchmarks, operator documentation,
rollback, provenance and first-install/export evidence.


## 2026-10-19 continuation — body mass, ElasticBodySkin3D, instruments and RPG triggers

### L00–L02: owner, mathematics and typed contracts

- `game_frontier_body_balance.py` derives total and carried mass, 3D COM,
  symmetric inertia tensor with spherical-segment intrinsic inertia, dynamic
  balance offset, signed support-polygon margin and approximate per-foot loads.
  Contact-load sharing is a bounded inverse-distance estimate; native
  contact Jacobian, actual center of pressure and locomotion stability remain
  separate work.
- `game_frontier_elastic_skin3d.py` implements the `ElasticBodySkin3D`
  wrapper for canonical `CharacterSkeleton`, `SkinnedMesh`, `AnimationClip`.
  It uses indexed triangle adjacency, current-pose bone anchors, explicit
  pinned vertices, wind/impact/gravity, temperature-sensitive shear stiffness,
  wetness-influenced mass, bounded substeps and poststep link-strain projection.
  Output is an immutable vertex snapshot with source geometry digest,
  collision count and strain evidence. This is not anatomically validated FEM.
- Godot `skeleton/forge/game_frontier_godot.py` exports a preview
  `SoftBody3D`, preserving **shared indexed vertices** in `ArrayMesh`:
  triangle-soup faces would disconnect the deformable topology.
  `SoftBody3D.set_point_pinned`, total_mass, damping_coefficient,
  linear_stiffness and native cast shadows are set from bounded candidate data.
  It does not yet attach these pins to a running Skeleton3D rig, simulate
  multiphysics clothes or prove Godot/Jolt engine parity.
- `game_frontier_instruments.py` implements six instrument families:
  gyroscope, magnetic compass, natural-horizon sextant, artificial-horizon
  bubble sextant, calibrated pressure altimeter and trigonometric survey
  altimeter. ENU coordinates; sextant sighting uses **supplied** celestial
  directions, not invented ephemerides or GPS; `NavigationEnvironment`
  declares latitude/longitude/altitude, magnetic declination, dip, local
  anomaly, pressure, temperature and acceleration. Altimeters expose metre
  and feet readings and calibration source. Gyro source rate/bias/drift are
  supplied; it is Euler reference not full INS fusion.
- `game_frontier_character_suite.py` composes the above into one typed
  optional game-scene pass, with deterministic source receipts and exactly
  one candidate-only authority flag.

### L03–L05: advanced RPG triggers and source custody

- `skeleton/forge/game_frontier_rpg_events.py` registers numeric and edge
  comparators, ranges, hysteresis, bounded cooldowns, prerequisite quest flags,
  priority ordering, and conflict resolution by channel plus target. Events
  include climate, lunar/solar tide, air density/altitude, shadows, rain, wind,
  slip/ice, compression/skin strain, equipment mass, collision impulse,
  instrument readings, game quests, party morale and environmental changes.
- The existing `game_frontier_studio.py` now permits typed environmental
  event pages alongside legacy interaction events with explicit ID separation.
  Its catalog exposes new authoring tools for rig skin, physical mass painter,
  center-of-mass visualization, navigation calibration, instrument tables,
  RPG event triggers and environmental timelines.
- The scene composer fills event signals from **existing scene-derived
  observations** (weather, pressure, tides, physics contacts, microclimate,
  light, structures, biome, sonar-like audio and instruments). Explicit
  conflicting values are rejected; incomplete signals are disclosed.
- Trigger actions remain proposals and are never executed in the exporter.
  Godot inspection prints `SIMULATED INSTRUMENTS (NOT GPS)` and
  `RPG ENVIRONMENT PROPOSALS (NOT EXECUTED)`.

### L06–L09: fail-closed behaviors

Invalid load distribution (duplicate segments, insufficient support polygon,
negative weights), invalid skin mesh/pins, nonfinite fields, incompatible
instrument prerequisites and inconsistent event signal sources are rejected.
Sensor gyroscope bias and secular drift, magnetic declination, index
errors, bubble tilt and atmosphere assumptions are explicitly visible.
Horizon sextants reject obscured natural horizons; bubble sextants remain
measurable with instrument-attitude bias and must not be confused with natural
sextant results. Non-opt-in scene candidates retain the prior static geometry.
Environment events only read canonical clock and last-fired receipts.

### L10–L13: evidence and unclosed native work

Focused GitHub Actions run `39192950014` passed **121 tests** at source
commit `f6b7c551c165538a492c3ee509ab1f45fcbbba27`.
This checks the combined scene source, exports, weight invariants,
instrument observations, event ordering and backward compatibility.
It is not a native Godot import or a measured physics performance run.
Current tracked P0–P3 To-Do: **199** milestones, with 73 checked as committed
source and 126 remaining.

> **GF-N status correction (2026-10-24, Jenkins):** the counts above are stale. `TODO.md` on `feature/game-frontier-p0-p3-20261019` @ `1dc834eb6` tracks **361** items (P0 194, P1 65, P2 51, P3 51): **151** checked (all P0), **210** open. Evidence: `grep -c` of `- [x] GF-P` / `- [ ] GF-P` in TODO.md at that commit. Open drafts are listed under `## Pending in draft` in TODO.md.

Required next steps: Godot 4 headless parse and screenshot of indexed
SoftBody3D, direct bone/pin attachment, collision+skin volume preservation,
multi-material tissue rig, world authority dispatch of RPG actions,
save/restore of calibration/cooldowns, real ephemeris and astronomical
positioning, mass/grip replay equivalence at 30/50/60/120 FPS, and historical
console/modern mobile/GPU budget qualification.
