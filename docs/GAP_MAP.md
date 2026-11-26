# Skeleton gap map — 2026-11-14

Baseline: `main` @ `c7e29744e` (2026-11-14 15:55 Oslo, #5348). Read-only audit, no test suites run.
Excluded (owned by another lane): #121 telemetry (`skeleton/telemetry/`), #807 B022 (ECS) and B027.

Companion data:
- [`gap_map/branch_inventory_20261114.tsv`](gap_map/branch_inventory_20261114.tsv): all 1,491 unmerged remote branches, with last commit, author, ahead/behind, `git cherry` counts, pending files and disposition.
- [`gap_map/untested_modules_20261114.txt`](gap_map/untested_modules_20261114.txt): production modules whose module name appears in no test file.

## How it was measured

- **Branches:** `git branch -r --no-merged main` gives 1,491 branches (main squash-merges, so nearly every branch shows as unmerged). For each branch:
  1. **Tree check:** compare every path the branch changed since its merge-base with the same path on main.
  2. **Patch check:** run `git cherry main <branch>` when the branch is ≤300 commits ahead.
  3. **Three-way pending check:** a path counts as *pending* only when the branch changed it **and main still has the merge-base version**. That means the content is really missing, not superseded.
- **Dispositions:**
  - `landed`: tree-identical, or every patch-id is already on main.
  - `obsolete`: main has moved past every touched path, or the branch only deletes files, or it is mass-generated (>300 files).
  - `integrate`: has pending additions or modifications.
- **Stubs:** `git grep` for `NotImplementedError`, `TODO|FIXME`, "not implemented", stub/placeholder markers in `skeleton backend frontend apps core`. Tests and vendored `skeleton/ai/research/external/**` are excluded.
- **Callers:** a static import graph over 341k import lines, plus dynamic `include_router` / `import_module` / dotted-string references.

## Branch and archive inventory — counts

| Disposition | Branches |
|---|---|
| landed | 332 |
| obsolete | 738 |
| integrate | 421 |
| **total unmerged** | **1,491** |

By prefix (landed / obsolete / integrate): archive 31/31/9, recovery 8/86/32, reconcile 20/63/22, fix 90/302/103, feat 128/141/188.
Only 7 PRs are open (#5351, #5350, #5349, #5315, #5300, #5285, #5283). Every other branch is left over from a closed PR.

Mass-generated branches are marked obsolete. Each one adds 600k+ files, which won't fit through the contents API and would exhaust the box's inodes:
- `draft/launch-ops-70k-a`
- `draft/launch-scale-1/2/3`
- `draft/launch-ops-1`
- `draft/ecosystem-full`
- `archive/frontier-milestone-14-pre-reconcile-20261023` (80k files)

### In-repo archives and recovered code

| Item | Size | Disposition | Target |
|---|---|---|---|
| `satellites/branch-snapshots/codex-frontier-runtime-integration/` | 4,086 files; 226 `.py` with no basename on main (≈200 `skeleton/frontier/gameforge_*` runtime modules: admission, budget, circuit, deadletter, event_bus, checkpoint…; `skeleton/api/frontier_routes.py`; `scripts/test_frontier.py`) | **integrate** | `skeleton/frontier/` + mount in `skeleton/api` |
| `satellites/branch-snapshots/codex-jeeves-epistemic-engine-next/` | 11 `tests/test_school_*.py` (epistemics, counterfactual, decision ledger/policy, replay, session runtime) absent on main | **integrate** | `tests/` against `skeleton/school` / `skeleton/learning/school` |
| `…/codex-jeeves-control-plane-v2/`, all three snapshots | `backend/routes/academy.py`, `backend/routes/quality_polish_api.py` absent on main | **integrate** (verify against `backend/core/academy_product.py`) | `backend/routes/` |
| Snapshot screenshots, `backend/artifacts_media`, `.emergent/`, `.claude/settings.local.json`, `.gitconfig` | ~45 files | obsolete (generated/local config) | — |
| `skeleton/ai/**` compat mirror | 12,470 byte-identical copies of legacy-root modules; external importers: `skeleton.ai.agents.jeeves` 9, `skeleton.ai.runtime.kernel` 1, `skeleton.ai.forge` 14 | **integrate** (convert to delegating shims) | `skeleton/ai/*` → canonical owners |
| `tests/legacy_root/` | 48 HTTP harnesses, not in CI | integrate selectively (port live assertions to `backend/tests/`), else obsolete | `backend/tests/` |
| `scripts/legacy_root/` | 3 sweep scripts | obsolete | — |
| `docs/archive/` (SEVEN_BY, planning) | 13 | landed (historical) | — |
| `.github/workflows-archive/` | 413 workflows | obsolete (keep as record; not wired) | — |
| `satellites/gameforge-middleware`, `gameforge-rs`, `hyperforge-cockpit-sota` | 17/29/14 | landed (satellite pointers) | — |

## Gap map — ranked by leverage

| # | Gap | Evidence / path | Fill |
|---|---|---|---|
| 1 | **Frontend product boot calls routes that don't exist** | `frontend/src/product/appBootstrapClient.ts` → `/api/app/bootstrap`, `/api/app/status`; `frontend/src/product/productCatalog.ts` → `/api/gameforge-studio`. No matching route or prefix in `backend/` or `skeleton/api/`. | Add `/api/app/{bootstrap,status}` + `/api/gameforge-studio` adapters, with contract tests |
| 2 | **Agents plane bypasses kernel contracts (API→agents→kernel spine broken)** | `skeleton/agents/*` (69 modules): 0 imports of `skeleton.kernel`; 71 imports of `skeleton.automation` only. `skeleton/api` → agents: 14 swarm route modules. | Route agent IDs/errors/capabilities/dedup through `skeleton/kernel`; e2e test API→swarm→kernel |
| 3 | **AI-tree mirror is a second implementation, not shims** | `skeleton/ai/agents/jeeves` ↔ `skeleton/jeeves` (9,041 identical files), `skeleton/ai/forge`↔`skeleton/forge` (679), `skeleton/ai/runtime/*`↔`skeleton/{kernel,persistence,api,…}`. This violates `docs/CANONICAL_MODULE_BOUNDARIES.md` ("shims must delegate"). | Generate delegating `__getattr__` shims; keep `scripts/reconcile_ai_tree_source_pins.py` parity |
| 4 | **Masterplan P0 G001 tokenizer/representation contract open** | `docs/architecture/masterplan-gap-audit.md` (verified delta 2026-10-08): training tokenizer separate from the native model-runtime tokenizer | Single tokenizer artifact bound in the model manifest (G003) |
| 5 | **Unwired generated capability packets** | 20,480 `*/caps/cNNNN.py` files, 20,416 with no importer (`skeleton/audio/eras/caps` 5,104; `skeleton/cue/gb46/caps` 2,559; ~638 per plane in ~30 planes, e.g. `skeleton/sheaf/facet10240/caps/`). Each returns a templated `contract()` hash. Also pushes the box to 96% inodes. | Collapse into one data-driven registry + loader (F-11) |
| 6 | **Recovered frontier GameForge runtime not on main** | `satellites/branch-snapshots/codex-frontier-runtime-integration/skeleton/frontier/gameforge_*.py`, `skeleton/api/frontier_routes.py` | Port into `skeleton/frontier/` with tests |
| 7 | **Kernel modules untested** | 26/123 in `skeleton/kernel`, incl. `ids`, `config_snapshots`, `merkle_log`, `crdt`, the `assurance_*` chain (gate, ledger, pipeline, recovery_controller, transition_validator) | Unit tests per module |
| 8 | **Memory/RAG core untested** | `skeleton/memory/{rag,cag,mag,dp}.py`; boundaries doc makes memory the canonical retrieval owner | Contract tests + wire to `skeleton/jeeves/rag.py` |
| 9 | **Security surface untested** | `skeleton/api/oauth.py`, `cache_control.py`, `deprecations.py` | Auth/cache header tests |
| 10 | **Game Frontier runtime wiring open** | `TODO.md`: 205 open (GF-P0 38, P1 65, P2 51, P3 51), e.g. GF-P0-34/35/38/57 (Godot headless import, screenshot proof, physics binding), GF-P0-58 (editors in Galaxy Studio) | Godot headless smoke + runtime binding |
| 11 | **Native target / ROM adapters not implemented** | `skeleton/ai/webcrawler/dragon_native_compile.py:89`, `dragon_native_projects.py:526`, `dragon_native_production.py:352-752`; `skeleton/ai/runtime/homebrew_porting.py:164`; `skeleton/jeeves/game_engine_legacy.py:162-185`; `skeleton/jeeves/game_learning_ingestion.py:673-862` (mapper/checksum/CIC); `skeleton/jeeves/game_rom_runtime.py:194` (DMA bus blocking) | Implement per-target adapters behind fail-closed gates |
| 12 | **Backend route coverage** | 124/322 `backend/routes` and 42/273 `backend/core` modules are named in no test; orphan route module `backend/routes/game_kb_extended.py` | Route smoke tests; mount or delete orphan |
| 13 | **Tier-2 language docks "COMING_SOON"** | `backend/server.py:474` (Rust, Go, … `executable: False`) | Sandboxed exec adapters via `core.exec_guard` |
| 14 | **Deferred specialised forges** | `backend/core/forge_registry.py` `_DEFERRED_RAW` (~120 forges) | Data-driven forge templates on Item Foundry |
| 15 | **Masterplan P0 G002–G020 (audit doc)** | `docs/architecture/masterplan-gap-audit.md` §1: dataset lineage, model artifact manifest, schema migration, sandbox, supply-chain root, leases/fencing, secret taint, DR, safe-mode. Not re-verified individually here. | Per-gap contracts + tests |
| 16 | Recovered-but-unwired Jeeves studio/ecosystem modules | `skeleton/jeeves/studio/` 514 orphan modules; `skeleton/jeeves/ecosystem/*` ~3,000 generated content modules with no importer | Registry loader or prune |
| 17 | 421 branches with pending content | see TSV; biggest: `feat/studio-b-source-bound-turn-combat-20261031-r11` (265 mod), `fix/walt-realtime-hardening-20261024` (196 mod), `feat/studio-b-cinder-ridge-rescue-20261103-r11` (178 add) | `rebase/<branch>` draft PRs |
| 18 | Frontier/forge untested | `skeleton/frontier/{gates_100x,gates_100x_v2,npc,vip}`, `skeleton/forge/game_frontier_studio_{map_edit,native_runtime,object_edit}`, `skeleton/forge/sim`, `skeleton/pipelines/npc` | Tests |
| 19 | F-11 Track E structural cleanup open | `BACKLOG.md` Tier 3: root sprawl, godot binary to LFS, shim deletion | Local git ops |
| 20 | `tests/legacy_root/` outside CI | 48 harnesses hitting historical preview URLs | Port or retire |

Abstract-base `NotImplementedError`s are by design and are **not** counted as gaps: `skeleton/jeeves/compiler/pipeline.py:115`, `agent/hierarchical_planning.py:257`, `game_engine_3d.py:568`, `game_engine_legacy.py:438-447`, `tools/integrations/adapters/provider.py:149-163`. Literal TODO/FIXME markers in production code are effectively zero; all the hits are detectors or fixtures.
