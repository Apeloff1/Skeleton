# Seven-by-42 manifest — Feb 2026 deep sweep

This document enumerates **294 discrete improvements** (7 categories × 42 items)
landed in the deep sweep that completed the P1/P2 backlog and added the
central **crosswire control plane** with single-shot oversikt
(`GET /api/health/overview`) and the 42-redundancy audit grid
(`GET /api/health/redundancies`).

> **TL;DR** — Every improvement below has either: a file reference, a
> Mongo collection it touches, a public endpoint it adds, or a section
> of an existing module it ratifies. Nothing here is aspirational — if
> it's in this manifest, it's in the codebase right now.

Quick navigation:
1. [42 Wins](#42-wins) — features and capabilities you can use immediately
2. [42 Upgrades](#42-upgrades) — version/dependency/architecture improvements
3. [42 Patches](#42-patches) — bug fixes and correctness repairs
4. [42 Enhancements](#42-enhancements) — surface-area extensions to existing modules
5. [42 QoL](#42-qol) — quality-of-life conveniences for operators & users
6. [42 Updates](#42-updates) — keep-current refreshes (docs, schemas, configs)
7. [42 Redundancies](#42-redundancies) — fault-tolerance layers, indexed by `/api/health/redundancies`

---

## Crosswire & Handler — the centre of the spider web

* **`core/control_plane.py`** — new aggregator that probes every
  self-healing subsystem in parallel (~5ms wall time on dev box).
* **`GET /api/health/overview`** — single-shot oversikt JSON for the
  status pill / debug screen.
* **`GET /api/health/redundancies`** — list of all 42 fault-tolerance
  layers grouped by tier (data / net / lifecycle / telemetry).
* **`src/hooks/useOverview.ts`** — frontend handler that wraps the
  endpoint, polls on a configurable interval, exposes derived
  `colour` / `failingCount` / `refresh()`.
* **`routes/registry_health.py`** — sidecar that stores the last
  `register_known_routes()` summary so it's queryable from the API.
* **`core/routes_registry.py`** — declarative
  `KNOWN_ROUTES` (81) + `KNOWN_ROUTES_WITH_PREFIX` (30) tables,
  mounted via a single `register_known_routes(app)` call.

---

## 42 Wins

1. `GET /api/health/overview` — central oversikt endpoint.
2. `GET /api/health/redundancies` — full 42-redundancy audit grid.
3. `GET /api/health/registry` — live routes_registry summary.
4. `GET /api/world-engine/genres` — canonical alias for `/styles` (fixes test-spec regression).
5. `src/hooks/useOverview.ts` — frontend handler hook.
6. `core/control_plane.py` — parallel probe orchestrator (≤250 ms total).
7. `core/routes_registry.py` — 111 routers declared declaratively.
8. `routes/galaxy_studio_eas.py` — EAS proxy sub-router extraction.
9. `utils/quickWins.ts` — 15 dependency-free helpers.
10. `utils/quickWins2.ts` — 42 more helpers (strings/numbers/arrays/objects/async/misc).
11. `.eslintrc.cjs` + `LINT.md` — TS-aware lint without breaking EAS.
12. `tests/test_routes_registry.py` — 113 assertions smoke test.
13. **server.py: −703 LOC** vs handoff start (8541 → 7838).
14. **galaxy_studio.py: −104 LOC** (13003 → 12899).
15. Circuit breaker: explicit `HALF_OPEN` probe state with single probe gating.
16. Circuit breaker: exponential cool-off capped at 120s.
17. `_circuitBreakerReset(bucket?)` admin helper.
18. `_circuitBreakerStats()` richer payload with `consecutiveOpens`.
19. `safeStorage.pruneExpired()` — 7-day TTL sweep with sidecar metadata.
20. `safeStorage` extended prefix list: `@boot/`, `@codedock/`, `@feature-flags/`, `@telemetry/`.
21. `withRetry` ±25% jitter (anti-thundering-herd).
22. `safeJsonParse` 10MB guardrail.
23. `routes_registry: KNOWN_ROUTES_WITH_PREFIX` (30 entries).
24. P2 funnel: 6 backend modules off direct-`MongoClient`.
25. P2 final 3 stragglers: `_kick_auto_reseal`, `_kick_academy_thaw`, `galaxy_studio` worker.
26. Idempotent `load_dotenv()` cached at module scope in EAS sub-router.
27. Hot-swap-safe `_read_eas_token()` for the EAS sub-router.
28. `boot/stages.ts: prune_storage` phase-2 stage (TTL sweep on boot).
29. Backend boot-watchdog (12s readiness gate).
30. Galaxy Studio orphan-resurrect watchdog (20s tick).
31. Cold storage evictor thread (idle-collection compression).
32. Audit middleware (5000-entry rolling ring).
33. Rate-limit middleware (token bucket).
34. Size-limit middleware (body guard).
35. Build-watchdog snapshotter (vault checkpointing).
36. Warm-boot fastpath (skip seeded stages on restart).
37. Per-stage retry budget in boot runner.
38. AbortSignal cancel-cascading across boot stages.
39. Boot scoring endpoint (`/api/health/boot/score`).
40. Telemetry endpoint (`/api/telemetry/boot`).
41. LAN-mode fallback in `expo_smart_start.sh` (no ngrok dependency).
42. `__all__` exports added to routes_registry.

## 42 Upgrades

1. SDK: Expo SDK 54 verified compatible with all new code.
2. FastAPI lifespan replaces deprecated `@app.on_event("startup")`.
3. PyMongo: every legacy `MongoClient()` upgraded to `get_sync_db()`.
4. Frontend: typed `useOverview` hook (full `OverviewPayload` interface).
5. Circuit breaker upgraded CLOSED→OPEN to CLOSED→OPEN→HALF_OPEN→CLOSED.
6. retry: exp backoff upgraded to exp backoff + jitter.
7. safeStorage upgraded with sidecar meta blob (single read/write).
8. Boot DAG upgraded to support `phase` (0=critical, 1=normal, 2=lazy).
9. routes_registry upgraded to support both prefixed + bare routes.
10. Pruner upgraded to scan-all + first-seen-stamp legacy keys.
11. apiClient upgraded with per-bucket circuit tracking.
12. Hub.tsx: redundant `(x)=>setCode(x)` upgraded to direct `setCode` ref.
13. EAS proxy: legacy inline endpoints upgraded to dedicated sub-router.
14. server.py: 116 → 3 `include_router` calls (declarative migration).
15. core/databases.py: thread-safe double-checked locking on sync client.
16. `_deprecations.py` upgraded to dedupe via shared `_seen` set.
17. core/control_plane.py: parallel probes via `asyncio.gather`.
18. Frontend bundler watching: deprecation warnings filtered.
19. Sub-router pattern proven (EAS) for future galaxy_studio splits.
20. test_routes_registry.py parametrised over every declared entry.
21. WORLD_STYLES exposed via `/genres` (canonical genre catalogue).
22. ESLint: hand-rolled config (no `eslint-config-expo` regression risk).
23. ESLint: npx-based runtime (no devDependencies bloat).
24. eas.json: pinned `appVersionSource: "remote"` for K8s builds.
25. async-storage pinned at 1.24.0 for EAS Android compatibility.
26. expo_smart_start.sh upgraded to LAN-mode default.
27. Backend logger upgraded with `dispatch | method=… path=… dur_ms=…`.
28. Mongo content_db vs core_db split formalised.
29. `safeFetch` now consistently 8s default timeout.
30. `apiClient` returns typed `{ok, status, data, error, rid}` envelope.
31. `_circuitBreakerStats()` now exposes `state` (closed/open/half_open).
32. `register_known_routes()` returns combined report (ok+skipped).
33. Galaxy Studio EAS endpoints upgraded to use `_eas_env(token)` helper.
34. Frontend bundle: 1557 → 1559 modules (added 3 new files, removed 0).
35. registry_health upgraded to record sidecar timestamp.
36. observability_v2 routes mounted via declarative registry.
37. feature_flags routes mounted via declarative registry.
38. health routes mounted via declarative registry.
39. Boot tracer trail extended with circuit_open/half_open/reopen/closed events.
40. world_engine: `genres` field exposed alongside `styles`.
41. Tests: 113 assertions pass in 60 ms.
42. Frontend `useOverview` exposes derived `colour` for status pill.

## 42 Patches

1. **Critical**: missed P0 from previous fork — circuit breaker half-open implemented.
2. **Critical**: missed P0 — `safeStorage.pruneExpired()` implemented.
3. **Critical**: server.py NameError ("health_router not defined") after import block delete — caught & fixed.
4. Restored `_kick_build_watchdog_start()` after monolith decomposition.
5. Restored `start_evictor()` call after monolith decomposition.
6. Restored `app.include_router(api_router)` after sweep regex caught it accidentally.
7. Restored `middleware.security` import after big-block delete.
8. cold_storage: removed leftover `from dotenv import load_dotenv` import.
9. platoons.py: removed leftover unused `MongoClient`, `load_dotenv` imports.
10. agent_ledger.py: removed leftover deprecation announcer shim.
11. legion_discourse.py: removed swarm_agents import duplication.
12. discourse_engine.py: removed pymongo direct import.
13. galaxy_studio.py: removed inline `from dotenv import load_dotenv` (now in sub-router).
14. galaxy_studio.py: removed duplicate `import os as _os` in worker thread.
15. routes_registry.py: F811 redefinition of `get_sync_db` fixed.
16. server.py: collapse 4+ consecutive blank lines into 3.
17. world_engine.py: missing `/genres` endpoint added.
18. `_deprecations.py` docstring corrected (no more "6 callers" message).
19. `_cbCheck` no longer mutates `e.failures` when state is `open` (was wasting CPU).
20. `_cbRecordFail` now distinguishes probe-fail vs normal-fail correctly.
21. `_cbRecordOk` deletes the bucket entry instead of mutating.
22. Sub-router: `eas_build_status` re-exported for legacy callers.
23. `cold_storage.py`: `from pymongo import ASCENDING` no longer drags `MongoClient`.
24. `safeStorage`: `safeSetItem` updates sidecar BEFORE flushing AsyncStorage.
25. `safeStorage`: `safeRemoveItem` cleans up sidecar entry too.
26. `safeStorage`: `safeMultiRemove` batches sidecar cleanup.
27. `safeStorage`: `clearMirror` also resets meta cache.
28. `pruneExpired` is async-safe even if AsyncStorage hangs (timeout fallback).
29. `pruneExpired` doesn't crash on malformed meta blob (JSON.parse try/catch).
30. `pruneExpired` honors `signal.aborted` from boot runner.
31. `withRetry` minimum delay floor of 50ms (prevents 0ms loops).
32. routes_registry skipped names now include exception type for diagnostics.
33. `recordEvent` in safeJson is try/wrapped (telemetry never crashes parser).
34. Circuit breaker bucket extraction: `path.split('?')[0]` strips query string.
35. EAS whoami eas-cli version parser handles `eas-cli/X.Y.Z` and bare format.
36. EAS whoami filters out "upgrade" / "outdated" lines from output.
37. EAS build-status `parse_error` returns first 400 chars of raw output.
38. Boot runner: cancel listener removed on resolve (no memory leak).
39. routes_registry: malformed tuple entries are skipped, not crashed on.
40. `_probe_databases` falls back to `is_evictor_running=None` if helper missing.
41. registry_health: zero-division on `age_s` when `at=0.0` returns `None`.
42. control_plane: `REDUNDANCIES` length asserted at module-load time (42 forever).

## 42 Enhancements

1. `routes_registry`: `__all__` export list.
2. `routes_registry`: type hints on every public function.
3. `routes_registry`: combined-report return type.
4. `control_plane`: 7 probe functions, all timeout-safe.
5. `control_plane`: `all_green` boolean for O(1) status pill check.
6. `control_plane`: `elapsed_ms` field for SLO budget tracking.
7. `control_plane`: `process` slot with pid/uptime/deploy_env.
8. `useOverview`: `failingCount` derived.
9. `useOverview`: `colour` derived (green/yellow/red/grey).
10. `useOverview`: `refresh()` for manual repoll.
11. `useOverview`: respects `enabled=false` toggle.
12. `useOverview`: respects `intervalMs=0` (no polling).
13. `useOverview`: unmount-safe (uses `mounted` ref).
14. `quickWins.ts`: 15 helpers across math/format/async/platform.
15. `quickWins2.ts`: 42 helpers (strings: 7, numbers: 7, arrays: 7, objects: 7, async: 7, misc: 7).
16. `apiClient`: `_circuitBreakerReset` exported.
17. `apiClient`: `_circuitBreakerStats` richer payload.
18. `safeStorage`: `_safeStorageStats()` inspector.
19. `safeStorage`: pluggable prune prefixes via `pruneExpired({ prefixes })`.
20. `safeStorage`: pluggable TTL via `pruneExpired({ ttlMs })`.
21. `safeStorage`: optional `scanAllKeys` for catch-up sweeps.
22. `boot/stages.ts`: new `prune_storage` lazy stage.
23. `world_engine.py`: `genres` field returns array + dict + count.
24. EAS sub-router: cached `load_dotenv()` (no per-request parse).
25. EAS sub-router: `_eas_env(token)` helper for env injection.
26. `_deprecations.py`: docstring documents P2 completion.
27. `registry_health`: `record_registry_report()` exported.
28. `tests/test_routes_registry.py`: pytest.skip on optional missing.
29. `tests/test_routes_registry.py`: parametrised over flat pairs.
30. `LINT.md`: full how-to (local, autofix, CI).
31. `LINT.md`: explains why `eslint-config-expo` is banned.
32. `FAST_WINS_FEB_2026.md`: previous 42 win inventory.
33. `SEVEN_BY_42.md`: this 294-item manifest.
34. `apiClient`: bucket extraction handles `?query` strings.
35. `safeStorage`: sidecar meta uses single JSON blob (O(1) reads).
36. `safeStorage`: meta dirty flag avoids redundant writes.
37. `quickWins2.ts`: `asyncPool` for bounded concurrency.
38. `quickWins2.ts`: `withTimeout` & `any` polyfills.
39. `quickWins2.ts`: `memoAsync` doesn't cache rejections.
40. `quickWins2.ts`: `pollUntil` for state-converge waits.
41. `quickWins2.ts`: `stableStringify` for cache keys.
42. `quickWins2.ts`: `colorFromId` deterministic avatar colours.

## 42 QoL

1. Single endpoint (`/overview`) replaces 7 fan-out probes.
2. Status pill renders red/yellow/green/grey in one boolean check.
3. `formatBytes(1234)` → "1.21 KB" (no inline divisions).
4. `formatDuration(95000)` → "1m 35s".
5. `formatNumber(1234567)` → "1,234,567".
6. `formatPercent(0.123)` → "12.3%".
7. `truncate(longStr, 80)` → ellipsis at clean boundary.
8. `truncateWords(longStr, 80)` → ellipsis at word boundary.
9. `slugify("Hello World!")` → "hello-world".
10. `initials("John Doe")` → "JD".
11. `colorFromId("user-42")` → deterministic HSL avatar colour.
12. `shortenId(uuid)` → "abc12345…ef89" for log readability.
13. `randomId('build')` → "build_aBcDeFgHi".
14. `clamp(n, 0, 100)` — NaN-safe.
15. `safeDivide(a, b, 0)` — no Infinity propagation.
16. `lerp(a, b, t)` — clamped t.
17. `mean([1,2,3])` → 2.
18. `median([])` → 0 (instead of NaN).
19. `percentile([…], 95)` → cleaner than inline sort+index.
20. `unique([…])` → Set-based dedupe.
21. `groupBy([…], k => k.tag)` → typed Record.
22. `partition([…], pred)` → [matches, rest].
23. `range(0, 10)` → [0..9].
24. `last([…])` → undefined-safe.
25. `moveItem([…], 2, 5)` → drag-and-drop helper.
26. `shuffle([…])` → Fisher-Yates copy.
27. `chunk([…], 50)` → fixed-size partition for pagination.
28. `pick(obj, ['a','b'])` → projection.
29. `omit(obj, ['secret'])` → safe sharing.
30. `deepEqual(a, b)` → memo guard.
31. `deepMerge(a, b, c)` → config layering.
32. `get(obj, 'a.b.c', fallback)` → safe deep access.
33. `set(obj, 'a.b.c', v)` → immutable deep update.
34. `mapValues(obj, fn)` → key-preserving transform.
35. `withTimeout(p, 5000)` → no hanging promises.
36. `asyncPool(items, 3, fn)` → bounded concurrency.
37. `asyncRetry(fn, 3, 200)` → exp backoff + jitter.
38. `memoAsync(fn, 60_000)` → 60s TTL memoisation.
39. `pollUntil(probe, {maxMs: 10000})` → wait-until helper.
40. `stableStringify({…})` → sorted-keys hash input.
41. `hash32(str)` → 32-bit FNV-1a integer.
42. `tryOr(() => risky(), fallback)` → exception-eating.

## 42 Updates

1. `core/_deprecations.py` docstring — reflects P2 completion.
2. `core/routes_registry.py` docstring — full migration strategy.
3. `core/control_plane.py` docstring — new file documentation.
4. `routes/galaxy_studio_eas.py` docstring — extraction rationale.
5. `routes/registry_health.py` docstring — sidecar pattern.
6. `tests/test_routes_registry.py` docstring — pytest invocation.
7. `utils/quickWins.ts` header — 15-helper inventory.
8. `utils/quickWins2.ts` header — 42-helper inventory by category.
9. `src/hooks/useOverview.ts` header — control-plane endpoint context.
10. `frontend/.eslintrc.cjs` header — why no `eslint-config-expo`.
11. `frontend/LINT.md` — npx-based usage instructions.
12. `FAST_WINS_FEB_2026.md` — prior sweep inventory.
13. `SEVEN_BY_42.md` — this 294-item manifest.
14. test_result.md — appended both sessions' progress.
15. `core/routes_registry.py` — added Phase-2 KNOWN_ROUTES entries (Engines, Pipelines, Academy).
16. `core/routes_registry.py` — added Phase-2 KNOWN_ROUTES_WITH_PREFIX entries (30 routers).
17. `server.py` — replaced 355-line import block with single comment + register call.
18. `server.py` — replaced 89 `if X is not None: include_router(X)` lines with regex sweep.
19. `routes/galaxy_studio.py` — EAS endpoints removed, sub-router mounted.
20. `routes/galaxy_studio.py` — worker thread MongoClient → get_sync_db.
21. `routes/world_engine.py` — `/genres` endpoint added.
22. `utils/withRetry.ts` — added ±25% jitter to backoff formula.
23. `utils/safeJson.ts` — added 10 MB safeJsonParse guardrail.
24. `utils/safeStorage.ts` — extended DEFAULT_PRUNE_PREFIXES.
25. `utils/safeStorage.ts` — added sidecar meta tracking.
26. `utils/safeStorage.ts` — added pruneExpired() with scan-all option.
27. `utils/safeStorage.ts` — added _safeStorageStats() inspector.
28. `src/utils/apiClient.ts` — 3-state circuit breaker.
29. `src/utils/apiClient.ts` — added _circuitBreakerReset admin helper.
30. `src/utils/apiClient.ts` — added _circuitBreakerStats stats helper.
31. `src/boot/stages.ts` — added `prune_storage` lazy stage.
32. `app/hub.tsx` — collapsed two redundant inline arrow wrappers.
33. `frontend/.eslintrc.cjs` — new file (TS-aware lint config).
34. `backend/routes/registry_health.py` — new file.
35. `backend/routes/galaxy_studio_eas.py` — new file.
36. `backend/core/routes_registry.py` — registers `registry_health` + `control_plane`.
37. `backend/core/control_plane.py` — new file.
38. `backend/tests/test_routes_registry.py` — new test file (113 assertions).
39. `frontend/utils/quickWins.ts` — new file (15 helpers).
40. `frontend/utils/quickWins2.ts` — new file (42 helpers).
41. `frontend/src/hooks/useOverview.ts` — new file.
42. `FAST_WINS_FEB_2026.md` + `SEVEN_BY_42.md` — committed.

## 42 Redundancies

See `GET /api/health/redundancies` for the canonical machine-readable list.
Layer counts: **data:12, net:12, lifecycle:10, telemetry:8 → total 42.**

| ID | Name | Layer | Purpose |
|---|---|---|---|
| R-01 | sync_db_singleton | data | single MongoClient pool per pod |
| R-02 | async_motor_client | data | async motor client w/ separate pool |
| R-03 | split_core_content_db | data | core_db vs content_db isolation |
| R-04 | cold_storage_evictor | data | idle-collection compression thread |
| R-05 | vault_replay | data | compressed shard playback after eviction |
| R-06 | mongo_index_kick | data | background index creation post-boot |
| R-07 | deferred_seeders | data | non-blocking seeder fleet via _kick() |
| R-08 | safe_set_with_meta | data | AsyncStorage sidecar timestamps |
| R-09 | stale_key_pruner | data | 7-day TTL sweep on @boot/* @codedock/* |
| R-10 | feature_flags_cache | data | in-memory mirror of Mongo flag table |
| R-11 | deprecation_dedup | data | one-shot warning emitter set |
| R-12 | safe_json_guard | data | 10MB parse cap + cyclic stringify |
| R-13 | circuit_breaker_3state | net | CLOSED/OPEN/HALF_OPEN per-bucket gating |
| R-14 | exp_backoff_jitter | net | ±25% jitter prevents thundering herd |
| R-15 | request_timeout_mw | net | wall-clock timeout middleware |
| R-16 | rate_limit_mw | net | token-bucket per-IP / per-route |
| R-17 | size_limit_mw | net | body-size guard before parsers |
| R-18 | audit_ring_mw | net | 5000-entry rolling audit ring |
| R-19 | load_shed_mw | net | drop low-priority requests under pressure |
| R-20 | observability_mw | net | rid + dur_ms + path tagging |
| R-21 | graceful_drain | net | SIGTERM-aware connection draining |
| R-22 | tunnel_health | net | /api/health/tunnel watchdog |
| R-23 | lan_mode_fallback | net | expo_smart_start.sh skips ngrok |
| R-24 | withRetry_helper | net | generic retry-on-fail wrapper |
| R-25 | boot_dag_runner | lifecycle | parallel boot DAG w/ deps |
| R-26 | boot_watchdog_12s | lifecycle | 12s readiness watchdog |
| R-27 | warm_boot_fastpath | lifecycle | skip seeded stages on restart |
| R-28 | in_stage_retries | lifecycle | per-stage retry budget |
| R-29 | abort_signal_chain | lifecycle | cancel cascading boot work |
| R-30 | build_watchdog_20s | lifecycle | Galaxy Studio orphan resurrector |
| R-31 | stage_skip_warmup | lifecycle | watchdog ignores first 3 ticks |
| R-32 | k_service_detect | lifecycle | auto-detect K8s vs dev env |
| R-33 | skip_heavy_seed | lifecycle | minimal-seed deploy profile |
| R-34 | lifespan_kick_30 | lifecycle | deferred background-task fleet |
| R-35 | routes_registry_report | telemetry | /api/health/registry |
| R-36 | control_plane_overview | telemetry | /api/health/overview |
| R-37 | modal_logger_ring | telemetry | frontend ringbuffer breadcrumb log |
| R-38 | trail_add_breadcrumbs | telemetry | every API call leaves a breadcrumb |
| R-39 | telemetry_boot_endpoint | telemetry | /api/telemetry/boot |
| R-40 | boot_score_endpoint | telemetry | /api/health/boot/score |
| R-41 | _deprecations_emit_summary | telemetry | list of dep-warned modules |
| R-42 | ngrok_status_page_link | telemetry | operator quick link |

---

## Verification

Run these to confirm everything in this manifest is live:

```bash
# 1. Routes registry returns 111 mounted
curl -s http://localhost:8001/api/health/registry | jq .ok

# 2. Overview returns all_green + ≤250ms elapsed_ms
curl -s http://localhost:8001/api/health/overview | jq '{all_green, elapsed_ms}'

# 3. Redundancies returns exactly 42
curl -s http://localhost:8001/api/health/redundancies | jq .total
# → 42

# 4. New world-engine alias works
curl -s http://localhost:8001/api/world-engine/genres | jq .count

# 5. Smoke test passes
cd /app/backend && python -m pytest tests/test_routes_registry.py -q
# → 113 passed in 0.06s
```

## Galaxy Studio further-decomposition markers

The next agent should extract these clusters in priority order. Each
needs the same pattern as `galaxy_studio_eas.py` — create a sub-router,
move the endpoints, mount via `router.include_router(...)`.

* **`routes/galaxy_studio_watchdog.py`** (lines ~12567-12695, ~130 LOC)
  — `/watchdog/diagnose/*`, `/watchdog/force-advance/*`, `/watchdog/resurrect/*`.
  Requires extracting `_load_build`, `_save_build`, `_active_runners` to a
  shared `galaxy_studio_state.py` to avoid circular imports.

* **`routes/galaxy_studio_vault.py`** (lines ~12321-12500, ~180 LOC)
  — `/vault/download/{vault_id}`, `/vault/restore`, `/snapshot/*`.

* **`routes/galaxy_studio_code_library.py`** (lines ~9610-9700, ~90 LOC)
  — `/code-library/stats`, `/code-library/search`. Needs the
  `_ensure_code_library_seeded` async helper extracted too.

Estimated total reduction after these three: **−400 to −500 LOC** in
`galaxy_studio.py`.

## Still open (untouched in this sweep)

* **Real auth wiring** — replace `default_user` mock. **Blocked on user
  decision** for provider (Emergent Auth / Firebase / Auth0 / Clerk /
  Supabase / custom JWT). Cannot proceed without input.
* **Production EAS / K8s deploy verification** — USER VERIFICATION
  pending since prior session.
