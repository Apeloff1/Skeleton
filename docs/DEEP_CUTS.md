# Deep Cuts — Skeleton Thickness Audit

Full survey of `skeleton/` (15 packages, ~150 modules). Every directory listed, every file
under 1.5 KB read, plus both halves of every suspicious duplicate pair. This document isolates
the thin areas and records the cuts made in the accompanying fix commit.

---

## 1. Critical — broken package imports (fixed in this commit)

1. **`skeleton/retrieval/__init__.py` imported `.lexicon`** (`Lexicon`, `default_lexicon`) — no
   `lexicon.py` exists. That made the whole retrieval package unimportable, and poisons
   `tests/test_retrieval.py` at collection.
2. **`skeleton/jeeves/__init__.py` imported `.safety`** — no `safety.py` exists. Same blast
   radius: any `import skeleton.jeeves.<anything>` failed, so the tutor subsystem was
   unreachable through the package surface.
3. **`skeleton/pipelines/seeds.py` used `@dataclass` without importing it** — guaranteed
   `NameError` at import; the deterministic-seed helper didn't load.
4. **`skeleton/jeeves/troubleshooting.py`** — `next_step()` is annotated
   `Optional[Tuple[str, str]]`, but `diagnose()` claims to return `str` while actually returning
   the tuple (or the fallback tuple). Annotation corrected.

These four were found by reading every module under 1.5 KB, byte-by-byte, rather than trusting
the README's "no placeholders" claim.

---

## 2. Duplicate modules — parallel implementations

- **`forge/validator.py` vs `forge/validators.py`** — two forge validators. The exported one
  (`validator.py`: `CompositeValidator`, rule packs) operates on `Blueprint` objects; the
  unexported one (`validators.py`: `BlueprintValidator`, dict-shape with reference integrity and
  cycle detection) is strictly the stronger gate. Cut: `validators.py` is now exported from
  `skeleton/forge/__init__.py` alongside the rule-pack surface, canonical for pre-materialisation
  gating.
- **`retrieval/rerank.py` vs `retrieval/reranker.py`** — two rerankers sharing the class name
  `Reranker`. The exported one is rule-based boosts; the unexported one is a proper feature-based
  second-pass ranker (coverage, proximity, position, BM25 length norm). Cut: the feature-based
  ranker is now exported as `FeatureReranker` (with `RerankWeights`, `RankedItem`) from
  `skeleton/retrieval/__init__.py`.
- **`kernel/work_queue.py` vs `kernel/workqueue.py`** — the latter is a deliberate alias shim
  (`FairWorkQueue`); marked THIN-KEEP, no cut.

---

## 3. Thin areas (< 1.5 KB) — verdicts

| Path | Bytes | Verdict |
|---|---|---|
| `kernel/workqueue.py` | 599 | THIN-KEEP — deliberate alias shim |
| `resilience/types.py` | 874 | THIN-KEEP — threat enum/report types |
| `retrieval/highlight.py` | 1051 | THIN-KEEP — small but complete |
| `retrieval/ingest.py` | 1198 | THIN-KEEP — corpus → chunks |
| `retrieval/dedup.py` | 1383 | THIN-KEEP — signature dedupe |
| `retrieval/ranking.py` | 1297 | THIN-KEEP — post-fusion ranker |
| `pipelines/cache.py` | 1231 | THIN-KEEP — TTL memoisation |
| `pipelines/registry.py` | 1246 | THIN-KEEP — name → factory map |
| `pipelines/seeds.py` | 1239 | FIXED — missing dataclass import |
| `pipelines/hooks.py` | 1349 | THIN-KEEP — lifecycle hook points |
| `observability/coverage.py` | 1380 | THIN-KEEP — probe coverage audit |
| `observability/sampling.py` | 1342 | THIN-KEEP — head-based sampler |
| `swarm/roles.py` | 1523 | THIN-KEEP — role capability presets |
| `resilience/metrics.py` | 1342 | THIN-KEEP — threat counters |
| `jeeves/troubleshooting.py` | 1365 | FIXED — return-type lie corrected |

Nothing on the list was a hollow stub; the thin files are genuinely small utilities. The audit
method (size-filtered read) is what surfaced the two package-breaking imports and the seed bug.

---

## 4. Repo-wide observations

- The root of the repo carries ~45 flat `*_test.py` scripts alongside the `tests/` package —
  the `tests/` tree is the canonical pytest surface; the flat scripts are sweep/review harnesses
  left over from earlier waves. A future cut should relocate them under `scripts/` to match the
  README layout.
- `README.md` documents a far smaller tree than exists (claims 14 files; actual ~150). The
  subsystem map needs regenerating against reality.
- Importability should be a CI gate: `python -c "import skeleton.retrieval, skeleton.jeeves,
  skeleton.pipelines"` would have caught items 1–3 before merge.
