# Batches B001–B040 (of 100 in #807)

Source: `skeleton/repo_intelligence/game_creation_batches.json` (`repo-intel/batches.json` is not on main). No doc names exactly "40 large batches"; plan.md says the earlier 40-batch scan was not found on the box. This lists B001–B040 (build/creator/gameplay/AI lanes) as a starting point; Dispatch Manager rebuilds the real 40 in `artifacts/dispatch-manager/batches-40.md`. Status from #807 body + remote branches 2026-10-24. Not started = no evidence found.

| ID | Lane | Wave | Title | Deps | Status | Lane owner |
|---|---|---|---|---|---|---|
| B001 | build | 1 | Repository intelligence spine | — | merged (#2185) | Grenn |
| B002 | build | 1 | Content-addressed build graph | — | on main (skeleton/build/incremental_graph.py); gap analysis only | Grenn |
| B003 | build | 1 | Local/CI cache unification | — | merged (#2187) | Grenn |
| B004 | build | 1 | Toolchain lock and bootstrap | — | held branch feat/807-toolchain-bootstrap not on remote | Grenn |
| B005 | build | 2 | Parallel test/build scheduler | B002 | held feat/807-parallel-scheduler-stack not on remote | Grenn |
| B006 | build | 2 | Large artifact extraction | B001 | partial: #2190 merged; extraction stack not on remote | Grenn |
| B007 | build | 2 | Incremental asset pipeline | B002 | held feat/807-incremental-asset* not on remote | Grenn |
| B008 | build | 2 | Remote build farm contract | B002,B004 | not started (no evidence) | Grenn |
| B009 | build | 3 | Build observability and critical path | B005 | held feat/807-build-observability-stack not on remote | Grenn |
| B010 | build | 3 | Reproducible release graph | B004,B008 | not started (no evidence) | Grenn |
| B011 | creator | 1 | Intent-to-project compiler | — | compiler on main; gate-wiring branch not on remote | Frontend |
| B012 | creator | 1 | Persistent design graph | — | held feat/807-persistent-design-graph not on remote | Frontend |
| B013 | creator | 1 | Agent work claiming and leases | B001 | not started (no evidence) | Frontend |
| B014 | creator | 1 | Creator command surface | — | not started (no evidence) | Frontend |
| B015 | creator | 2 | Live preview transaction loop | B011 | not started (no evidence) | Frontend |
| B016 | creator | 2 | Semantic game diff | B012 | not started (no evidence) | Frontend |
| B017 | creator | 2 | Human approval boundaries | B013 | not started (no evidence) | Frontend |
| B018 | creator | 2 | Undo/redo across generated state | B012,B016 | not started (no evidence) | Frontend |
| B019 | creator | 3 | Visual scene and logic editing | B014,B016 | not started (no evidence) | Frontend |
| B020 | creator | 3 | Natural-language iterative repair | B015,B019 | not started (no evidence) | Frontend |
| B021 | gameplay | 1 | Canonical mechanics core | — | not started (no evidence) | Murash |
| B022 | gameplay | 1 | Entity/component/system substrate | — | not started (no evidence) | Murash |
| B023 | gameplay | 1 | Safe gameplay scripting runtime | — | not started (no evidence) | Murash |
| B024 | gameplay | 1 | Input/device abstraction | — | not started (no evidence) | Murash |
| B025 | gameplay | 2 | Save/state schema and migration | B021 | not started (no evidence) | Murash |
| B026 | gameplay | 2 | Inventory/equipment/items | B022 | claimed: Murash (murash/economy-inventory-currency-sinks) | Murash |
| B027 | gameplay | 2 | Combat/ability framework | B021,B022 | not started (no evidence) | Murash |
| B028 | gameplay | 2 | Quest/objective runtime | B021 | not started (no evidence) | Murash |
| B029 | gameplay | 3 | Economy and progression simulator | B026 | claimed: Murash (murash/economy-inventory-currency-sinks) | Murash |
| B030 | gameplay | 3 | Genre template composition | B021,B027,B028 | not started (no evidence) | Murash |
| B031 | ai | 1 | Model capability router | — | not started (no evidence) | Olly |
| B032 | ai | 1 | Project memory planes | — | not started (no evidence) | Olly |
| B033 | ai | 1 | Agent tool capability security | — | not started (no evidence) | Olly |
| B034 | ai | 1 | World-grounded NPC cognition | — | not started (no evidence) | Olly |
| B035 | ai | 2 | Narrative planner and canon graph | B032 | not started (no evidence) | Olly |
| B036 | ai | 2 | Dialogue/voice orchestration | B034,B035 | not started (no evidence) | Olly |
| B037 | ai | 2 | Constraint-guided quest synthesis | B035 | not started (no evidence) | Olly |
| B038 | ai | 2 | AI generation provenance | B031 | not started (no evidence) | Olly |
| B039 | ai | 3 | Self-repair and bounded optimization | B031,B038 | not started (no evidence) | Olly |
| B040 | ai | 3 | Game creation eval arena | B031,B039 | not started (no evidence) | Olly |

B041–B100 lanes: world Santo, assets Bork, network Walt, quality Gronk, security Internal Systems, platform Snappo.
