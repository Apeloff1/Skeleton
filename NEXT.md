# NEXT — factory queue (CoS, 2026-10-24)

Factory-style work, **no Cursor cloud agents**. Source of truth for claims: `artifacts/COS/FANOUT.md` + `artifacts/COS/STATUS.md`.

## Loop (every work unit)
1. Claim via Chief of Staff (one owner per unit; no claim = no push).
2. Fresh local clone on the box: `git clone https://github.com/Apeloff1/Skeleton /workspace/skel-<owner>-<unit>`.
3. Branch `<lane>/<unit-id>-<slug>-<yyyymmdd>` off current `main`. One unit per branch.
4. Gate locally: focused tests + `scripts/quality-gates.sh` subset for touched area; forge changes also run the local GameForge suite. Traceability-touching units run `python3 scripts/generate_master_traceability.py --check` and `tests/test_traceability_spine.py`.
5. Push via `gh` or GitHub MCP, open PR (`Closes #N` / `Refs Bxxx`), update `artifacts/COS/STATUS.md`.
6. Open PRs as **DRAFT** only. No merges this push; GitHub Ops promotes later, only fully green + Jenkins approval where required. If Actions is starved, don't re-run or stack pushes.
7. Status every hour to `artifacts/<bot>/status-YYYYMMDD-HHMM.md`; report to Grok Bot. Window: 2026-10-24 18:40–23:40 Oslo. Plan: `/workspace/skeleton-5h/plan.md` (box).

## Queue (priority order, owners per 5h plan)
| # | Unit | Source | Owner | Size |
|---|---|---|---|---|
| 1 | U01 8 skipped boot route modules | #4133 | Glenny (+Murash for creator_economy/marketplace) | M |
| 2 | U02 #4138 bind/retire plan ONLY, no removal | #4138 | Klint | S |
| 3 | U03 persistence docstring deprecations, no removals | #4122 | Coder Lead | S |
| 4 | U04 Game Frontier P0 runtime wiring + tests | #4167 | Santo | L |
| 5 | U17 P1 adapter interfaces + licence matrix (stubs, no weights) | #4168 | Bork | M |
| 6 | U18 P2 observe→reason→act→verify scaffold + win/loss tests | #4169 | Olly | M |
| 7 | U19 P3 FPS telemetry harness 30/50/60/120 + checklist | #4170 | Gronk | M |
| 8 | U05 repo atlas + duplicate report | #3721 | Wally | L |
| 9 | U06 FRONTIER_CONSOLIDATION inventory update | #80 | Carrol | S |
| 10 | U07–U16 #807 batches by lane (see lane map in BOT_BRIEF.md) | #807 | lane owners; Dispatch Manager hands out unclaimed | S–L |
| 11 | PR queue #4112,#4118,#4119,#4145,#4127 to green, dedupe | — | Throughput Delegator | — |
| 12 | U20 persistence migration phase | #4122 later | Coder Lead, after arch contracts | L |

Full specs: `artifacts/COS/ISSUES.md`. Assignments: `artifacts/COS/FANOUT.md`.
