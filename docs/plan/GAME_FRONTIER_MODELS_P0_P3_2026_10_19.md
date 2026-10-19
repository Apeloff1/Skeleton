# Frontier game model milestones — P0→P3 (2026-10-19)

## Owner, precedence and truth in advertising

Owner remains `skeleton/jeeves/` game capability, `skeleton/forge/` materialization,
`skeleton/ai/game_builder/` candidate and rights controls, `skeleton/game/`
authoritative engine scenes, and `skeleton/ai/training/` governed weight promotion.
Do **not** create a competing model-provider route, ledger, persistence root or
engine authority. Model calls must pass existing
`skeleton/provider_runtime.py` and mandatory architecture acknowledgement.

These source modules implement a functional deterministic **baseline**, not
replicas or checkpoints of Genie 3, LingBot-World 2.0, HY-World 2.0, SIMA 2,
Microsoft Muse/WHAM-RT, TRELLIS.2, or NVIDIA Cosmos. All seven are inspiration
targets; verify license/availability/real checkpoint identity before adapters
become enabled. See [To-Do](../../TODO.md) for tracked task statuses.

## Dependency order and outputs

| Phase | Delivery | Implemented candidate | Open proof |
|---|---|---|---|
| P0.1 | Weather and cloud movement | altitude-interpolated wind, seeded spatial-temporal gusts, midpoint cloud advection, shear/stretch | renderer/cloud particle integration, native weather visual proof |
| P0.2 | FPS mode selector | exact integer nanosecond 30/50/120 presentation scheduler and old-frame dropping | host clock/input integration, actual measured throughput |
| P0.3 | Per-era skeletal LOD | generated closed bone-envelope triangle mesh, rigid bone influence, budgets from early 3D to next era | weighting/normal/UV seams, import/export and 3D visual QC |
| P0.4 | Animated sim assets | sampled clips, hierarchy transforms, per-bone collision capsules | dynamic capsule deformation in actual sim, clip interoperability |
| P0.5 | Cognition and cinematics | evidenced target selection, reason traces, proposed actions/camera shot class | visual-semantic model, multi-shot blocking continuity, 3D camera controls |
| P0.6 | Input prediction | 0–500ms bounded linear player extrapolation, confidence upper bound | learned visual-conditioned prediction and calibration |
| P0.7 | World-axis generator | continuous spatial noise for terrain, biome, climate, sky islands, wind volatility | Cosmos-like learned world generation, streaming multi-axis project compiler |
| P0.8 | Typed composition | content-addressed scene candidate, explicit model readiness and non-execution claims | acceptance into canonical engine runtime and importers |
| P1 | Model serving and visual understanding | none | checkpoint readiness, visual learned rollout, action-conditioned model, 3DGS/depth/mesh outputs |
| P2 | Autonomous agent+training | existing Jeeves scaffolds; no new weights trained | controller action loop, source-attributed visual learning and held-out competence |
| P3 | Live production release | no production qualification | GPU benchmarks, Godot/console export, long-horizon tests, governed canary promotion |

## Concrete public contracts

- `game_frontier_dynamics.py`: `WindField.sample(x_m,y_m,altitude_m,time_s)` returns `WindVector`.
  `advect_clouds` returns immutable cloud candidates using second-order
  midpoint advection; the wind vector is never mistaken for a pixel renderer.
- `PresentationClock(fps)` accepts 30, 50, 120. `deadline(index)` uses
  `origin_ns + floor(index * 10^9/fps)`, preventing long-run float drift.
  `due` is permitted to drop **presentation** frames, never physics ticks.
  Native 120fps performance is not guaranteed by a scheduler.
- `generate_world_cell` depends only on seed, XY and `WorldAxis`; sky-island
  flags are derived, not a completed open-world 3D generator.
- `game_frontier_production.py`: `skeleton_to_polygon` takes a typed bone
  hierarchy and an era, emits actual triangles, collision envelopes and bone
  influences. Source geometry is a tube-like skin, not reconstructed HY meshes.
- `AnimationClip` and `pose_skinned_mesh` yield posed vertices, preserving the
  rest mesh and hierarchy. They do not replace production skinning, FK/IK,
  weighting, collision solvers or root motion.
- `plan_cinematic` and `reason_about_world` propose only evidence-supported
  decisions. User tasks, game controls, objectives and story canon remain
  game-engine authority; no native model is claimed.
- `anticipate_user_motion` produces a proposal with `authority` set to
  `speculative_never_auto_execute`. A predicted user action is never fired.
- `compile_frontier_scene` composes all of the above into a portable candidate
  manifest, SHA-256 identity and transient skinned geometry; `approved_for_runtime`
  remains false pending engine validation and explicit authorization.

## Acceptance gates (fail-closed)

1. **Correctness** — deterministic seeds, finite numeric guards, invalid-geometry
   rejection, topology-ordered bones, bounded budgets, monotonic frame deadlines.
2. **Temporal** — compare simulation state at 30/50/120 against same physics
   tick sequence; presentation FPS may not change authoritative gameplay.
3. **Weather** — independent snapshots of cloud paths, strong-altitude shear,
   wind direction shifts, tile boundaries and negative/large world coords.
4. **Geometry** — multiple skeletons and animation clips through actual Godot
   imports and render frames; check colliders and topology, per-era triangle
   ceiling, normal/UV/material integrity and current renderer semantics.
5. **Inference** — only count learned-model milestones when the real model
   checkpoint is loaded, weights/version/rights checked, and measured sampled
   frames/actions carry source identity. No text-only claims or synthetic scores.
6. **Reasoning** — tie every proposed NPC/cinematic objective to observable
   scene evidence; abstain or inspect when evidence is absent.
7. **Anticipation** — never execute predictions; calibration, cancellation,
   latency, rollback and stale-time checks are required before UI enablement.
8. **Rights** — model weights, videogame data, reference ROMs, visual artifacts,
   trademarks and music each have declared lawful source and permitted scope.
9. **Security** — no dynamic code execution from generated scenes or remote
   assets, no cross-plane provider bypass and no model-generated authoritative
   state.
10. **Operational** — process supervision, backpressure, bounded resource usage,
    durable checkpoints, crash recovery, metrics, operator controls and release
    rollback supported before P3 closure.

## Suggested improvements beyond the seven asks

- Support volumetric cloud density, precipitation, local storm systems,
  occlusion-aware cloud shadows, aerodynamics, acoustic wind and tree response.
- Use deterministic low-frequency weather simulation ticks and adaptive
  weather/asset render LOD so 120 Hz display mode never accelerates physics.
- Blend learned world-frames with persistent engine geometry via an explicit
  generated-versus-authoritative provenance mask; never feed generated frames
  back as independent truth without real observation verification.
- Expand axis vocabulary with topology, tectonics, underground caverns,
  orbital biomes, day/night, culture, transportation, magic, city density and
  life-cycle ecology while retaining seeded backward-compatible generation.
- Add adaptive skeletal decimation preserving silhouette, bone weight
  assignments, facial rigs and gameplay-critical hitboxes.
- Use goal-specific cinematic shot grammar: continuity axes, moving subjects,
  camera velocities, cuts, focal length, exposure, depth-of-field and
  accessibility/camera comfort constraints.
- Train next-action predictions against consented event sequences, rewarding
  calibration and safe abstention rather than apparent user anticipation.
- Run Dragon/Jeeves/adversary paired experiments with native emulator and
  deterministic-engine evidence, and separate model training from inference.
- Add accessibility and frame-budget profiles for older devices, mobile,
  contemporary desktop and dedicated console targets.
- Add quantitative scorecards for scene continuity, interaction success,
  physics plausibility, visual fidelity, long-horizon state restoration and
  real generated vs displayed FPS at 30, 50 and 120.

## Verification record

Source and tests are committed on a feature branch. No actual model
inference/checkpoint training, live GPU benchmark, engine installation or
console hardware acceptance has been performed as part of this milestone.
Do not represent P0–P3 as fully done until the To-Do checkboxes carry accepted
exact-head run and review evidence.
