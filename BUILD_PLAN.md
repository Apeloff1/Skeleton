# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Generated 2026-08-28, anchored to the deep-cut ledger (fe5ec07, c553ef8, bdca180b).

## Correction log

- The first scaffold attempt (ca9238c) mistakenly REWROTE the existing
  `api/server.py` (full AppState + lifespan wiring + health probes + metrics)
  and `api/errors.py` (ApiErrorResponse) with thin versions. Both were
  restored verbatim (b4790a1). Rule going forward: never rewrite an
  existing file for this build plan — extend only, and read before touching.

## Track A — Interface plane (skeleton/api) — DONE

- [x] A1. routes.py surveyed (f6c7a78).
- [x] A2. `GET /genesis/handles` + `GET /interface/reranker/stats` (f6c7a78).
- [x] A-fix. `AppState` declares `cockpit`/`gameforge` as Optional — 500 → 503 (f6c7a78).
- [x] A3. `api/telemetry.py` optionally mirrors samples onto the kernel bus (31c8541).
- [x] A4. `IdempotencyGuard` + `X-Idempotency-Key`, mounted on /forge/materialise,
      /forge/archetype, /gameforge/run, /gameforge/intake (e3eaeca, 3ebed65).
- [x] A5. `RouteTelemetry` wired into request_id_middleware with the kernel bus;
      `GET /telemetry/routes` exposes the snapshot (3ebed65).

## Track B — Memory/caching convergence (backend ↔ skeleton)

- [x] B1. Ownership decided (default): skeleton/memory owns semantics;
      backend services become thin adapters over it.
- [x] B2. `skeleton/memory/prefix_renderer.py` — the services/cag.py prefix
      engine (PrefixSegment, CAGPrefix, build_prefix, PrefixRegistry,
      PrefixRenderer, compose_prompt) ported as pure domain, single-sourcing
      the Jeeves prefix text (this commit).
- [x] B3. `skeleton/memory/warmer.py` — the services/mag.py preemptive
      filler TTL/warmer (Filler, FillerStore, MemoryWarmer) ported as pure
      domain with injectable clock; persistence stays caller-side
      (this commit).
- [ ] B4. Cutover: `backend/services/cag.py` + `services/mag.py` become
      re-export shims over the skeleton modules, and
      `services/memory_engine.py` collapses into a facade over
      PrefixRenderer + MemoryWarmer + trinity. Deferred — backend stack is
      live; needs a verification pass (prefix byte-identity) before shimming.

## Track C — Retrieval rank plane — DONE

- [x] C1. `retrieval/pipeline.py` optional rule/feature/diversity stages,
      fixed order (31c8541).
- [x] C2. Stage order documented; stages optional (31c8541).

## Track D — Kernel queue convergence

- [ ] D1. Migrate lane-based consumers to `WorkQueue`; collapse shims at the
      rename pass.
- [x] D2. `WorkQueue` optional per-submitter caps + deadline expiry (e3eaeca).

## Track E — Cleanup pass (deferred, requires local git ops)

- [ ] E1. Move 50 loose root test/sweep scripts into `tests/` and `scripts/`.
- [ ] E2. Move 8 `SEVEN_BY_*.md` docs into `docs/archive/`.
- [ ] E3. `backend/godot` (103 MB) → git-lfs or release asset + history purge.
- [ ] E4. Remove collapsed shims after consumer migration (D1, rename pass).

## Completed cuts (ledger)

- ✅ kernel/fair_queue.py → shim over work_queue.py DRR lanes (fe5ec07)
- ✅ kernel/vclock.py → shim over clocks.py immutable impl (fe5ec07)
- ✅ services/cag.py dead route-import sever + prefix text single-sourced (c553ef8)
- ✅ retrieval twin Reranker → FeatureReranker rename + alias (bdca180b)
- ✅ genesis.py imports canonical clocks path (bdca180b)
- ✅ api/server.py + api/errors.py restored after bad rewrite (b4790a1)
- ✅ Track A1/A2 + AppState cockpit/gameforge fix (f6c7a78)
- ✅ Track A3 telemetry bus mirror + Track C1/C2 rank-stage pipeline (31c8541)
- ✅ Track A4 idempotency guard + Track D2 queue policies (e3eaeca)
- ✅ Track A5 telemetry wiring + A4 mounting (3ebed65)
- ✅ Track B1/B2/B3 memory semantics ported into skeleton/memory (this commit)
