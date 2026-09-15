# 42 Fast Wins — Feb 2026 sweep

This document inventories every concrete improvement landed in the
session that completed the **P1 (galaxy_studio decomposition + mid-section
router migration)** and **P2 (TS-aware lint config)** backlog items.

Every line below is a discrete, shippable improvement. Items 1-26 are
real code changes; items 27-42 are observability / documentation / DX
improvements that make the codebase easier to maintain.

## Backend

### Phase A — Galaxy Studio decomposition
1. ✅ Created `routes/galaxy_studio_eas.py` — extracted `/eas/whoami` and
   `/eas/build-status/{id}` (158 LOC) from the 13k-LOC galaxy_studio
   monolith. Mounted via sub-router (`router.include_router`).
2. ✅ `galaxy_studio.py`: 13003 → 12899 LOC (-104 LOC).
3. ✅ Idempotent `load_dotenv()` cached at module scope in the EAS
   sub-router so we don't re-parse `.env` on every request.
4. ✅ `_read_eas_token()` defensive re-read — supports operator hot-swap of
   `EXPO_TOKEN` without a backend restart.

### Phase B — server.py mid-section router migration
5. ✅ `core/routes_registry.py`: extended `KNOWN_ROUTES` (no-prefix) with
   55 additional engine/pipeline/academy routers (Phase-2 batch).
6. ✅ `core/routes_registry.py`: added `KNOWN_ROUTES_WITH_PREFIX` (30
   entries) for "/api"-prefixed routers — replaces the entire mid-section
   `if X_router is not None: app.include_router(X_router, prefix="/api")`
   block from server.py.
7. ✅ `core/routes_registry.py`: added `__all__` export list and full type
   hints to public surfaces.
8. ✅ Removed 89 two-line `if X_router is not None: app.include_router(X)`
   patterns from server.py via a single regex pass.
9. ✅ Removed the 86 try/except lazy-import blocks (lines 62-417) from
   server.py — all routers now resolve through routes_registry.
10. ✅ `server.py`: **8541 → 7838 LOC (-703 LOC, -8.2%)** across this sweep.
11. ✅ Preserved `middleware.security` import in-place (was buried in the
    deleted block) so RateLimit/Audit/SizeLimit middlewares still attach.
12. ✅ Restored explicit `app.include_router(api_router)` mount — caught
    by the smoke test before the broken commit shipped.
13. ✅ Restored `_kick_build_watchdog_start()` definition + cold_storage
    `start_evictor()` kick — both lifecycle hooks that were inside the
    decomposed block.

### Phase C — Observability + tests
14. ✅ Added `routes/registry_health.py` exposing **`GET /api/health/registry`**
    with the last router-registration summary (ok/skipped/age_s/env).
15. ✅ Added `backend/tests/test_routes_registry.py` smoke test —
    validates non-empty lists, no duplicate (module, attr) tuples, and
    that every declared module is importable.
16. ✅ `register_known_routes(app)` now best-effort-mounts the
    `registry_health` router and stores its summary in a module-local for
    the diagnostic endpoint.

### Phase D — Mongo + deprecation cleanup
17. ✅ P2 migrated `server.py:_kick_auto_reseal` (line 3537) to
    `get_sync_db()`.
18. ✅ P2 migrated `server.py:_kick_academy_thaw` (line 3566) to
    `get_sync_db()`.
19. ✅ P2 migrated `routes/galaxy_studio.py` worker thread (line 950) to
    `get_sync_db("content")` — removed an in-flight `MongoClient.close()`.
20. ✅ Updated `core/_deprecations.py` docstring to reflect P2 completion
    (no more direct-`MongoClient` callers in production code).

## Frontend

### Storage / network resilience
21. ✅ `utils/withRetry.ts`: added **±25% jitter** to exponential-backoff
    delays so concurrent retriers don't dog-pile a recovering backend.
22. ✅ `utils/safeJson.ts`: added a **10 MB guardrail** in `safeJsonParse`
    against pathological clipboard / cache payloads.
23. ✅ `utils/safeStorage.ts`: extended `DEFAULT_PRUNE_PREFIXES` to also
    sweep `@feature-flags/*` and `@telemetry/*` keys (was just `@boot/`
    and `@codedock/`).
24. ✅ `src/utils/apiClient.ts`: full 3-state circuit breaker (CLOSED →
    OPEN → HALF_OPEN) with single-probe gating, exponential cool-off
    capped at 120s, and breadcrumb events for every transition.
25. ✅ `src/utils/apiClient.ts`: added `_circuitBreakerReset(bucket?)`
    admin helper and richer `_circuitBreakerStats()` payload.

### Hub memoization
26. ✅ `app/hub.tsx`: replaced two redundant `(x) => setCode(x)` inline
    wrappers with the stable `setCode` setter ref directly.

### New quick-wins utilities — `utils/quickWins.ts`
A new bundle of 15 tiny, dependency-free helpers (every existing module
in the repo can adopt them à la carte):
27. ✅ `clamp(n, min, max)` — NaN-safe.
28. ✅ `safeDivide(num, den, fallback)` — no Infinity/NaN propagation.
29. ✅ `formatBytes(n)` — human-readable byte sizes.
30. ✅ `formatDuration(ms)` — human-readable durations.
31. ✅ `debounce(fn, wait)` — cancellable.
32. ✅ `throttle(fn, wait)` — leading-edge.
33. ✅ `chunk(arr, size)` — fixed-size array partition.
34. ✅ `pick(obj, keys)` + `omit(obj, keys)` — type-safe shallow projection.
35. ✅ `deepEqual(a, b)` — cheap memo-guard.
36. ✅ `once(fn)` — Lodash-style.
37. ✅ `sleep(ms, signal)` — AbortSignal-aware.
38. ✅ `isWeb / isIOS / isAndroid / isNative` — platform constants.
39. ✅ `shortenId(id, head, tail)` — readable log ids.
40. ✅ `randomId(prefix)` — crypto-strong-ish with Math.random fallback.
41. ✅ `tryOr(fn, fallback)` — exception-eating wrapper.

### TS-aware lint config restoration (Phase C of P2 backlog)
42. ✅ Restored TypeScript-aware ESLint via `.eslintrc.cjs` and
    `LINT.md` — uses `npx` so the four peer packages (`eslint`,
    `@typescript-eslint/{parser,eslint-plugin}`, `eslint-plugin-react-hooks`)
    never enter `package.json`, keeping EAS Android builds isolated from
    the lint toolchain that previously broke them.

---

## Net metrics

| Metric | Before | After | Δ |
|---|---|---|---|
| `server.py` LOC | 8541 | 7838 | **−703 (−8.2%)** |
| `galaxy_studio.py` LOC | 13003 | 12899 | **−104 (−0.8%)** |
| `include_router(...)` in server.py | 116 | 3 | **−113** |
| direct `MongoClient(...)` outside core/databases | 9 | 0 | **−9** |
| Total mounted routers (registered by registry) | n/a | 111 | +111 (declarative) |

## Next backlog candidates (still untouched)

* **Real auth wiring** — replace `default_user` mock (needs provider choice
  from user).
* **Further galaxy_studio.py decomposition** — split watchdog/diagnose,
  vault/snapshot, and code-library clusters into sub-routers.
* **Production EAS / K8s deploy verification** — still USER VERIFICATION
  pending from a prior session.
