# Repository Consolidation — August 2026

**Skeleton is the single canonical repo for the Tutolage platform.**

## Repo survey & verdicts

| Repo | Contents | Verdict |
|------|----------|---------|
| **Skeleton** (canonical) | 287 backend routes, full frontend, 200+ modules, tests | **Survives** |
| Tutolage | 46 backend routes, older frontend, config files | Merged (see below), then archive |
| Prood | Byte-identical duplicate of Skeleton's 79 root files | Redundant — safe to delete |
| Prod, gameforge-rs, Ai-gamestudio, Piper, Restorepoint, resting-22, Ieresting-22 | Empty | Nothing to merge — delete |
| 2dv0.1–0.4, 2d, Openworld*, Newmove*, Hotday*, Summer, lage, tolage | Old JS game prototypes | Superseded — archive |

## Tutolage merge (file-level diff)

A full diff of both repos was run. Results:

- **Routes: 0 to merge.** All 46 Tutolage routes already exist in Skeleton's 287.
- **Frontend: 0 to merge.** Skeleton's is strictly newer (has `src/`, `state/`,
  `theme/`, `app.config.js`, `babel.config.js`, `eas.json`); Tutolage only adds
  a `package-lock.json` (Skeleton uses yarn) and a `.metro-cache/` build dir.
- **docker-compose.yml — merged.** Tutolage's had Mongo auth, healthchecks, a
  ChromaDB profile, and the full Expo port range; combined with Skeleton's
  data-volume layout.
- **`.pre-commit-config.yaml` — merged.** Tutolage's was a strict superset:
  mypy, ESLint, Prettier, bandit, hadolint, commitizen on top of ruff. Adopted
  wholesale, with the large-file limit raised to 110 MB so the Godot binary
  stays committable.
- **`backend/pyproject.toml` — merged.** Tutolage's richer tooling config
  (stricter ruff rules, per-file ignores, mypy block, coverage branch mode,
  pytest markers) ported onto Skeleton's naming; dependencies kept aligned with
  the rebuilt `requirements.txt`.
- **README — kept Skeleton's.** Tutolage's longer README is an older
  "CodeDock"-branded draft; Skeleton's is current.

## Consolidation fixes (earlier pass)

- Added `LICENSE` (MIT) and `.env.example` files (root / backend / frontend).
- Fixed `.gitignore` env contradiction — real env files ignored, examples tracked.
- Rebuilt `backend/requirements.txt` (was a 190-package machine freeze with CUDA
  toolkits and PyInstaller); fixed the `bcrypt 5.x` / `passlib 1.7.4` break by
  pinning `bcrypt==4.0.1`.
- Corrected README clone URL (pointed at a nonexistent `tutolage/tutolage`).

## Godot engine (in-repo binary → first-class subsystem)

The 103 MB `backend/godot` binary is the app's game engine, wired in as
`backend/gameforge/godot_engine/` — one focused module per concern:

- `binary.py` — locate/verify/profile the binary (async probe, version, headless self-test)
- `cache.py` — TTL cache with stale-while-revalidate
- `logbuffer.py` — per-job ring log capture
- `scheduler.py` — staggered queue, bounded concurrency, cancellation
- `pipeline.py` — headless jobs (import / GDScript check / export) as tracked tasks
- `project.py` — scaffold runnable Godot 4 projects from specs
- `scenes.py` — .tscn generators (platformer / topdown / empty)
- `controllers.py` — playable GDScript player controllers
- `presets.py` — export presets (desktop / web / mobile)
- `health.py` — deep health snapshot (probe + disk headroom + dir writability)

HTTP surface: `backend/routes/godot_engine.py` at `/api/godot-engine`, mounted
through the declarative registry in `backend/core/routes_registry.py`
(engines group). Generated projects/builds live under `backend/data/godot_projects/`
and `backend/data/godot_builds/` (volume-backed, gitignored).

Try it:

```bash
curl http://localhost:8001/api/godot-engine/status
curl -X POST http://localhost:8001/api/godot-engine/projects \
  -H 'Content-Type: application/json' \
  -d '{"title": "My First Game", "description": "Scaffolded by Tutolage"}'
```

## Known remaining issue

`test_result.md` and `backend_test.py.bak_1779283310` are gitignored but still
tracked in history. The GitHub API returns `GitRPC::BadObjectState` on tree
creation touching this repo's older objects (likely the 103 MB godot blob).
Untrack them locally:

```bash
git clone https://github.com/Apeloff1/Skeleton.git
cd Skeleton
git rm --cached test_result.md backend_test.py.bak_1779283310
git commit -m "chore: untrack test dump and backup file"
git push
```


## Workspace census (2026-08-27)

Canonical product is **Apeloff1/Skeleton** (public, Python, GameForge + Jeeves cortex).
Grok App Builder `/workspace` is a TanStack Start scaffold — not the product. `/workspace/artifacts` is empty. Live clone: `/tmp/skel/Skeleton`.

| Repo | Visibility | Size | Verdict |
|---|---|---|---|
| **Skeleton** | public | ~107 MB | Canonical. Hexagonal Tutolage rewrite + GameForge + cortex. |
| Tutolage | public | ~45 MB | Merged (see above). Archive. |
| hyperforge-cockpit-sota | public | 493 kb | 3D ECS cockpit prototype. Superseded by Skeleton cockpit. |
| gameforge-middleware | private | 14 kb | C# Zaibatsu gate. Keep as sibling; not in Python spine. |
| gameforge-rs | private | 106 kb | Rust axum port. Sibling; do not merge into Python. |
| Prood | private | ~58 MB | v15 monolith. Byte-overlap with Skeleton root. Do not merge. |
| Prod, Ai-gamestudio, Piper, Restorepoint, resting-22, Ieresting-22, Hotday, Hotdayz, lage, Summer, Nextstep, Nextstepz, tolage, utolage | private | 0 kb | Empty. Nothing to merge. |
| 2d, 2dv0.2–0.4, 2dv1, Openworld*, Newmove*, Newsay*, Newstuff*, Lorebuff*, Saymore*, Expa, Newfix | public/private | JS prototypes | Superseded. Archive. |
| Asds, Ggg, New-tey, Interesting-22 | private | large dumps | Not GameForge. Leave. |

52 owner repos surveyed via GitHub API. One git clone on this host: `/tmp/skel/Skeleton`.

## Cortex LM (2026-08-27)

Jeeves neo is a stacked Pre-LN transformer (n_layers=2, n_heads=2, d_ff=32) that actually runs those layers in pure Python. GPU is a harness: `probe()` / `to("cuda")` pins `TorchAccel` when torch sees a GPU; weights stay resident; decode/SGD run on-device; snapshot syncs lists back. No torch in CI. After `train()`, `BuilderBrain.plan(..., cortex=neo)` briefing is authored by the own-lm decode (`LM:` prefix). Veto still beats the LM.

Specialist heads live on the neo residual: left numeric mix, right bias, midbrain route, PFC veto+policy. Corpus callosum splits the residual into left/right streams with a K=4 working-memory bank and Hebbian coupling when both fire. MoE bank (4 residual adapters + softmax router) is how acquire copies the MODELS not the prompts; `fingerprint()` is the merkle of those guts. Sleep replays the buffer (heads SGD, adapter distill, Hebb, EMA of Wout). REINFORCE takes walk slack as reward on the numeric head. Builder will take a fitted MoE mix if thermal walk still extracts, unless the hive imported/invented mix said skip_search.
