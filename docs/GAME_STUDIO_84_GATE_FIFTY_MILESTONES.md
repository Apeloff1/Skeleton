# Original-Game Production Studio — 50-Milestone Build (Gates 35–84)

## Authority and status

This batch extends the existing 34 `skeleton/game` source-bound candidate-quality
gates with **50 independently receipted domains** under the same runtime owner.
It is real executable validation code, not a list of future features. Thresholds
are explicitly defined candidate acceptance policies, **not** industry-certified
or externally validated hardware measurements.

**No runtime root, AI provider, shell, model-weight trainer, controller execution
authority or production release approval is introduced.**

## Ten milestone families / 50 explicit contracts

The following fifty gates are enforced by
`skeleton/game/production_expanded_gates.py`; each domain requires its
own `studio.expanded.<name>` source-bound contract. No omitted domain
can produce a passing report.

| # | Source-bound gate | Family | Candidate budget | Accountable owner |
|---:|---|---|---|---|
| 35 | `frame_interpolation` | timing | 2 ms | `render_timing_owner` |
| 36 | `animation_blends` | timing | 8 ms | `animation_director` |
| 37 | `lip_transitions` | timing | 12 ms | `voice_lipsync_director` |
| 38 | `subtitle_layout` | timing | 40 ms | `localization_director` |
| 39 | `quest_causality` | timing | 250 ms | `narrative_director` |
| 40 | `npc_reactions` | timing | 120 ms | `npc_behavior_director` |
| 41 | `weather_dwell` | timing | 500 ms | `dynamic_environment_director` |
| 42 | `camera_path` | timing | 16 ms | `cinematic_director` |
| 43 | `audio_beat_grid` | timing | 20 ms | `soundscape_director` |
| 44 | `controller_buffer` | timing | 24 ms | `input_latency_owner` |
| 45 | `elastic_skin` | physics | 0.06 strain_ratio | `character_physics_owner` |
| 46 | `skeletal_joint` | physics | 3 degrees | `animation_physics_owner` |
| 47 | `center_mass` | physics | 0.04 meters | `physics_solver_owner` |
| 48 | `fluid_buoyancy` | physics | 15 newtons | `fluid_physics_owner` |
| 49 | `freefall_terminal` | physics | 1.5 meters_per_second | `aerial_physics_owner` |
| 50 | `wind_drafting` | physics | 12 newtons | `aerial_physics_owner` |
| 51 | `turbulence` | physics | 1 meters_per_second_squared | `weather_physics_owner` |
| 52 | `surface_grip` | physics | 0.08 slip_ratio | `traction_physics_owner` |
| 53 | `inertial_gyro` | physics | 1.2 degrees | `navigation_instruments_owner` |
| 54 | `sextant_fix` | physics | 6 meters | `navigation_instruments_owner` |
| 55 | `plot_threads` | graph | 128 nodes | `narrative_director` |
| 56 | `character_arcs` | graph | 256 nodes | `character_director` |
| 57 | `dialogue_choices` | graph | 512 nodes | `dialogue_director` |
| 58 | `quest_dependency` | graph | 1024 nodes | `quest_director` |
| 59 | `reputational_effects` | graph | 256 nodes | `reputation_director` |
| 60 | `faction_branching` | graph | 512 nodes | `faction_director` |
| 61 | `ending_resolutions` | graph | 512 nodes | `narrative_director` |
| 62 | `lore_citations` | graph | 2048 nodes | `canon_director` |
| 63 | `world_portals` | graph | 1024 nodes | `multiworld_director` |
| 64 | `multi_world_state` | graph | 1024 nodes | `multiworld_director` |
| 65 | `sprite_atlases` | asset | 1 percentage | `sprite_asset_director` |
| 66 | `color_palette` | asset | 3 delta_e | `palette_director` |
| 67 | `material_shaders` | asset | 3 percentage | `shader_director` |
| 68 | `foliage_detail` | asset | 7 percentage | `environment_asset_director` |
| 69 | `parallax_depth` | asset | 4 percentage | `camera_art_director` |
| 70 | `lod_transition` | asset | 4 percentage | `lod_director` |
| 71 | `shadow_contact` | asset | 3 percentage | `lighting_director` |
| 72 | `volumetric_light` | asset | 5 percentage | `lighting_director` |
| 73 | `texture_streaming` | asset | 2 percentage | `texture_director` |
| 74 | `particle_fidelity` | asset | 8 percentage | `vfx_director` |
| 75 | `checkpoint_atomic` | integrity | 750 ms | `recovery_owner` |
| 76 | `save_rollback` | integrity | 1250 ms | `savegame_compatibility_owner` |
| 77 | `chunk_receipts` | integrity | 150 ms | `frame_evidence_owner` |
| 78 | `deterministic_compilation` | integrity | 2000 ms | `builder_graph_owner` |
| 79 | `controller_binding` | integrity | 350 ms | `input_devices_owner` |
| 80 | `console_portability` | integrity | 5000 ms | `cross_console_owner` |
| 81 | `multiplayer_reconcile` | integrity | 600 ms | `network_determinism_owner` |
| 82 | `crawler_knowledge` | integrity | 5000 ms | `dragon_knowledge_owner` |
| 83 | `adversarial_promotion` | integrity | 10000 ms | `verification_owner` |
| 84 | `background_workers` | integrity | 15000 ms | `longform_recovery_owner` |

## Verification semantics

- **timing:** Ordered, captured start/end/target times; three independent measurements and domain drift limit.
- **physics:** Unit-matched expected/actual/replayed physical measurements; independent replay and three observations.
- **graph:** Canonical cited nodes, complete reachability, reverse closure to terminal and no dangling references.
- **asset:** Original/rendered hashes, captured deviation against domain-specific limit, rights review and byte budget.
- **integrity:** Three sequenced state transitions with replayed state digests, receipts and bounded recovery latency.

All five families enforce exact SHA-256 source identity, declared independent
observation evidence and bounded input sizes. Replaying a declared hash is
not independently running an original engine; review receipts are claims
verified for structural consistency only.

## Operational integrations

1. `audit_expanded_studio(bundle)`: recompute original 34 plus 50 domains
   in order, return 84 gates, findings and SHA-256 evidence ledger.
2. `verify_expanded_studio(bundle, report)`: independently recompute from
   source and reject altered gate outcomes and fabricated summaries.
3. `challenge_84_verifiers(bundle)`: isolated 50-domain fault cases,
   plus forged source report and summary probes.
4. `compare_84(prior, current)`: per-gate objective improvement and
   regression; no average-score masking.
5. `queue_84(report)` and `impact_84(report)`: owner-routed repair
   queue and upstream recheck graph, never permission to edit.
6. `QualityHistoryStore`: existing SQLite WAL/CAS and hash-linked
   source-locked journal reads all 13/20/27/34/84 report schemas.
7. `expanded_studio_quality_handlers(...)`: eight host-scoped Jeeves
   operations; user/model payloads cannot inject project sources.
8. Focused specialized CI compiles and runs the new source/test surface,
   including 50 independently executable mutation regression tests.

## L00–L13 construction dossier

- **L00 Scope and ownership:** expand the existing original-game producer
  evidence plane; preserve canonical application/runtime owner mapping.
- **L01 Architecture:** additive under `skeleton/game` with Jeeves
  existing command registry and existing SQLite evidence store.
- **L02 Contracts:** `game.candidate.production_84.v1`, 84 ordered gates,
  source digest, per-gate receipts, explicit candidate-only release status.
- **L03 Admission:** exact host source loaders and declared source digests;
  tool registration never grants a permission.
- **L04 Flow:** source -> original 34 -> next 50 -> isolated independent and
  structural verification -> history/diff/triage.
- **L05 State:** append-only SQLite WAL and CAS revisions; no migration
  of authoritative application state, no overwrite of historical receipts.
- **L06 Security/privacy:** no raw identifiers/credentials in helper reports,
  no license grant, no bypass of operator review or source requirements.
- **L07 Failure and recovery:** reject foreign source, stale CAS, malformed
  payload, impossible budget values, fabricated receipts and corrupt history.
- **L08 Observability:** source digest, ordered findings, per-plane evidence,
  owner mapping, objective comparisons and adversarial proof digest.
- **L09 Capacity/economics:** input arrays and scalar ranges capped; no
  provider/tool budget spend for these deterministic audits.
- **L10 Deployment:** trusted host may attach handlers; unregistered tools
  cannot invoke new operations, legacy 34-gate callers keep their contracts.
- **L11 Evaluation:** 50 individually named rejection tests, clean baseline,
  tamper probes, 84-history CAS, Jeeves authorization and graph/state edge cases.
- **L12 Rollback:** detach advanced handlers; preserve prior 34-plane
  candidate path and prior evidence, never silently downgrade records.
- **L13 Signoff:** structural test pass is candidate evidence only;
  real Godot native/GPU, physical controls, authentic capture, provider
  training, legal originality review and full-app E2E remain independent.

## Commands

```sh
python -m compileall -q skeleton/game/production_expanded_*.py skeleton/jeeves/game_expanded_studio_quality_tools.py skeleton/testing/test_game_production_expanded_quality.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q --noconftest skeleton/testing/test_game_production_expanded_quality.py
python scripts/check_architecture_logical_layers.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
```

The 50 contracts verify evidence semantics. They **do not produce a finished
game, train Jeeves weights or independently attest simulated measurements**.
Those require the existing source-authoring engines, trusted hosts, native
execution and release/evaluation planes.
