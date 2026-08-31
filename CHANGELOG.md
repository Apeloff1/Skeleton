# CHANGELOG

All notable changes to Skeleton.

---

## 2026-08-31 — Retain vs consolidate under live pressure

- organism/budget.py. Tight → consolidate (dream/tighten). Slack → retain.
- Walk N follows cap tier. Cite 2607.17545 as the split only.

---

## 2026-08-31 — Perpendicular: MHC, nucleus bind, field depth

- Pointers: EVAF 2606.26806, ProCL 2605.13162, retain/consolidate 2607.17545.
- Empty-stimulus pulses bind wiki nucleus URLs.
- MHC card on product/ready.

---

## 2026-08-31 — Bounded walk (not gameforge run)

- organism/runloop.py pulses until hold/tighten or N≤8.
- CLI walk, POST /cortex/walk. Does not steal `run`.

---

## 2026-08-31 — Pulse obeys next

- organism/pulse.py dispatches seed/dream/step/tighten/hold.
- CLI pulse, POST /cortex/pulse.

---

## 2026-08-31 — Product freeze 2026.08.31-ready

- product.version stamp. PRODUCT.md and STATUS.md match the live surface.

---

## 2026-08-31 — Ready ritual + wiki field in S

- organism/ready.py seeds an empty wiki then returns health/next/caps.
- CLI ready, GET /cortex/ready.
- _S gains up to 0.18 from wiki topic count.

---

## 2026-08-31 — Field seed + health carries next/journal

- social/seed.py files SOTA pointers as citation atoms. Idempotent.
- Persist-on first pulse seeds an empty wiki.
- Health includes next code and journal tail.
- CLI seed, POST /cortex/seed.

---

## 2026-08-31 — Next hint + pulse journal + S×coverage

- _S gains 0.20 × coverage score.
- organism/next.py coded hint. CLI next, GET /cortex/next.
- journal.jsonl capped by live atoms/8.

---

## 2026-08-31 — Perpendicular: coverage, 10x path, freshness, field

- Field pointers: GraphMemix 2608.26983, parametric KG 2608.25489,
  graph selection integrity 2606.12290, DMAS LTM 2601.07978.
- social/coverage.py. organism/path10.py. Editor.freshness.
- State persists last_health. Product embeds coverage + path10 + fresh.

---

## 2026-08-31 — Operator health card

- organism/health.py — ok/pressure/G/lattice/kv in one JSON.
- CLI health, GET /cortex/health. Product embeds it.

---

## 2026-08-31 — Hoag lattice card + gated KV handles

- galaxy/lattice.py — colored ring nodes + ASCII.
- galaxy/kv.py — residual handles only if transformer bound.
- CLI lattice, GET /cortex/lattice.

---

## 2026-08-31 — Adaptive caps: tighten now, ease later

- Pressure = 0.65 memory-fill + 0.35 load/cpu. Headroom shrinks with it.
- adapt() tightens immediately; eases only after two calm probes.
- trim_mesh evicts oldest low-value captures over the live cap.
- Organismer step runs adapt + trim.

---

## 2026-08-31 — Hardware multi-cap table (headroom 0.62)

- organism/caps.py probes RAM/CPU/GPU, tiers tiny→max, applies 0.62
  headroom so shelves sit below the wall.
- Atoms, vault, rules, query, residual, growth clip, CDX bytes read live().
- CLI `caps`, GET /cortex/caps. Env SKELETON_HEADROOM / SKELETON_TIER.

---

## 2026-08-31 — Wiki query, memory banks, write-back suppress

- SPARQL-shaped SELECT over wiki atoms.
- Common vs long-tail banks + residual hash block.
- High-value atoms tagged internalized; later near-duplicates skip.
- CLI wiki/banks, GET /cortex/wiki and /cortex/banks.

---

## 2026-08-31 — CCL vault + decoder device prior

- acquired/galaxy/vault.ccl compact codec lines.
- Decoder prior CPU-canonical; GPU tilt only if mouth device is not cpu.
- Vault written beside galaxy.json on persist.

---

## 2026-08-31 — MAD editor audit + idle dream + contact surface

- galaxy/mad.py — Jaccard collapse + robust-z outliers on principles.
- Editor.audit on every galaxy pulse. Organismer dreams every 4 steps.
- CLI `contact`, POST /cortex/contact.

---

## 2026-08-31 — Teacher contact rule + opt-in CDX probe

- Organismer step runs teacher sync then distiller gleans a
  contact-rule atom. Weights stay on the mouth.
- Opt-in CDX header probe (`--cdx` / SKELETON_CDX=1), 1s/host, 2KB cap.
- CommandDeck.contact.

---

## 2026-08-31 — Galaxy shelf persist + atom ids on the merkle chain

- galaxy/shelf.py — atoms + wiki topics survive process (cap 400).
- Atom.from_dict. Pulse returns atom_ids. Ledger line carries them.
- Product card exposes galaxy_atoms / wiki_topics.

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
