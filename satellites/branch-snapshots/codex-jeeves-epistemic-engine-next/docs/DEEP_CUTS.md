# Deep Cuts — Skeleton Thickness Audit

Original full-survey audit plus the 2026-08-28/29 follow-up pass. This
document records which file pairs and thin areas were isolated, and the
cuts made in their accompanying fix commits.

---

## Part I — Original audit (Feb 2026)

### 1. Broken package imports (fixed in that commit)

1. `skeleton/retrieval/__init__.py` imported `.lexicon` — no `lexicon.py`
   existed → whole retrieval package unimportable.
2. `skeleton/jeeves/__init__.py` imported `.safety` — no `safety.py` existed
   → tutor subsystem unreachable.
3. `skeleton/pipelines/seeds.py` used `@dataclass` without importing it —
   `NameError` at import.
4. `skeleton/jeeves/troubleshooting.py` return-type lie — `diagnose()`
   annotated `str` while returning a tuple.

Found by reading every module under 1.5 KB byte-by-byte.

### 2. Duplicate modules — parallel implementations

- `forge/validator.py` vs `forge/validators.py` — the exported rule-pack
  validator and a stronger unexported dict-shape validator; the stronger one
  exported alongside, canonical for pre-materialisation gating.
- `retrieval/rerank.py` vs `retrieval/reranker.py` — rule-based boosts vs a
  feature-based second-pass ranker; exported as `FeatureReranker`.
- `kernel/work_queue.py` vs `kernel/workqueue.py` — deliberate alias shim,
  kept.

### 3. Thin-area (< 1.5 KB) verdicts

All THIN-KEEP except the two fixed modules; the size-filtered read method is
what surfaced the package-breaking imports.

### 4. Repo-wide observations

- ~45 flat `*_test.py` scripts at root → relocate under `scripts/` was
  recommended (still pending in Track E).
- `README.md` under-documented the tree (~14 files claimed vs ~150 actual)
  — regenerated 2026-08-29.
- Importability should be a CI gate: `python -c "import skeleton.retrieval,
  skeleton.jeeves, skeleton.pipelines"`.

---

## Part II — Follow-up pass (2026-08-28 → 2026-08-29)

A second survey over the v16 tree after six build-plan sessions, performed
before the runtime-landmine commit series. Findings and cuts:

### 5. Runtime landmines now pinned by tests

| # | Surface | Bug | Commit |
|---|---|---|---|
| 5.1 | `retrieval/quad.py` | called `EventBus.publish(str, dict)` — four-plane retrieval crashed on every call | 5a4d78a |
| 5.2 | `swarm/consensus.py` + `swarm/mesh.py` | `ConsensusError(…, ballot=…)` hit an unknown kwarg → `TypeError` on every failed quorum | 972b802 |
| 5.3 | `swarm/consensus.py` (BFT) | called `AgentId.generate()`, which the id lattice never had | 972b802 |
| 5.4 | `api/server.py` lifespan | `cockpit`/`gameforge` declared-but-unwired → `/context/*` and `/gameforge/*` permanent 503s | df7fbcd |
| 5.5 | `__main__.py` | two subparsers both named `plan` → argparse `conflicting subparser` — every CLI command dead at startup | 3033821 |

### 6. Duplicate modules (folded to canonical, shims preserved)

- `kernel/fair_queue.py` orphan priority-heap → shim onto `work_queue.py`
  (fe5ec07)
- `kernel/vclock.py` mutable twin → shim onto `clocks.py` (fe5ec07)
- `retrieval` rule `Reranker` vs feature `Reranker` disambiguated as
  `FeatureReranker` with a legacy alias (bdca180b)
- Backend `services/cag.py` and `services/mag.py` → guarded shims over
  `skeleton.memory.prefix_renderer` / `skeleton.memory.warmer` (324db3d,
  7790918)
- `agents/mesh.py` vs `swarm/mesh.py` — audited and kept as deliberate
  twin-mesh boundary: operational roster (API) vs research substrate
  (Genesis) — documented in `skeleton/swarm/mesh_boundary.py` (e6e765b)

### 7. Thin-area verdicts (new survey)

| Path | Verdict |
|---|---|
| `kernel/workqueue.py` | THIN-KEEP — deliberate alias shim |
| `kernel/fair_queue.py` | THIN-KEEP — after fold, a shim |
| `kernel/vclock.py` | THIN-KEEP — after fold, a shim |
| `memory/store.py` interface | THIN-KEEP — ABC contract |
| `retrieval/ranking.py` | THIN-KEEP — third rank primitive |
| `api/telemetry.py` | EXTENDED — optional bus mirror added |
| `api/idempotency.py` | EXTENDED — guard + header extraction added |

### 8. Repo-wide observations (2026-08)

- The biggest remaining H5-grade unwired surface was the 44-module `cortex`
  — given a genesis phase and a read-only API surface (3b22c74, 3892273).
- The backend memory stack (`services/memory_engine.py`) is a live facade
  over the skeleton canonicals once the guarded shims flip; the backend image
  vendors `skeleton/` as of commit 48963bd.
- Root sprawl, `SEVEN_BY_*.md` archival, 103 MB godot binary, and shim
  deletion sit in Track E — all deletion-shaped, local-git territory.

---

## Methodology

Every survey was a size-filtered read: list the tree, then read (not import)
files under the threshold, plus both halves of every duplicate pair. It is
the method that found each bug above — none surfaced through import-time
failures until they were read.
