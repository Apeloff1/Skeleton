# 🔝 NEXT FORK — TOP PRIORITY: CHURN

> Set by user request ("Add churn next fork. As top priority."). The next agent/fork
> MUST start here before anything else.

## 1. Lint/Quality CHURN (do first)
Run a systematic, file-by-file cleanup of the remaining ~280 ESLint problems that were
intentionally deferred (they cause NO crashes but the user wants them cleared):
- `@typescript-eslint/no-unused-vars` — remove unused imports/vars across screens.
- `@typescript-eslint/array-type` — `Array<T>` → `T[]`.
- `react/no-unescaped-entities` — escape remaining multi-line/brace JSX text (`'`→`&apos;`, `"`→`&quot;`).
- `react-hooks/exhaustive-deps` — review each callback's deps (watch for real stale-closure bugs).
- `import/first` (e.g. hub.tsx) — move imports to top.
- `no-unused-expressions` — convert `cond ? a() : b()` statements to `if/else` (harmless but flagged).
Approach: lint per-file with the lint tool (`fix=true` for safe auto-fixes), verify each file
parses, then screenshot-smoke the app. Do NOT mass-regex across 100+ files (caused a `<TextInput>`
attribute corruption this session — always re-lint touched files).

## 2. Forge quality-gate CHURN (continuous improvement loop)
Forge audit scores consistently land BELOW the 95 gate (narrative Q48, physics Q58, tileset Q47,
camera, etc.). `_llm_json` now retries up to 4× and returns the HIGHEST-scoring attempt, but rarely
clears 95. Next fork: tune `routes/quality.py` (MIN_QUALITY / audit rubric) and/or the forge system
prompts so stages actually reach ≥95 — or add a "polish pass" that iterates a stage until threshold.

## 2.5 DEFERRED — new forge stages to add (user-requested, build after the churn)
Add these as additional Snowball forge stages (mirror the existing `_forge_*` pattern in
`backend/routes/game_kb.py`: a `_XXX_SYS` schema with the `'options'` array, an async
`_forge_xxx(pid, instruction)`, register in `_FORGES`/`_APPROVABLE`/`_STAGE_ART`/`_DOWNSTREAM`,
add to `_LADDER` in `snowball.py`, add a GDD section + summary). Each must scan game files +
vault (augmentation is automatic via `_llm_json(pid=..., stage=...)`):
- **quality forge** — holistic QA/polish pass (juice, game-feel, accessibility, bug list).
- **fine tuning forge** — numeric balance tuning (curves, drop rates, difficulty knobs).
- **critter & bestiary forge** — enemies/creatures: stats, behaviors, spawn tables, lore.
- **nature forge** — flora/biomes/weather/ecology systems.
- **realism forge** — physical/visual realism rules (lighting, materials, plausibility).
- **fine mechanic forge** — micro-mechanics & interaction details (input buffering, coyote time…).
- **movement forge** — locomotion/traversal (accel, jump arcs, dash, climb, swim).
- **city forge** — urban/level layout generation (districts, roads, POIs, density).

## 3. Known follow-ups (from finish summaries)
- Seamless Factory→Studio build-id handoff (DONE partially: `/studio` now auto-picks latest build).
- Auto-reap stale "running" forge jobs (DONE: get_job ceiling tightened to 8 min).
- "Maximise alternatives/options per stage" (DONE: `_EXHAUSTIVE_DIRECTIVE` added to every forge).

## Context anchors
- Snowball ladder (13 stages) + forges: `backend/routes/game_kb.py` (`_FORGES`, `_llm_json`, `_augment_for_forge`, `_EXHAUSTIVE_DIRECTIVE`).
- Snowball flow/skip/GDD: `backend/routes/snowball.py`.
- Unified entry screen: `frontend/app/studio.tsx`.
- Quality gate: `backend/routes/quality.py`.
