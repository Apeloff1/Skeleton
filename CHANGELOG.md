# CHANGELOG

All notable changes to Skeleton.

---

## 2026-08-31 — Product persist + merkle ledger + write router

- Dual-layer write route skip|update|new against wiki nucleus.
- Append-only merkle ledger + state.json (acquired/organism, gitignored).
- Operator product card: CLI `product`, GET /cortex/product.
- Field pointers: Mem0, Graphiti, Letta, Cognee, arXiv:2607.16848.
- Dual-layer cite arXiv:2608.22215. Docs: docs/PRODUCT.md.

---

## 2026-08-31 — Organismer 10× + social SOTA (ArchiveX / arXiv / labs)

- `skeleton/organism/organismer.py` — clipped G growth with source
  density S. Target G=10.
- `skeleton/social/` — source catalog, ArchiveX/Wayback pointers,
  ingest, SOTA coverage card. stored_prose=0.
- CommandDeck.organismer / social. CLI + HTTP.
- Seeded field pointers: Recuris, MindMemOS, O-Mem, MemGen,
  proactive-memory, context-codec, x-archive-rag, xf, xarchive.
- Tests: `skeleton/testing/test_organismer_social.py`.
- Docs: `docs/ORGANISMER.md`.

---

## 2026-08-30 — Hoag galaxy five-brain knowledge + context postprocess

- `skeleton/galaxy/` — memory, compiler, dream, distiller, editor.
  Wiki librarian nucleus. Colored mouth mirrors in the gap (every
  catalog family + house slots) via Jeeves.
- Knowledge codec T0–T5 + SOTA house decoder (commitment recall).
- Context post-process after seal; snowball mass unchanged.
- CommandDeck.galaxy, CLI `galaxy`, GET/POST `/cortex/galaxy`.
- Docs: `docs/HOAG_GALAXY.md`, `docs/BACKLOG.md`.
- Tests: `skeleton/testing/test_galaxy_brains.py`.
- stored_prose=0. Hoag cited, not copied.

---

## 2026-08-30 — Perpendicular cut (era bind × seven axes)

- `skeleton/cortex/era_bind.py` — title / slogan / ref-era collapse onto
  forge `ERA_IDS`. `cozy` compiles `cozy_wholesome`. `like Elden Ring`
  binds soulslike + Steam citation.
- `skeleton/cortex/perpendicular.py` — REF·ERA·LAW·TEACH·ASCEND·GENOS·OBSERVE
  as one card. `stored_prose=0`.
- `forge/eras.py::era_pack` consults `HOUSE_ERA` before fallback.
- `Jeeves.bind_era` / `plan_build` resolve like-titles to house era.
- `GameForgeRun.execute` uses `resolve()` so vision era is the pack era.
- CommandDeck.cut + CLI `python -m skeleton cut` + `POST /cortex/cut`.
- Tests: `skeleton/testing/test_cortex_perpendicular.py`.

---

## 2026-08-30 — Command deck HTTP + observe citation

- `skeleton/cortex/deck.py` — CommandDeck: speak/refer/improve/ascend/plan/genos/walk.
  `like <title>` auto-ascends. stored_prose 0.
- `skeleton/api/cortex_routes.py` — GET deck/laws/refs/dodeca; POST speak/refer/improve/ascend/plan/genos + dodeca walk/pick.
  Genesis handle if wired; live_cortex otherwise.
- CLI `python -m skeleton deck [stimulus] [--walk N]`
- Perpendicular: `observe_run` returns G + law + citation + stored_prose.
  `GameForgeRun.execute` payload carries citation + stored_prose.
- Tests: `skeleton/testing/test_cortex_deck.py`

---


## 2026-08-29 → 2026-08-28 — Deep-cut + build-plan campaign

A single working session of structural cuts, runtime-landmine fixes, and
surrounding-system build-out across the v16 package. 23 commits, zero
deletions.

### Runtime landmines found by reading (now pinned by tests)

| Bug | Effect | Commit |
|---|---|---|
| `retrieval/quad.py` called `EventBus.publish(str, dict)` | Four-plane retrieval lattice (RAG/CAG/MAG/KAG + RRF) raised `EventBusError` on every ingest/retrieve | 5a4d78a |
| `ConsensusError(…, ballot=…)` hit an unknown kwarg | Every failed swarm quorum raised `TypeError` | 972b802 |
| BFT consensus called `AgentId.generate()` | BFT crashed on every invocation | 972b802 |
| `AppState.cockpit`/`gameforge` declared-but-unwired | `/context/*` and `/gameforge/*` were permanent 503s | df7fbcd |
| `__main__.py` registered two subparsers both named `plan` | **Every CLI command dead at startup** (argparse `conflicting subparser`) | 3033821 |

### Structural deep cuts (fold-to-canonical, shims preserved)

- kernel `fair_queue.py` / `workqueue.py` → single `work_queue.py` DRR lane
  implementation (fe5ec07)
- kernel `vclock.py` mutable twin → immutable `clocks.py` (fe5ec07)
- `services/cag.py` dead route-module imports removed; prefix text
  single-sourced (c553ef8)
- retrieval twin `Reranker` classes disambiguated into rule-based `Reranker`
  + `FeatureReranker` (bdca180b)
- `genesis.py` imports canonical clocks path (bdca180b)
- `SubmitterCapError` finally exported from `skeleton/kernel` (338df9df)

### Build plan landed (BUILD_PLAN.md — full ledger in-repo)

- **API plane**: genesis handle introspection, telemetry mirrored onto the
  kernel bus, `X-Idempotency-Key` guard on forge/gameforge POSTs,
  `GET /telemetry/routes` (f6c7a78 → 3ebed65)
- **Memory convergence**: `skeleton/memory/prefix_renderer.py` +
  `skeleton/memory/warmer.py` own the KV-cache semantics; backend
  `services/cag.py` and `services/mag.py` are guarded shims that flip to the
  skeleton canonicals when importable; backend image vendors `skeleton/` so
  the flip runs in prod (51275cb → 48963bd)
- **Rank pipeline**: optional rule-boost → feature-rerank → diversity-rank
  stages, fixed order (31c8541)
- **Quad retrieval**: wired into Genesis and exposed at
  `POST /api/v1/retrieval/query|ingest` (5a4d78a, a5abbdc)
- **Swarm consensus**: ballot-carrying `ConsensusError`, AgentId fix,
  deliberate twin-mesh boundary documented in
  `skeleton/swarm/mesh_boundary.py` (972b802, e6e765b)
- **Context/cortex**: Cockpit + ten-stage GameForgeRun wired into lifespan;
  JeevesCortex given a genesis phase and read surface at
  `/api/v1/cortex/status|think` (df7fbcd, 3b22c74, 3892273)
- **CLI**: duplicate `plan` subparser renamed `build-plan` (3033821)

### Correction log

- A scaffold attempt (ca9238c) briefly rewrote the lifespan app factory and
  error envelope; both were restored verbatim from the prior commit
  (b4790a1). All subsequent build-plan edits are extend-only.

### Verification state

- `skeleton/testing/test_build_plan_smoke.py` — 15 tests covering queue,
  shims, reranker, pipeline, prefix renderer, warmer, idempotency, quad,
  genesis wiring, SubmitterCapError export
- `skeleton/testing/test_swarm_consensus.py` — 6 tests covering ballot
  carrying, raise paths, majority pass, BFT happy path
- Docs refreshed in this pass: README regenerated against the real tree,
  DEEP_CUTS extended with the session's new findings

### Deferred (Track E — requires local git ops)

Root sprawl moves, `SEVEN_BY_*.md` archival, the 103 MB `backend/godot`
binary relocation, and shim deletion (the three kernel shims plus the
`Reranker` alias).

---

## Aug 2026 → Feb 2026 — Backend monolith decomposition

See the previous entries below; this section covers the Phase-1 → Phase-9
backend decomposition and the Aug 2026 Godot-crate hardening that predates
the Skeleton v16 rewrite.

---

## Aug 2026 — Godot engine crate + backend packaging hardening

(Previous content retained below.)
