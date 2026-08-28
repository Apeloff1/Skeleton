# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Generated 2026-08-28, anchored to the deep-cut ledger (fe5ec07, c553ef8, bdca180b).

## Correction log

- ca9238c mistakenly rewrote api/server.py + api/errors.py; restored (b4790a1).
  Rule: extend only, read before touching.
- B4 deploy constraint discovered via backend/Dockerfile: the production image
  copies only `backend/` into /app, so `import skeleton` fails there. All B4
  cutovers must be guarded shims (skeleton import → local fallback), never
  hard imports, until the image vendors the skeleton package.

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
- [x] B2. `skeleton/memory/prefix_renderer.py` — services/cag.py prefix engine
      ported as pure domain (51275cb).
- [x] B3. `skeleton/memory/warmer.py` — services/mag.py preemptive filler
      TTL/warmer ported as pure domain (51275cb).
- [x] B4a. `backend/services/cag.py` is now a guarded shim: re-exports
      `skeleton.memory.prefix_renderer` when importable, byte-identical local
      fallback otherwise (this commit). Verified both branches render the
      same prefix bytes (same constants + same builder logic).
- [ ] B4b. `backend/services/mag.py` cutover — BLOCKED: backend FillerStore
      takes a persistence Path (JSON disk store) which skeleton's FillerStore
      doesn't accept; port persistence into skeleton/memory/warmer.py first,
      then shim. Also blocked on image vendoring (see correction log).
- [ ] B4c. `services/memory_engine.py` collapses into a facade over
      PrefixRenderer + MemoryWarmer + trinity — after B4b.
- [ ] B5. Vendor `skeleton/` into the backend image (or set PYTHONPATH) so
      the guarded shims flip to canonical in prod; flip is a deploy change,
      not a code change.

## Track C — Retrieval rank plane — DONE (31c8541)

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
- ✅ Track A (f6c7a78, 31c8541, e3eaeca, 3ebed65)
- ✅ Track B1/B2/B3 memory semantics ported into skeleton/memory (51275cb)
- ✅ Track B4a services/cag.py guarded shim (this commit)
