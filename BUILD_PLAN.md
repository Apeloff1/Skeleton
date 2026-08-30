# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Updated 2026-08-30, anchored to the deep-cut ledger (fe5ec07 → 62b36bf).

## Correction log

- ca9238c mistakenly rewrote api/server.py + api/errors.py; restored (b4790a1).
- B4/B5 deploy constraint: backend image originally vendored only backend/;
  shims guarded; B5 vendored skeleton/ (48963bd).

## Tracks — all buildable tracks DONE

- A — Interface plane — DONE (f6c7a78 → 3ebed65)
- B — Memory/caching convergence — DONE (51275cb → 48963bd)
- C — Retrieval rank plane — DONE (31c8541)
- D — Kernel queue convergence — DONE (9622493)
- F — Quad retriever wiring — DONE (5a4d78a)
- G — Swarm/mesh audit — DONE (972b802, e6e765b)
- H — Context/gameforge wiring + import audit — DONE (df7fbcd, a5abbdc)
- H5 — Cortex genesis phase + read surface — DONE (3b22c74, 3892273)
- I — CLI + lazy-import audit — DONE (3033821)
- Docs — README regenerated, CHANGELOG session entry, DEEP_CUTS Part II (bc4fa6b)

## Track J — Pipelines + resilience sweep — DONE (4126b52)

- [x] J1. `ResilientRunner` constructed `CircuitBreaker(policy=...)` — a kwarg
      the kernel breaker never accepted → TypeError at construction — and
      `run()` never engaged the breaker at all. Rebuilt: correct construction
      (name + thresholds), every run routed through before_call/on_success/
      on_failure, stage errors count as breaker failures.
- [x] J2. `PipelineComposer` recorded a raw TypeError when a stage returned a
      non-dict, hiding the real error; non-dict outputs now rejected with a
      clear StageError before the context merge.
- [x] J3. Verified clean (no cuts): core.py DAG runner, parallel.py level
      executor, retry.py wrapper, cache.py TTL memoisation,
      intelligence/orchestrator.py reason() signature vs the
      /intelligence/reason route, jeeves/matrices.py (SAM/CLOM/KREM
      snapshot()), memory/repetition.py (correct bus usage, forgetting-curve
      math), all five api helpers (auth/validation/filters/responses/
      middleware), resilience/fortress.py process_input signature.
- [x] J4. test_pipelines_fixes.py: 5 regression tests for J1/J2.

## Track E — Cleanup pass (deferred, requires local git ops)

- [ ] E1–E4 as before (root sprawl, SEVEN_BY docs, godot binary, shim removal).

## Remaining ideas (no deletion required)

- cortex/callosum + sleep + rl subsystems are exercised only via the neo
  transformer path; a smoke suite over them would catch drift early.
- H5.4: decide whether the genesis cortex twin should BE the live singleton
  once $SKELETON_OWN persistence exists in the container.

## Completed cuts (ledger)

fe5ec07 · c553ef8 · bdca180b · b4790a1 · f6c7a78 · 31c8541 · e3eaeca ·
3ebed65 · 9622493 · 5a4d78a · 972b802 · e6e765b · df7fbcd · a5abbdc ·
3b22c74 · 3892273 · 3033821 · bc4fa6b · 4126b52
