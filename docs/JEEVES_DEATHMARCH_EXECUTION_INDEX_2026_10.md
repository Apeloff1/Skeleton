# Deathmarch execution index — 2026-10-13


## DX-31–DX-58 — real original-game authoring, source output, human publication

The existing game editor, authoring workspace, game compiler, offline browser
renderer, Godot source exporter, and prompt router now share **one governed
Jeeves production lane**, rather than independent mock demonstrations.
These are committed source implementations; product qualification awaits
separate exact-head and installed-platform acceptance.

| Milestone | Real committed functionality | Existing canonical owner |
| --- | --- | --- |
| DX-31 | 1–24 installed engine source configurations generated with actual schema | \`jeeves_production_wave.py\` |
| DX-32 | Exact-plan source SHA/active-project reviewed configuration staging | \`JeevesProductionWave.stage\` |
| DX-33 | Real procedural original authored playable scene sources | \`JeevesProductionWave.plan(phase="scenes")\` |
| DX-34 | Scene source binds actual previously committed system settings | \`GameWorkspace._validate_advanced_scene_source\` |
| DX-35 | Per-source optimistic concurrency and user-controlled game source ownership | \`GameWorkspace.propose\` |
| DX-36 | Interactive multi-engine/scene plan-and-stage Game Studio panel | \`game_workspace_ui.py\` |
| DX-37 | Actual original playable world compilation from typed finite intent | \`jeeves_original_release_wave.py\` |
| DX-38 | Executed winning path by existing original-game simulator | \`compile_original_game\` |
| DX-39 | Actual standalone offline browser game source output | \`render_dual_runtime_package\` |
| DX-40 | Actual Godot 4 source project, world JSON, proof and tile editor output | \`render_dual_runtime_package\` |
| DX-41 | Source SHA-256 and manifest-bound native project review proposals | \`JeevesOriginalReleaseWave.stage\` |
| DX-42 | Native \`.godot\` source support in canonical reviewed workspace | \`game_project_workspace.py\` |
| DX-43 | Interactive original browser/Godot source compilation/staging cockpit | \`game_workspace_ui.py\` |
| DX-44 | Persisted source proposals become complete per-file unified diff reviews | \`jeeves_production_review.py\` |
| DX-45 | Explicit per-file SHA approval uses **real** canonical workspace commits | \`JeevesProductionReview.commit\` |
| DX-46 | Partial commits report completed prefix and outstanding IDs honestly | \`JeevesProductionReview.commit\` |
| DX-47 | Canonical natural-language game prompt router connected to editor construction | \`jeeves_prompt_production.py\` |
| DX-48 | Real typed engine sources selected by prompt axis, not guessed model behavior | \`JeevesPromptProduction.plan\` |
| DX-49 | Exact prompt and source plan digests before any source proposals | \`JeevesPromptProduction.stage\` |
| DX-50 | Live prompt-based user editor source production and review cockpit | \`game_workspace_ui.py\` |
| DX-51 | Real original multiple game worlds generated from controlled seed changes | \`jeeves_game_variants.py\` |
| DX-52 | Optional supported original-theme variation across independent worlds | \`JeevesGameVariants.plan\` |
| DX-53 | Actual individual offline browser/native source manifests for each world | \`JeevesOriginalReleaseWave.plan\` |
| DX-54 | Source-custodied portfolio proposal staging with partial-stage honesty | \`JeevesGameVariants.stage\` |
| DX-55 | Live original-game source variants Studio cockpit | \`game_workspace_ui.py\` |
| DX-56 | Durable pending/accepted proposal records inventoried with active project identity | \`jeeves_proposal_queue.py\` |
| DX-57 | Stale/conflicting and malformed source proposal custody identified | \`JeevesProposalQueue.page\` |
| DX-58 | Interactive paginated proposal custody and exact-review queue handoff | \`game_workspace_ui.py\` |

### Concrete source changes

- **Core/runtime adapters:** \`jeeves_production_wave.py\`,
  \`jeeves_original_release_wave.py\`, \`jeeves_production_review.py\`,
  \`jeeves_prompt_production.py\`, \`jeeves_game_variants.py\`,
  \`jeeves_proposal_queue.py\`.
- **Actual write boundary:** the existing \`game_project_workspace.GameWorkspace\`
  with source proposals and explicit human-approved commit; no second
  filesystem writer, tool authority, provider SDK or background worker.
- **Client:** the installed \`game_workspace_ui.py\` gains production sources,
  playable/native game exports, independently different game variants,
  prompt-based studio authoring, exact diff approval, commit, and queue
  browsing. All source content is rendered as text, not executable HTML.
- **Compatibility:** all new adapters route through the existing Jeeves
  \`jeeves_appwide_fabric.JeevesAppwideRuntime\`, which already uses the
  authenticated local Game Studio API; source runtime boundaries remain intact.

### Build-only truth

No repository unit tests, CI suites or hardware smoke tests were executed
in this workpass, at the user's direction. The *product feature*, when
called by a designer, runs the existing original-game compiler and its
intrinsic winning replay, which is a compilation prerequisite rather than
a repository test suite.

Actual generated browser source and Godot source packages are **code**, not
certified binaries. GameWorkspace source files become real project contents
only after independent human review and explicit commit. No trained model
self-modification, model-performance gain, production deployment, mainline
merge, or enterprise qualification is claimed.


## DX-18–DX-30 — multi-file construction, real source navigation and critical path

| Milestone | Committed feature | Source |
| --- | --- | --- |
| DX-18 | Bounded 8-file reviewed exact-hunk source patchsets | \`jeeves_source_patchset.py\` |
| DX-19 | Whole-patchset preflight, source SHA and overlapping-hunk refusal | \`jeeves_source_patchset.py\` |
| DX-20 | Real UTF-8 source-content search with stable bounded cursor | \`jeeves_code_navigator.py\` |
| DX-21 | Exact source SHA-256 and line-paged context | \`jeeves_code_navigator.py\` |
| DX-22 | Live Studio source-content search controls | \`game_workspace_ui.py\` |
| DX-23 | Search result → SHA-bound source snippet handoff | \`game_workspace_ui.py\` |
| DX-24 | Reviewed multi-file patch cockpit, never automatic commit | \`game_workspace_ui.py\` |
| DX-25 | Python and JS/TS real syntax import topology | \`jeeves_dependency_navigation.py\` |
| DX-26 | Bounded graph traversal, hashed sources and incompleteness labels | \`jeeves_dependency_navigation.py\` |
| DX-27 | Source dependency graph inspector in Game Studio | \`game_workspace_ui.py\` |
| DX-28 | Canonical graph longest structural chain and bottlenecks | \`jeeves_critical_path.py\` |
| DX-29 | Dependency and priority breakdown by canonical task owner | \`jeeves_critical_path.py\` |
| DX-30 | Interactive critical-path and owner workload cards | \`game_workspace_ui.py\` |

Registered source adapters: \`source.patchset.preview\`,
\`ai.code.search\`, \`ai.code.snippet\`, \`ai.code.dependencies\`,
\`ai.milestones.critical\` and \`ai.milestones.owners\`.

**No tests executed in this build-only pass.** A source patchset is a
proposal, not a committed patch; a syntax import is not runtime evidence;
a structural critical chain does not imply an engineering duration.
All release and completion checks remain dependent on later exact-head
acceptance and stacked-branch landing.

## Workpass DX-09–DX-15 — real Jeeves appwide continuation

Source branch: \`feat/jeeves-evidence-graph-scale-20261013\`, stacked
behind #3738 → #3730 → #3729 → #3718. This workpass adds functional
source-grounded tooling without inventing a new AI runtime owner.

| Milestone | Delivery | Code |
| --- | --- | --- |
| DX-09 | Dependency-respecting, per-owner parallel workwaves with paged receipts | \`jeeves_deathmarch_workpacks.JeevesWorkpackDirector.waves\` |
| DX-10 | Canonical milestone-to-source workpacks: hashes, source excerpts and budgets | \`JeevesWorkpackDirector.workpack\` |
| DX-11 | Source-pinned change frontier and conservative graph blast radius | \`JeevesWorkpackDirector.change_frontier\` |
| DX-12 | Directory-owned app/AI capability context expansion, labeled as sampled | \`JeevesWorkpackDirector._source_paths\` |
| DX-13 | File-and-directory impact propagation into canonical acceptance milestones | \`JeevesWorkpackDirector.change_frontier\` |
| DX-14 | Multi-plane editor/director/forge/Dragon/crawler *real* preview batching | \`jeeves_batch_workbench.run_batch_preview\` |
| DX-15 | Batch-level preflight, typed action allow-list, budgeted result custody | \`jeeves_batch_workbench._admit\` |

Registered in the existing \`JeevesAppwideRuntime\` action dispatch:
\`ai.workwaves\`, \`ai.workpack\`, \`ai.change_frontier\`,
\`studio.batch_preview\`. All remain limited to source reads, editor
templates, simulated previews or other reviewed non-mutating adapters.
Individual \`source.propose\` and production compilers retain their own
separate operator gates.

**DX-16–17:** Existing local Game Studio serves a new interactive deathmarch deck, backed by the already authenticated `jeeves-appwide-invoke` route. The UI uses text-only JSON output, rejects invalid counts, and never requests source-write authority. Distinct action selector IDs remove an existing page-level collision between the appwide panel and capability cockpit.

**Scope/status:** source implementation landed on a draft stacked branch.
No tests were run by request. No production release, merge, model weight
promotion, successful device build or enterprise AI completion is claimed.
The existing exact-head CI and app journey blockers remain outstanding.

See \`docs/JEEVES_DEATHMARCH_WORKPACKS_2026_10.md\` and
\`docs/JEEVES_MULTI_ADAPTER_WORKBENCH_2026_10.md\` for the operator API.

**Active integration PR:** #3730, stacked on #3729 and #3718.  
**Truth rule:** An unmerged branch and a partially passing CI workflow are not a released application. This file tracks durable implementation changes, exact failures, and the next bounded actions. Update it when CI changes.

## Implemented this workpass (real commits, not claimed release qualification)

| Work | Source of truth | Implementation |
| --- | --- | --- |
| DX-01: whole-app completion | `skeleton/ai/game_builder/jeeves_completion_census.py` | Eight-source authority read, source-hash evidence, 421 AI volumes, 9 product capabilities, 27 architecture planes, 5 runtime services, P0/P1 closure distinction, missing owners/paths, 11 enterprise domains and 12 journeys |
| DX-02: Jeeves source intelligence | `skeleton/ai/game_builder/jeeves_capability_intelligence.py` (upstream #3729) | Static language exports, bounded context, selected dependency graph, duplicate scouts |
| DX-03: work frontier | `JeevesCompletionCensus.backlog` and `JeevesAppwideRuntime.invoke("ai.deathmarch", ...)` | Deterministic priority-sorted page of AI capabilities, app runtime services, enterprise workstreams, system journeys, source repairs and volume qualification. Each item has specific acceptance evidence and a fail-closed source receipt. No automation authorization |
| DX-04: stale plan evidence | `.github/workflows/game-builder-jeeves-story-canon.yml` | Refuses to fake index freshness: parse-index mismatch is reported as an actual acceptance blocker instead of asserting that every signature is already current |
| DX-05: quest system | `advanced_quest_director_runtime.py` | `event_rules` now controls count of causal rule variants; a single allowed variant does not silently suppress witnessed discover/help/harm/repair quest origins |
| DX-06: ecosystem | `advanced_ecosystem_runtime.py` | Food-consuming dormant populations get finite bounded food allocation before active species exhaust it, preserving ledger accounting and avoiding synthetic production |
| DX-07: fighting/rollback acceptance | `tests/test_game_builder_advanced_fighting.py`, `tests/test_game_builder_advanced_fighting_rollback.py` | Verify block effectiveness against exact attack type rather than different adaptive AI choices; zero regen when asserting net spend; normalize health through canonical editor; verify wrapped API errors |
| DX-08: advanced engine maturity | `tests/test_game_builder_advanced_runtime.py` | Replace obsolete Maze/RPG unsupported assertion with real replay validation plus unknown-engine refusal |

## Real gate history and outstanding failures

- #3729: **Jeeves Windows and Ubuntu target suite passed** at SHA `00c79418`; Secret scanning and native Godot replay also passed. Broader `AI Game Builder 500 Levels` failed obsolete Maze/RPG capability assertions, fixed in #3730.
- #3730 prior SHA `06401f42`: Jeeves suite **82/82 passed** in Ubuntu, but its additional whole-app contract assertion failed because the canonical masterplan parse-index signature was not current. The explicit stale/evidence check was repaired without altering the signed authority.
- #3730 prior SHA `06401f42`: advanced engine lane **474 tests; 3 failures + 3 errors**. Failure categories: fighting attack economy and adaptive guard tests, fighting rollback fixture, witness quest rule parameter, finite dormant ecosystem food. Fixes here require **new exact-head validation** before closure.
- Windows hardware release, real trained GGUF benchmark, full game production package, all 12 enterprise journeys, and 421 independent enterprise qualifications are **not certified** by any of the above source/test reports.

## Machine-readable continuation / minimal AI context

Use the installed repository and the canonical existing Jeeves runtime; avoid inventing additional runtime islands.

```python
from pathlib import Path
from skeleton.ai.game_builder.jeeves_appwide_fabric import AppwideInventory, JeevesAppwideRuntime
inv = AppwideInventory(Path.cwd())
inv.scan()  # explicit finite source inventory; no execution by discovered code
runtime = JeevesAppwideRuntime(inv)
census = runtime.invoke("ai.completion", {})["result"]
frontier = runtime.invoke("ai.deathmarch", {
    "limit": 20, "expected_report_digest": census["digest"]
})["result"]
print(census["readiness"]["blocking_conditions"])
print(frontier["total_work_items"], frontier["next_offset"])
```

The frontier intentionally summarizes source-derived categories, not arbitrary GitHub CI conclusions. GitHub workflow/run/commit status must be inspected separately at the exact head before an acceptance task is marked done. Never copy historical test-green status to a newer SHA.

### Work budget and next action

1. **First close failing exact-head regression lanes** in priority order: Jeeves source/signature truth, quest and ecosystem, fighting/rollback, then advanced engines and 500-level suite.
2. **Re-run and inspect** exact-head Windows and Linux steps, read failure logs, repair root causes and add targeted security/identity tests.
3. **Consolidate overlapping index PRs** #3722–#3728 into a single indexed owner with correctness/parity checks and archive evidence. Do not blindly squash competing inventories.
4. **Land stacked features in dependency order** after required CI passes: #3718 → #3729 → #3730. Rebase individual PRs if underlying main changes before merge.
5. **Advance next functional closure milestones:** appwide UI→adapter exact contract coverage, actual trained local AI and safe tool execution, end-to-end game outputs and platform smoke, crawler/Dragon source custody, learning holdouts and release.

**Status at time of writing:** code committed to a draft integration branch. All status values above are source-scoped. Full application completion percentage remains unknown until weighted end-to-end acceptance; registry-complete product AI capabilities remain 0/9 at last inspected `main`.
