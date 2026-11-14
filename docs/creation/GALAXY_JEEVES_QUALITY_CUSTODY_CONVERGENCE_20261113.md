# Source-preserving Galaxy + Jeeves completion wave, 13 November 2026

**Base:** integration PR #5318 exact head
`1ecf4b8dc79137ad15318e8953aaed108f71488b`.

**Archival inputs:**
- PR #5313 at `30ed3ea8c4d973e12c2abae013ccee5205331115` supplies the bounded
  offline-first genre catalog merge, device scoped authoring concepts and
  the known Galaxy `beat_em_up`, `shoot_em_up` specialization IDs.
- PR #5285 at `06515a6e93f76d4fdf13067553438137dcdb2dac` supplies the exact
  public 24-task game-quality scorer and official Godot reference summary,
  local pinned GGUF quality-evaluation CLI, cross-process execution lease
  and source/AI mirrors.

## New functional integration

1. Preserve all **67** original Galaxy offline genres; add the two
   historically recognized specialties to reach **69 actual offline
   picker choices**. These map to the 158-genre creative intake but do not
   certify 69 or 158 independent playable engines.
2. Validation of live server genre data is capped at 512 rows with bounded
   subgenre labels, names, colors and file counts. Partial server responses
   can no longer replace and erase the historical offline catalog.
3. **Explicit Save full Galaxy design** control in the original Galaxy
   Studio view. It passes the same authoritative authored payload used by
   the complete 14-matrix GameForge handoff. The local snapshot is
   versioned, complexity-bounded, 30-day expiring and scoped to the active
   local auth fingerprint/epoch. No cleartext token is used as a storage
   key. Data is stored with AsyncStorage and is **not encrypted at rest**.
4. **Explicit Restore saved design** control in the modern GameForge
   questionnaire; reuse the existing `importGalaxy` reducer to preserve
   all source matrices, narrative/style parameters and the existing
   ten-axis mapping. No automatic replacement or background game build.
5. Exact-source archived Jeeves game-quality assessment (24 public tasks,
   deterministic dimensions) with Python/AI mirror parity, source-bound
   local GGUF operator CLI, strict source custody, bounded local
   execution leases and frozen reference provenance.
6. A read-only `GET /api/skeleton/jeeves/game-quality` endpoint and a
   collapsed GameForge UI inspector show taskset identity and breadth.
   This does **not** execute a model or certify inference quality.
7. Focused tests cover 69/158 catalog survival, malicious remote rows,
   snapshot expiration, exact authoring round-trip, account isolation,
   strict quality scorer, reference pack, endpoint identity and UI
   presence.

## Required qualifications

```sh
cd frontend
node --test scripts/skeleton-forge/{genre-registry-recovery,galaxy-profile-snapshot,galaxy-profile-custody,galaxy-save-restore-controls,jeeves-quality-panel,instruments,multigenre-playable}.test.cjs
yarn typecheck
cd ..
PYTHONPATH=.:backend python -m pytest -q --noconftest \
 tests/test_game_builder_quality.py \
 tests/test_game_builder_reference_pack.py \
 backend/tests/test_jeeves_game_quality_catalog.py \
 skeleton/testing/test_historical_controls_full_catalog.py \
 skeleton/game/presentation/test_genre_action_profiles.py
python scripts/check_ai_file_tree.py
```

Then full exact-head Merge Readiness, Backend Quality, E2E, Godot native,
Windows/WSL2, local GGUF, CodeQL, secret scan, dependency, artifact,
malware, hygiene and release provenance. No queued, skipped, cancelled,
mocked or ancestor outcome is considered passing.

**Never merge/auto-merge/release this work until required exact-head
evidence passes.** The new control, executor and UI are distinct from
actual native hardware acceptance.
