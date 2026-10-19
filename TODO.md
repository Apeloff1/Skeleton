# To-Do — Game Frontier Models P0–P3

Updated: 2026-10-19. Owner: existing Skeleton Jeeves/game, game-builder, forge and AI training planes.
Tracking branch: `feature/game-frontier-p0-p3-20261019`.
Detailed acceptance map: [Game Frontier Model Milestones](docs/plan/GAME_FRONTIER_MODELS_P0_P3_2026_10_19.md).

**Status semantics:** `[x]` = source implementation committed to the feature branch
(not merged or necessarily verified); `[ ]` = open. Source implementation
is not permission to claim model parity, neural weights, benchmark proof, or
runtime release readiness. All inference/training keeps existing authority.

## P0 — Durable engine foundation / correctness first

- [x] GF-P0-01 Genie-inspired deterministic wind-field primitives with altitude interpolation, turbulence, temporal/spatial coherence.
- [x] GF-P0-02 Adaptive clouds with midpoint wind advection, shear-based stretch, per-cloud orientation, optional world wrapping.
- [x] GF-P0-03 LingBot-inspired exact presentation clocks at **30, 50, 120 FPS** with bounded catchup and physics-clock isolation.
- [x] GF-P0-04 World-axis generation for terrain, temperature, humidity, verticality, sky islands, volatility, biomes.
- [x] GF-P0-05 HY-World-inspired skeletal-bone-to-polygon meshes; reduce polygon counts by engine era and available triangle budget.
- [x] GF-P0-06 TRELLIS-inspired simulation-ready mesh data with bone influences, collision capsules, animation sample transforms.
- [x] GF-P0-07 SIMA-inspired evidence-linked cinematic shots plus inspect/approach/interact proposals (never autonomous mutation).
- [x] GF-P0-08 Muse-inspired bounded speculative user-motion prediction with no input firing.
- [x] GF-P0-09 Candidate-only shared composition façade with content-addressed receipts.
- [x] GF-P0-10 Add primitive and integration regression tests (execution/green CI not yet proven).
- [x] GF-P0-19 Add candidate-only model checkpoint, frame throughput and simulation-ready 3D evidence contracts.
- [x] GF-P0-20 Add independent license allowlist, external receipt identity, measured-versus-requested FPS checks.
- [x] GF-P0-21 Add opt-in 30/50/120 FPS bridge to canonical per-era simulation timing, with cross-mode tests.
- [x] GF-P0-22 Export Godot overlay scene with posed polygons, generated bone capsules, sky islands and source-wind cloud animation paths.
- [x] GF-P0-23 Add exporter custody/regression tests and apply 30/50/120 requested FPS cap to preview script.
- [ ] GF-P0-11 Run targeted tests and exact-head standard architecture, construction, interface and provider checks; fix any failures.
- [ ] GF-P0-12 Wire scene-candidate output into canonical Jeeves/Forge/Godot runtime and UI, through existing authorisation.
- [ ] GF-P0-13 Bind generated cloud geometry/render state to existing real raster renderer, not just metadata.
- [ ] GF-P0-14 Persist/restore world-axis and weather configuration under existing state authority, migrations, backups.
- [ ] GF-P0-15 Add model-weight readiness/rights/VRAM capability discovery to existing model registry and provider runtime.
- [ ] GF-P0-16 Add exact game environment adapters, deterministic replay and holdout dataset isolation.
- [ ] GF-P0-17 Confirm correct per-era bone-weighted mesh imports with actual Godot/headless output.
- [ ] GF-P0-18 Establish sustainable deadlines and resource envelopes rather than unbounded per-invocation memory use.

## P1 — Real neural generation and perception

- [ ] GF-P1-01 Implement provider-neutral action-conditioned frame/world generator adapter with negotiated input/output types.
- [ ] GF-P1-02 Deploy authorized real visual world-model checkpoint; record architecture and support matrix.
- [ ] GF-P1-03 Build continuous observation+action+camera history and compact, durable temporal latent/world memory.
- [ ] GF-P1-04 Add visual continuity, occlusion, viewpoint revisit and long-horizon drift evaluation.
- [ ] GF-P1-05 Implement variable-latency neural sampling with 30/50/120 FPS fallback, frame interpolation/drop policy and metrics.
- [ ] GF-P1-06 Add GPU/CPU fallback scheduling with adaptive graphics quality, render resolution, latency and power governors.
- [ ] GF-P1-07 Import HY-World-like licensed mesh/3DGS/depth/normal/camera outputs; validate source license and coordinates.
- [ ] GF-P1-08 Build skeleton-guided remeshing, bone correspondence, LODs, skin-weight transfer and seam-preservation metrics.
- [ ] GF-P1-09 Create TRELLIS-compatible legal image-to-3D ingestion and generate UV/PBR material maps and rig proposals.
- [ ] GF-P1-10 Verify animation-ready meshes with actual collision, walking, IK, root motion and sim tick playback.
- [ ] GF-P1-11 Give Dragon video/optical understanding via an approved checkpoint; ground semantic observations in frame evidence.
- [ ] GF-P1-12 Connect SIMA-like language goals, game controls, visual context and reasoned plan proposals.
- [ ] GF-P1-13 Add world-axis auto-generation request schema and adaptive weather/terrain/cloud visual constraints.
- [ ] GF-P1-14 Integrate grounded music, VFX, cinematic camera motion and synchronized event staging.
- [ ] GF-P1-15 Add visual 3D asset quality and IP similarity adjudication before promotion.

## P2 — Autonomous play, training, cinematics and scaled content

- [ ] GF-P2-01 Build an autonomous emulator closed-loop observe→reason→act→verify controller with authoritative state checks.
- [ ] GF-P2-02 Add SIMA-style world cognition: object permanence, physics consequences, affordance discovery and goal hierarchy.
- [ ] GF-P2-03 Add cinematographic reasoning: framing, camera movement, blocking, continuity, timing and subject tracking.
- [ ] GF-P2-04 Fuse camera, audio, HUD and controller input into grounded event timelines without confusing measurements/interpretation.
- [ ] GF-P2-05 Train prediction/calibration models for WHAM-style preemptive lookahead against recorded user action histories.
- [ ] GF-P2-06 Define prediction latency/confidence thresholds, cancellation and rollback to avoid speculative game actions.
- [ ] GF-P2-07 Add adversarial pilot-versus-director cooperation with reproducible game environment evidence.
- [ ] GF-P2-08 Scale world-axis combinations across biome, geography, ecology, gravity, weather, lore and transit topology.
- [ ] GF-P2-09 Add longform canonical world and NPC state retention; ensure non-contradictory changes in scene, quest, dialogue.
- [ ] GF-P2-10 Add multi-camera replay and generative reconstruction benchmarking for complex regions and sky-island levels.
- [ ] GF-P2-11 Use authorized game data and synthetic originals for training; run contamination, dedup and rights gates.
- [ ] GF-P2-12 Train local game-related checkpoints or approved adapters; preserve optimizer state, seed, dataset and model hashes.
- [ ] GF-P2-13 Compare neural and deterministic physics over long horizons, including weather, wind, collisions and destruction.
- [ ] GF-P2-14 Create Dragon/Jeeves/adversary learning triangle with independently measured, not self-graded improvements.
- [ ] GF-P2-15 Verify end-to-end playable game generation, objective completion, win/loss detection and failure recovery.

## P3 — Production qualification and large-scale world operation

- [ ] GF-P3-01 Run real GPU serving load tests per 30/50/120 mode, with measured generated versus displayed frame rates.
- [ ] GF-P3-02 Qualify 3D level scalability, chunk streaming, weather and cloud LOD under low/high device profiles.
- [ ] GF-P3-03 Add spatial/neural memory compaction and world-state restore beyond hour/day/week production runs.
- [ ] GF-P3-04 Profile persistent project runs lasting weeks/months, crash resume, backups, lease recovery and budget limits.
- [ ] GF-P3-05 Build source/mesh/skeleton/material/animation export paths per licensed console and engine target.
- [ ] GF-P3-06 Compare transfer performance over held-out games/eras and record independent benchmark receipts.
- [ ] GF-P3-07 Add neural/visual/style quality acceptance with provenance, similarity screening, regression and human inspection.
- [ ] GF-P3-08 Implement governable shadow→candidate→canary→production model promotion with rapid rollback.
- [ ] GF-P3-09 Release cinematic and preemptive suggestion controls in Jeeves cockpit / Galaxy Studio.
- [ ] GF-P3-10 Add artifact/documentation UI: live frames, weather windmaps, LoD budget, skeleton rig preview, evidence and model status.
- [ ] GF-P3-11 Full first-install qualification, native emulator ROM validation, Godot export and cross-device recovery.
- [ ] GF-P3-12 Finish VOL L00–L13 research/implementation/assurance dossiers and exact-head enterprise benchmarking.
- [ ] GF-P3-13 Verify production feature parity claims strictly from executed inference and generated/exported scenes.
- [ ] GF-P3-14 Merge only after review and acceptable CI; reconcile conflicts, retain rights and safety gates.

## Source references

- [Genie 3](https://deepmind.google/blog/genie-3-a-new-frontier-for-world-models/)
- [HY-World 2.0](https://github.com/Tencent-Hunyuan/HY-World-2.0)
- [SIMA 2](https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/)
- [Microsoft WHAM](https://www.microsoft.com/en-us/research/project/wham/)
- [TRELLIS.2](https://github.com/microsoft/TRELLIS.2)
- [NVIDIA Cosmos](https://developer.nvidia.com/cosmos)
