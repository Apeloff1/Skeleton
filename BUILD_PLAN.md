# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Generated 2026-08-28, anchored to the deep-cut ledger (fe5ec07, c553ef8, bdca180b).

## Correction log

- ca9238c mistakenly rewrote api/server.py + api/errors.py; restored (b4790a1).
  Rule: extend only, read before touching.
- B4/B5 deploy constraint discovered via backend/Dockerfile + compose: image
  originally vendored only backend/. Shims guarded; B5 vendored skeleton/.

## Track A — Interface plane (skeleton/api) — DONE (f6c7a78 → 3ebed65)

## Track B — Memory/caching convergence — DONE (51275cb → 48963bd)

## Track C — Retrieval rank plane — DONE (31c8541)

## Track D — Kernel queue convergence — DONE

- [x] D1. Audited: `genesis.py` imports canonical clocks; the three shims
      (`workqueue.py`, `fair_queue.py`, `vclock.py`) are pure re-exports with
      zero internal consumers — they ARE the deprecation layer. Nothing left
      to cut without deletion; shim removal queued under E4.
- [x] D2. `WorkQueue` optional per-submitter caps + deadline expiry (e3eaeca).

## Track E — Cleanup pass (deferred, requires local git ops)

- [ ] E1. Move 50 loose root test/sweep scripts into `tests/` and `scripts/`.
- [ ] E2. Move 8 `SEVEN_BY_*.md` docs into `docs/archive/`.
- [ ] E3. `backend/godot` (103 MB) → git-lfs or release asset + history purge.
- [ ] E4. Remove the three kernel shims + `Reranker` alias after consumer
      migration window.

## Verification

- [x] `skeleton/testing/test_build_plan_smoke.py` — executable smoke tests
      for every surface landed this session: DRR fairness, deadline expiry,
      submitter caps, shim identity, FeatureReranker, pipeline stages,
      prefix byte-determinism, filler persistence, warmer refresh,
      idempotency replay (this commit).
- [ ] Run `pytest skeleton/testing/test_build_plan_smoke.py` in CI/local and
      confirm green; then `docker compose build backend` and confirm the
      `jeeves:system` prefix SHA is unchanged after the B5 flip.

## Completed cuts (ledger)

- ✅ kernel/fair_queue.py → shim over work_queue.py DRR lanes (fe5ec07)
- ✅ kernel/vclock.py → shim over clocks.py immutable impl (fe5ec07)
- ✅ services/cag.py dead route-import sever + prefix text single-sourced (c553ef8)
- ✅ retrieval twin Reranker → FeatureReranker rename + alias (bdca180b)
- ✅ genesis.py imports canonical clocks path (bdca180b)
- ✅ api/server.py + api/errors.py restored after bad rewrite (b4790a1)
- ✅ Track A (f6c7a78, 31c8541, e3eaeca, 3ebed65)
- ✅ Track B (51275cb, 324db3d, 7790918, 656406a, 48963bd)
- ✅ Track D1 audit closed (this commit)
