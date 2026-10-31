# Skeleton Frontier Consolidation

**Program:** Frontier Model Build  
**Lead:** Apeloff1  
**Canonical repository:** `Apeloff1/Skeleton`  
**Branch:** `frontier/consolidation-foundation`

## Mission

Consolidate the strongest AI, learning, agent, game, world, and cockpit capabilities from the Apeloff1 repository family into one coherent platform. The objective is not to concatenate repositories; it is to produce a production-grade AI operating substrate with explicit contracts, replaceable implementations, and a polished developer/operator surface.

## Non-negotiables

1. Skeleton is the canonical root.
2. Preserve useful implementation provenance in `docs/lineage/` and consolidation manifests.
3. Never merge secrets, generated caches, dependency directories, or opaque build output into normal Git history.
4. Large model/data/game assets use Git LFS or external artifact storage.
5. Every promoted subsystem receives a contract, tests, observability, and security boundary.
6. No duplicate “core” implementations: one canonical interface, multiple adapters where justified.
7. Existing working behavior is preferred over speculative rewrites.
8. Experimental code may remain quarantined until it passes promotion gates.

## Target architecture

```text
core/kernel
    -> runtime
    -> memory
    -> intelligence
    -> swarm
    -> game
    -> learning
    -> forge
    -> services
    -> cockpit
```

### Core planes

- **Kernel:** events, errors, clocks, registries, invariants.
- **Runtime:** lifecycle, configuration, execution context, capabilities.
- **Memory:** RAG/CAG/MAG, vector retrieval, provenance, memory policies.
- **Intelligence:** agents, orchestration, planning, reasoning, evaluation, tool use.
- **Swarm:** multi-agent routing, coordination, work queues, collective state.
- **Game:** worlds, NPCs, dialogue, quests, simulation, mechanics, animation.
- **Learning:** tutoring, curriculum, ZPD, mastery, gamification, knowledge packs.
- **Forge:** blueprints, generators, materialization, project scaffolding.
- **Services:** API, persistence, auth, jobs, storage, telemetry.
- **Cockpit:** operator UI, dashboards, inspectors, visualization, command center.

## Promotion gates

A component moves from source repository to canonical implementation only after:

- source provenance recorded;
- dependencies mapped;
- public API identified;
- secrets/config audit completed;
- unit tests or characterization tests added;
- integration boundary defined;
- duplicate implementations compared;
- performance implications documented;
- security capabilities declared;
- owner/maintainer identified.

## Workstreams

### W0 — Control plane
Branching, CI, repository inventory, architecture records, dependency policy, security scanning.

### W1 — Kernel/runtime
Stabilize boot, event bus, registry, config, runtime context, capability model.

### W2 — Intelligence
Unify agent lifecycle, orchestration, tool invocation, planning, reasoning, evaluation.

### W3 — Memory
Unify retrieval, memory planes, vector adapters, provenance, ranking and fusion.

### W4 — Learning/Jeeves
Promote tutoring, system laws, learning matrices, co-coding and knowledge packs as adapters on the common intelligence/memory substrate.

### W5 — Game/world
Promote NPC, dialogue, quest, world and simulation implementations from Lorebuffa/Openworld/GameForge families.

### W6 — Forge
Unify blueprint generation and materialization; expose one project-generation contract.

### W7 — Cockpit
Integrate HyperForge's web stack as the operator/developer surface without coupling UI concerns into the kernel.

### W8 — Validation
Unit, integration, E2E, load, chaos, benchmark, security, reproducibility.

### W9 — Asset/artifact plane
Move large assets into explicit LFS/artifact boundaries and document reproducible acquisition/build procedures.

## Definition of done

The frontier build is considered consolidated when:

- one command boots the platform;
- one CLI discovers and operates all major subsystems;
- one agent contract powers Jeeves and game agents;
- one memory contract powers learning and game retrieval;
- one event/telemetry model crosses subsystem boundaries;
- cockpit can inspect runtime, agents, memory, worlds, jobs and health;
- all promoted modules have tests and documented failure modes;
- source repository remains maintainable while total platform assets can scale to the requested multi-GB footprint through proper artifact channels.

## Inventory snapshot — 2026-10-24 (#80)

Appended by QA (Carrol) for #80. Extend-only: nothing above this section was changed. Every entry below is read from files on `main` at `9c4481e4e86ba4be67c6eb25e3b9648abeccf4d8`; nothing is inferred from repository names. Status lines for workstreams quote the #80 issue body as of 2026-10-24.

### Source repository inventory (`docs/lineage/source-repository-inventory.v1.json`)

Schema `1`, captured `2026-09-15`, `repository_count` = 38 (list length 38).

| Repository | Role | Manifest status | Visibility | Size (KB) | Revision |
|---|---|---|---|---|---|
| Apeloff1/2d | source-candidate | uncharacterized | public | 146 | — |
| Apeloff1/2dv0.2 | source-candidate | uncharacterized | public | 134 | — |
| Apeloff1/2dv0.3 | source-candidate | uncharacterized | public | 195 | — |
| Apeloff1/2dv0.4 | source-candidate | uncharacterized | public | 194 | — |
| Apeloff1/2dv1 | source-candidate | uncharacterized | public | 195 | — |
| Apeloff1/Asds | source-candidate | uncharacterized | private | 26538 | — |
| Apeloff1/Expa | source-candidate | uncharacterized | public | 458 | — |
| Apeloff1/gameforge-middleware | source-candidate | curated | private | 14 | `282b0af7cf39` |
| Apeloff1/gameforge-rs | source-candidate | curated | private | 137 | `669b99d068fc` |
| Apeloff1/Ggg | source-candidate | uncharacterized | private | 26535 | `dddecadd6daf` |
| Apeloff1/hyperforge-cockpit-sota | source-candidate | curated | public | 493 | `161c12634a21` |
| Apeloff1/Interesting-22 | source-candidate | uncharacterized | private | 10407 | — |
| Apeloff1/Lore-buff | source-candidate | uncharacterized | public | 568 | — |
| Apeloff1/Lorebuf22f | source-candidate | uncharacterized | public | 764 | — |
| Apeloff1/Lorebuff | source-candidate | uncharacterized | public | 679 | — |
| Apeloff1/Lorebuffa | source-candidate | curated | public | 826 | `279539fc299f` |
| Apeloff1/New-tey | source-candidate | uncharacterized | private | 26528 | `84eef331b3d9` |
| Apeloff1/Newfix | source-candidate | uncharacterized | public | 1014 | — |
| Apeloff1/Newmove | source-candidate | uncharacterized | public | 874 | — |
| Apeloff1/Newmove2 | source-candidate | uncharacterized | public | 933 | — |
| Apeloff1/Newsay | source-candidate | uncharacterized | public | 26538 | — |
| Apeloff1/Newsay2 | source-candidate | uncharacterized | public | 26606 | — |
| Apeloff1/Newsay3 | source-candidate | uncharacterized | private | 166 | — |
| Apeloff1/Newsay4 | source-candidate | uncharacterized | public | 167 | — |
| Apeloff1/Newstuff | source-candidate | uncharacterized | public | 305 | — |
| Apeloff1/Newstuff2 | source-candidate | uncharacterized | public | 399 | — |
| Apeloff1/Openw3orld4 | source-candidate | uncharacterized | private | 1140 | — |
| Apeloff1/Openworld | source-candidate | curated | public | 1072 | `8324f0f88969` |
| Apeloff1/Openworld2 | source-candidate | uncharacterized | public | 1080 | — |
| Apeloff1/Openworld3 | source-candidate | uncharacterized | public | 1137 | — |
| Apeloff1/Openworld4 | source-candidate | uncharacterized | public | 1139 | — |
| Apeloff1/Prood | source-candidate | curated | private | 59739 | `aa33a5c9cfaf` |
| Apeloff1/Saymore5 | source-candidate | uncharacterized | public | 253 | — |
| Apeloff1/Saymore6 | source-candidate | uncharacterized | private | 217 | — |
| Apeloff1/Saymore7 | source-candidate | uncharacterized | private | 217 | — |
| Apeloff1/Saymore8 | source-candidate | uncharacterized | public | 220 | — |
| Apeloff1/Skeleton | canonical-receiver | canonical | public | 113054 | `4ea9a063e959` |
| Apeloff1/Tutolage | source-candidate | curated | public | 45854 | `d94030b6d4c7` |

Manifest status totals: canonical: 1, curated: 7, uncharacterized: 30.

### Consolidation manifest (`docs/lineage/consolidation-manifest.v1.json`)

Schema `1`, inventory date `2026-09-15`, 7 sources, 7 components.

| Source | Disposition | Capabilities |
|---|---|---|
| Apeloff1/Prood | promote-unique-only | jeeves, rag, learning, text-to-npc, game-pipelines |
| Apeloff1/Tutolage | promote-unique-only | tutoring, rag, gamification, npc-pipeline, game-logic-pipeline, animation-pipeline |
| Apeloff1/gameforge-rs | promote-unique-only | gameforge, simulation, generation, digest, idempotency, outbox |
| Apeloff1/gameforge-middleware | promote | middleware, orchestration |
| Apeloff1/hyperforge-cockpit-sota | boundary-consumer | cockpit, visualization, telemetry, validated-bridge |
| Apeloff1/Lorebuffa | adapt-unique-only | lore, world-building, narrative, npc-catalog, world-map, quests, reputation |
| Apeloff1/Openworld | characterize-and-deduplicate | world, exploration, procedural-content, npc-catalog, world-map, quests, reputation |

| Component | Source path | Destination | Maturity | Tests | Present on main |
|---|---|---|---|---|---|
| prood-rag-memory | Apeloff1/Prood:`backend/services/rag_service.py` | `skeleton/frontier/memory_adapters.py` | promoted | passing | yes |
| prood-npc-generation | Apeloff1/Prood:`backend/routes/npc_pipeline.py` | `skeleton/frontier/npc_profiles.py` | characterized | characterized | yes |
| gameforge-runtime-semantics | Apeloff1/gameforge-rs:`crates/gf-core/src/lib.rs` | `skeleton/frontier` | characterized | characterized | yes |
| hyperforge-capability-boundary | Apeloff1/hyperforge-cockpit-sota:`src/lib/preview-host-bridge.ts` | `skeleton/frontier/agent_runtime.py` | characterized | characterized | yes |
| lorebuffa-openworld-world-policy | Apeloff1/Lorebuffa:`backend/world_map.py` | `skeleton/frontier/world.py` | characterized | characterized | yes |
| gameforge-middleware-service | Apeloff1/gameforge-middleware (no source path recorded) | `services/gameforge` | candidate | not-run | NO |
| tutolage-learning-unique | Apeloff1/Tutolage (no source path recorded) | `skeleton/learning` | candidate | not-run | yes |

### Lineage records (`docs/lineage/`)

76 files: `AQUARIUM_PROMOTION_2026-09-15.md`, `ASSET_POLICY.md`, `BAIT_PROMOTION_2026-09-15.md`, `BIOTOPE_ACHIEVEMENT_PROMOTION_2026-09-15.md`, `BIOTOPE_PROMOTION_2026-09-15.md`, `BREEDING_PROMOTION_2026-09-15.md`, `COMMERCE_VIP_TOURNAMENT_PROMOTION_2026-09-15.md`, `COOKING_PROMOTION_2026-09-15.md`, `CRAFTING_PROMOTION_2026-09-15.md`, `ENERGY_PROMOTION_2026-09-15.md`, `EQUIPMENT_PROMOTION_2026-09-15.md`, `FRONTIER_INTEGRATION_WAVE_2.md`, `FRONTIER_WAVES_9_11_2026-09-15.md`, `GAMEFORGE_RS_INVENTORY_2026-09-13.md`, `GUILD_PROMOTION_2026-09-15.md`, `LUCKY_WHEEL_PROMOTION_2026-09-15.md`, `MEMORY_CONFORMANCE_2026-09-15.md`, `PROOD_INVENTORY_2026-09-13.md`, `PROOD_TUTOLAGE_PROMOTION.md`, `README.md`, `SEASON_PASS_PROMOTION_2026-09-15.md`, `TUTOLAGE_INVENTORY_2026-09-13.md`, `admit.md`, `artifact_plane.md`, `audio_eras_batch5120.md`, `audio_vol156_batch1280.md`, `capabilities.md`, `check.md`, `chronicle.md`, `circulation.md`, `consolidation-manifest.v1.json`, `cue.md`, `cue_gb46_batch2560.md`, `decode.md`, `delta.md`, `document_vision_vol155_batch640.md`, `economy.md`, `era.md`, `facet_batch10240.md`, `fold.md`, `genos.md`, `godot_pointer.md`, `graphs.md`, `hive.md`, `hoag.md`, `mesh.md`, `motive.md`, `pair.md`, `parse.md`, `persist.md`, `place.md`, `plane_audit.md`, `prefill.md`, `primitives.md`, `promotion-manifest-v11-supplement.yaml`, `promotion-manifest-v12-supplement.yaml`, `promotion-manifest-v13-supplement.yaml`, `promotion-manifest-v14-supplement.yaml`, `promotion-manifest-v15-supplement.yaml`, `promotion-manifest.yaml`, `quota.md`, `reclaim.md`, `scatter_batch10240.md`, `serving_token_synergy.md`, `seven_by.md`, `sheaf.md`, `source-repository-inventory.v1.json`, `spine.md`, `stock.md`, `supply_chain_vol178_batch160.md`, `swarm.md`, `telemetry.md`, `turn.md`, `video_vol158_batch320.md`, `viscera.md`, `walk.md`.

### Frontier contract package (`skeleton/frontier/`)

115 tracked files. By subpackage: (top-level): 55, characters: 4, ecology: 9, economy: 9, game: 4, progression: 13, runtime: 21.

### Workstream status (from the #80 issue body)

| Workstream | Tracking | Status |
|---|---|---|
| Inventory/provenance | #115 | closed |
| Kernel/runtime | #116 | complete |
| AI agent/orchestration | #117 | complete |
| Memory/RAG | #118 | closed |
| Jeeves/learning | #952 | closed |
| Game/world | #945 | closed |
| GameForge | #763 / #768 | merged / closed |
| HyperForge cockpit | #362 (+ #11, #50, #356, #1655, #1839) | checked |
| Unified API/CLI | #953 | closed |
| Security/secret audit | #540 | **open** |
| Integration/E2E | #122 | closed |
| Reliability/load/chaos | #123 | closed |
| LFS/artifact plane | #954 | closed |
| Release/docs polish | #954 | closed |
| Merge-readiness policy | #127 (+ #784) | **open**: needs repository-admin required-check enforcement |

Open tail for #80: #540 and #127/#784. The 2026-09-28 note in #80 also lists HyperForge cockpit and release/docs polish as tail items, but the same body marks both checked. This snapshot follows the checkboxes and flags the mismatch for the issue owner.

Inventory finding: component `gameforge-middleware-service` (maturity `candidate`, tests `not-run`) names destination `services/gameforge`, and that path does not exist on `main`. It is recorded here as an open gap and has not been fixed in this docs-only change.
