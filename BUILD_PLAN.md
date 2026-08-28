# Skeleton — Surrounding Systems Build Plan

Status legend: ✅ done · 🔨 scaffolded · ⬜ pending
Generated 2026-08-28, anchored to the deep-cut ledger (fe5ec07, c553ef8, bdca180b).

## Correction log

- ca9238c mistakenly rewrote api/server.py + api/errors.py; restored (b4790a1).
  Rule: extend only, read before touching.
- B4 deploy constraint discovered via backend/Dockerfile: the production image
  copies only `backend/` into /app, so `import skeleton` fails there. All B4
  cutovers are guarded shims (skeleton import → local fallback), never hard
  imports, until the image vendors the skeleton package.

## Track A — Interface plane (skeleton/api) — DONE (f6c7a78 → 3ebed65)

## Track B — Memory/caching convergence (backend ↔ skeleton)

- [x] B1. Ownership decided (default): skeleton/memory owns semantics;
      backend services become thin adapters over it.
- [x] B2. `skeleton/memory/prefix_renderer.py` — services/cag.py prefix engine
      ported as pure domain (51275cb).
- [x] B3. `skeleton/memory/warmer.py` — services/mag.py preemptive filler
      TTL/warmer ported as pure domain (51275cb).
- [x] B4a. `backend/services/cag.py` guarded shim over
      `skeleton.memory.prefix_renderer` (324db3d).
- [x] B4b. `skeleton/memory/warmer.py` FillerStore gained opt-in JSON
      persistence (`path=...`, atomic tmp+replace, byte-compatible with the
      legacy mag_fillers.json), and `backend/services/mag.py` is now a
      guarded shim over it (this commit). Module-level API (prime, stats,
      warm_now, register_default_fillers) preserved on both branches.
- [ ] B4c. `services/memory_engine.py` collapses into a facade over
      PrefixRenderer + MemoryWarmer + trinity — small; next session.
- [ ] B5. Vendor `skeleton/` into the backend image (or set PYTHONPATH) so
      the guarded shims flip to canonical in prod; deploy change, not code.

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
- ✅ Track B4a services/cag.py guarded shim (324db3d)
- ✅ Track B4b warmer persistence + services/mag.py guarded shim (this commit)
