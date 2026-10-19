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
- [x] GF-P0-03 LingBot-inspired exact presentation clocks at **30, 50, 60, 120 FPS** with bounded catchup and physics-clock isolation.
- [x] GF-P0-04 World-axis generation for terrain, temperature, humidity, verticality, sky islands, volatility, biomes.
- [x] GF-P0-05 HY-World-inspired skeletal-bone-to-polygon meshes; reduce polygon counts by engine era and available triangle budget.
- [x] GF-P0-06 TRELLIS-inspired simulation-ready mesh data with bone influences, collision capsules, animation sample transforms.
- [x] GF-P0-07 SIMA-inspired evidence-linked cinematic shots plus inspect/approach/interact proposals (never autonomous mutation).
- [x] GF-P0-08 Muse-inspired bounded speculative user-motion prediction with no input firing.
- [x] GF-P0-09 Candidate-only shared composition façade with content-addressed receipts.
- [x] GF-P0-10 Add primitive and integration regressions; targeted CI execution has passed.
- [x] GF-P0-19 Add candidate-only model checkpoint, frame throughput and simulation-ready 3D evidence contracts.
- [x] GF-P0-20 Add independent license allowlist, external receipt identity, measured-versus-requested FPS checks.
- [x] GF-P0-21 Add opt-in 30/50/60/120 FPS bridge to canonical per-era simulation timing, with cross-mode tests.
- [x] GF-P0-22 Add **60 FPS**, preserving 30/50/60/120 and canonical physics tick rates.
- [x] GF-P0-23 Eight distinct world-variant generation transforms: inverse, mirror, elemental, ethereal, mythic, lensed, shadow, celestial.
- [x] GF-P0-24 Top-down, platformer, full 3D and depth-weighted 2.5D/2.6D/2.7D/2.8D/2.9D projection candidates.
- [x] GF-P0-25 Skin elasticity, cloth and hair soft-node spring motion; wetness/mass/wind damping and anchor displacement reference solver.
- [x] GF-P0-26 Weather-aware player motion, traction, wind load, body temperature, rain and snow interaction.
- [x] GF-P0-27 Adaptive character-plane collision, material restitution, recorded impact impulse and damage candidates.
- [x] GF-P0-28 Environment soil saturation/erosion/foliage/snow/debris adaptation with simulated impacts.
- [x] GF-P0-29 Construction progress, house integrity, long-term climate damage, natural growth and explicit maintenance.
- [x] GF-P0-30 Liquid-aware hair, clothing, boots; protection/thermal and slip-risk character cognition.
- [x] GF-P0-31 CPU shadow ray intersections for character and environment occluders plus area-light, wet-surface specular.
- [x] GF-P0-32 Scene-candidate composition exports projection, variants, impacts, wear, awareness and ray-lighting evidence.
- [x] GF-P0-33 Path-scoped frontier CI verified: 57 tests passed on source commit `586028081cd740fb153378422eb04f78c944cbf8` (GitHub Actions run `39186433511`).
- [ ] GF-P0-34 Wire reference soft-body, weather, lifecycle and character collision outputs into authoritative Godot/era runtime.
- [ ] GF-P0-35 Convert projected polygons and character-aware ray shadows into visible graphics with native renderer reference screenshots.
- [ ] GF-P0-36 Persist world variants, structures, weather fields and motion state with history/canon/backups.
- [x] GF-P0-37 Extend existing Forge Godot overlay with Y-up/Z-forward conversion, shadow-casting clouds, 60fps, variant luminance and top-down/platformer/pseudo-depth cameras.
- [ ] GF-P0-38 Run real Godot headless parse, emitted scene import and screenshot smoke; inspect shadow caster geometry, camera and collision fidelity.
- [x] GF-P0-39 Add conflict-safe Godot project overlay attachment preserving existing main level and imports.
- [x] GF-P0-40 Export Godot overlay scene with posed polygons, generated bone capsules, sky islands and source-wind cloud animation paths.
- [x] GF-P0-41 Add exporter custody/regression tests and apply 30/50/60/120 requested FPS cap to preview script.
- [x] GF-P0-42 Sample altitude/heat/moist air density and visibility with ISA troposphere reference at 830 metres / 2723 feet.
- [x] GF-P0-43 Separate physical fog extinction from air density, rain freshness proxy and optional cold-wind response.
- [x] GF-P0-44 Add solar/lunar harmonic tide phase, height, current and rise-rate calculations.
- [x] GF-P0-45 Add bounded conservative liquid grid flux with volume receipts and immersion/buoyancy/drag character calculations.
- [x] GF-P0-46 Add atmosphere/rain/fog/occlusion/tide aware environmental audio delay/gain/filter/ambience candidates.
- [x] GF-P0-47 Implement motion-coherent animated leaf geometry with independently ray-verified receiver-plane shadow area.
- [x] GF-P0-48 Add 3D source distance inverse-square lighting with per-occluder transmittance, fog/rain/cloud optical dampening and wet-material highlight.
- [x] GF-P0-49 Add wind- and character-impact responsive shrub/pebble reference physics integrated into same-frame 3D occlusion.
- [x] GF-P0-50 Build real 3D indexed meshes from original 2D source sprites with old-era and modern outputs retaining the same asset digest.
- [x] GF-P0-51 Build chunked triangle mesh partitioning and dual SHA-256 identity/topology reconstruction verification for every registered engine era.
- [x] GF-P0-52 Add declarative multi-era RPG game editor backend for tile maps, prefabs, event pages, quests, cinematics, RPG systems and world/weather/physics parameters.
- [x] GF-P0-53 Integrate reference atmosphere, tide, fluid, foliage, 3D lighting, mesh evolution and per-era chunk verification in one game scene candidate.
- [x] GF-P0-54 Extend Godot Forge overlay with fog, scene light dampening, shadow polygons, water surface and shrub/rock geometry.
- [x] GF-P0-55 Cross-system regression verified: 74 tests passed on source commit `e5cd4fe9c4026b6e090b349ffea600bd1b560dda` (run `39188618020`).
- [ ] GF-P0-56 Integrate double-verifier chunking in every *actual* registered native engine runtime and guarantee seamless spatial streaming.
- [ ] GF-P0-57 Run live Godot weather/water/leaf-shadow/rock/character physics simulation with per-frame coherence and screenshot proof.
- [ ] GF-P0-58 Surface all new RPG-style editors in Galaxy Studio/Jeeves cockpit and connect event actions through authorized game runtime.
- [ ] GF-P0-59 Bind conservative water solver to native moving-boundary shorelines, 3D collision and persistent coastal terrain.
- [ ] GF-P0-60 Bind atmospheric audio cues and proper audio assets to playable mixer buses, occlusion and audio engine.
- [ ] GF-P0-61 Profile production GPU 3D ray/path lighting and physically measured leaf-shadow alignment on low/high hardware.
- [x] GF-P0-62 Implement SI-unit reference terminal velocity using atmosphere density, gravity, body mass, area and drag coefficient.
- [x] GF-P0-63 Add 3D lee-side aerodynamic drafting with downwind wake distance, width and shielding factors.
- [x] GF-P0-64 Add hot thermals, sinking air, vertical wind and turbulence with deterministic time/seed/position coherence.
- [x] GF-P0-65 Add bounded substep aerodynamic integration with gravity, lift, drag, mechanical energy and drag dissipation.
- [x] GF-P0-66 Implement wet/icy/loose gravel traction, weighted cargo, slope force balance, climbing skill and foothold/rope checks.
- [x] GF-P0-67 Add mass/inertia-aware rigid-body impulse resolution with tangential Coulomb friction, angular motion, material restitution and energy/momentum receipts.
- [x] GF-P0-68 Add continuous collision detection for high-speed sphere–sphere and sphere–terrain/plane sweeps.
- [x] GF-P0-69 Evolve microclimate rain, freeze/thaw, solar drying, erosion, sediment, pressure shear and convective uplift into actual climbing surface/airflow inputs.
- [x] GF-P0-70 Add 14-domain realism/coherence auditor with measurable invariants and content-addressed evidence; never award self-certified physics quality scores.
- [x] GF-P0-71 Wire opt-in advanced aerodynamic, traction, impact and weather candidates into the existing source-hashed Jeeves scene.
- [x] GF-P0-72 Export Godot native RigidBody3D candidate with mass/collider/restitution, live per-fixed-tick wind-relative drag and wet/ice-adjusted contact material.
- [x] GF-P0-73 Add focused regression source and CI tests for terminal speed, lee-wake, thermals, climbing, collision momentum/energy, CCD, air/terrain integration and scene compatibility.
- [ ] GF-P0-74 Verify native Godot RigidBody3D/headless import, GPU/physics timestep equivalence and actual slope/impact behavior.
- [ ] GF-P0-75 Bind continuous collision prediction and multi-body contact solver to game-authoritative engine physics and actor controllers.
- [ ] GF-P0-76 Add real per-era physics solver adaptation and source-verified fixed-step streams with dual chunk checks under loaded scenes.
- [ ] GF-P0-77 Benchmark field-scale weather turbulence and long-horizon physical energy/momentum against independent reference solvers.

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
- [ ] GF-P1-05 Implement variable-latency neural sampling with 30/50/60/120 FPS fallback, frame interpolation/drop policy and metrics.
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
- [ ] GF-P1-16 Rigged skin deformation with vertex weights, collision-aware cloth self-contact and root-motion coupling to production physics.
- [ ] GF-P1-17 Calibrated rain/snow/fluid solver for cloth/hair/boots and continuous environmental heat transfer.
- [ ] GF-P1-18 GPU renderer integration of character/environment occlusion, BVH spatial acceleration, traced reflections and soft shadows.
- [ ] GF-P1-19 Full world-family graph and cross-world transitions preserving identity, canon, biome climate and physical rules.
- [ ] GF-P1-20 Parallax layer/material synthesis and camera editor controls per 2.5–2.9D projection level.
- [ ] GF-P1-21 Native gameplay rig, clothing, impact and structure wear benchmarks per historical console era.
- [ ] GF-P1-22 Automatic source-to-target mesh/texture/normal/upscale/retarget LOD across old console/modern engines with semantic safeguards.
- [ ] GF-P1-23 True water surface hydrodynamics and submerged character locomotion with mass/energy budgets.
- [ ] GF-P1-24 Motion-driven leaf shadow penumbra vs GPU ray-tracer cross-verification and temporal coherence across sunlight.
- [ ] GF-P1-25 Implement 3D source/medium photometry (atmospheric scattering, high-order bounces, shadow transmittance) in GPU shader pipeline.
- [ ] GF-P1-26 Build desktop/mobile interactive RPG authoring UI for events, quests, scenes, characters, chunk editors and 3D prefabs.
- [ ] GF-P1-27 Implement atmospheric boundary-layer turbulence, wind shear, terrain-induced drafting and vortex shedding calibrated against physical reference cases.
- [ ] GF-P1-28 Integrate GPU/native climbing IK, limb contact, grip mechanics, ropes, sliding and rockfall support across 2D–3D engines.
- [ ] GF-P1-29 Dynamic rigid-body CCD/broadphase/BVH/manifold generation and reliable restitution/friction on deformable and moving terrain.
- [ ] GF-P1-30 Couple wind, thermal plumes, dynamic foliage, fabric, debris, fluid droplets and character motion through one authoritative timestep.
- [ ] GF-P1-31 Map weather state to collision/surface friction, surface temperature and physical damage without mutating canonical worlds out of turn.

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
- [ ] GF-P2-16 Cognitive character planning for heat/cold, storms, shelter, liquid interactions, slippery surfaces and impact responses.
- [ ] GF-P2-17 Multi-character skin/hair/garment interaction and wet/dry season, wind/water, high-speed simulation sweeps.
- [ ] GF-P2-18 Construction crews, resource supply, scheduled maintenance and accelerated weather-aging simulations across years.
- [ ] GF-P2-19 Elemental/ethereal/celestial/mythic inverse/mirror realm puzzle/physics/lighting scenario validation.
- [ ] GF-P2-20 Full ray-traced cinematics (moving lights, dynamic geometry, shadow continuity and multi-view evidence).
- [ ] GF-P2-21 Emergent multi-era RPG production templates with dialogue/quest continuity and playable game build export.
- [ ] GF-P2-22 Cross-chunk foliage/river/shore physics reconciliation and dual verifier checks under dynamic world changes.
- [ ] GF-P2-23 Calibrate barometry, aerosol visibility, thermal/cold/wet motion and seasonal astronomical physics against test measurements.
- [ ] GF-P2-24 Build live character/foliage/rocks/liquid interactions with audio events, impact damage, shadow and weather responses.
- [ ] GF-P2-25 Add mass-energy calibration and conservation or loss receipts for character, projectile, vehicle, building and mixed-material contacts.
- [ ] GF-P2-26 Character cognition for drafting, updraft soaring, terminal descent, foothold search, avalanche/fall-risk avoidance and climate-responsive traversal.
- [ ] GF-P2-27 Closed-loop learned game-agent simulation around weather, fast collision, climbing, carrying loads, stamina and terrain aging.
- [ ] GF-P2-28 Weather realism parameter fitting across hot/cold, extreme elevation and changing land cover with held-out validation.

## P3 — Production qualification and large-scale world operation

- [ ] GF-P3-01 Run real GPU serving load tests per 30/50/60/120 mode, with measured generated versus displayed frame rates.
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
- [ ] GF-P3-15 GPU/CPU parity and frame-time telemetry for 30/50/60/120 FPS including pseudo-depth view modes.
- [ ] GF-P3-16 Multi-year world and building restoration, freeze-thaw/flood/fire long-tail damage and maintenance economic qualification.
- [ ] GF-P3-17 Per-era visual QA of dynamic hair/cloth and character-aware ray tracing under mobile/PC/console performance envelopes.
- [ ] GF-P3-18 Gameplay across all nine world families (including original) and eight projection modes; continuity/transition acceptance.
- [ ] GF-P3-19 Frame and sensor evidence separate computed reference motion from authoritative GPU/physics outcomes.
- [ ] GF-P3-20 Qualify 830m reference air vs sea level, polar/hot/fog/rain weather extremes, and lunar/solar tides at realistic and fictional locations.
- [ ] GF-P3-21 Verify all-engine chunk streaming under multithreaded edits, world reloads, LOD swaps, actor movement and save/restore.
- [ ] GF-P3-22 Full Godot export/import screenshots and real 2D-to-3D modernization project first-install acceptance.
- [ ] GF-P3-23 Cinematic/audio/lighting/world consistency benchmarks at actual GPU-produced 30/50/60/120fps.
- [ ] GF-P3-24 Cross-engine real-time aerodynamics, drag, wakes, winds, fast CCD, multi-contact, climbing and impact throughput under 30/50/60/120 FPS presentation modes.
- [ ] GF-P3-25 Native physics frame-by-frame replay energy/momentum conservation, rollback and weeks-long weather-aware traversal tests.
- [ ] GF-P3-26 Independent external physics benchmark acceptance across rigid/soft/liquid/terrain engines and hardware generations.

## Source references

- [Genie 3](https://deepmind.google/blog/genie-3-a-new-frontier-for-world-models/)
- [HY-World 2.0](https://github.com/Tencent-Hunyuan/HY-World-2.0)
- [SIMA 2](https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/)
- [Microsoft WHAM](https://www.microsoft.com/en-us/research/project/wham/)
- [TRELLIS.2](https://github.com/microsoft/TRELLIS.2)
- [NVIDIA Cosmos](https://developer.nvidia.com/cosmos)
