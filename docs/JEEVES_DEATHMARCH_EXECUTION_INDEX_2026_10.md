# Deathmarch execution index — 2026-10-13

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
