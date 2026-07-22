# CodeDock Maintainability & Stability Toolbox

This directory documents the **wraps, helpers, and CI scripts** that
were added in Feb 2026 to make CodeDock crash-resistant, fast on
physical Android, and easy to extend.

## ⚡ Stability wraps (frontend)

| Helper                                | Purpose                                                                                            |
| ------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `utils/bootTracer.ts`                 | Persists boot steps + crash counter to AsyncStorage. Drives `/safe-mode` recovery route.           |
| `utils/safeStorage.ts`                | `AsyncStorage` with hard timeouts + in-memory mirror (protects against OneUI encrypted-storage hang). |
| `utils/safeFetch.ts`                  | `fetch` with timeout, retries, JSON-safe envelope. Never throws.                                   |
| `utils/safeTimers.ts`                 | Tracked `setTimeout` / `setInterval` + AppState pause-on-background.                               |
| `utils/globalGuards.ts`               | RN `ErrorUtils` global handler + unhandledrejection listeners. Posts to `/api/telemetry/last-crash`. |
| `components/ErrorBoundary.tsx`        | Root error boundary in `_layout.tsx`.                                                              |
| `components/withScreenGuard.tsx`      | Per-screen error boundary HOC. Wired into `_layout.tsx` via `<ScreenGuard key={pathname}>`. Auto-includes `useRenderTrace`. |
| `components/SafeModalRoute.tsx`       | `makeModalRoute(Modal, name)` — converts any legacy modal to a guarded native route in one line. |

## ⚙ Performance wraps

`utils/perf.ts` exports:

- `useRenderTrace(name)` — logs slow renders (>300ms)
- `useDebounced(value, ms)` / `useThrottled(value, ms)`
- `useStableCallback(fn)` — stable refs for FlatList renderItem
- `useDeferredHeavy(fn, fallback)` — InteractionManager-deferred compute
- `memoCache<T>(ttlMs)` — TTL cache
- `FLATLIST_PERF_PROPS` — drop-in `<FlatList {...FLATLIST_PERF_PROPS}>`

## 🛠 Maintainability wraps

| Helper                          | Purpose                                                          |
| ------------------------------- | ---------------------------------------------------------------- |
| `utils/featureFlags.ts`         | Runtime AsyncStorage-backed toggles. `useFeatureFlag('foo')`.    |
| `utils/deprecation.tsx`         | `deprecated(Component, info)` HOC + `deprecatedFn(name, info)`.  |
| `utils/routeRegistry.ts`        | Single source of truth for all navigable routes (90 entries).    |

## 🔍 CI / dev scripts

| Script                                       | Purpose                                                                              |
| -------------------------------------------- | ------------------------------------------------------------------------------------ |
| `scripts/route_coverage_check.py`            | Verifies `routeRegistry.ts` ↔ `/app/*.tsx` consistency. Catches "Unmatched Route" regressions before merge. |
| `scripts/audit_modals.py`                    | Lists modal components by usage (orphan / route-only / actively used).               |
| `.pre-commit-config.yaml` (hook block)       | Runs route-coverage on every relevant commit.                                        |
| `.github/workflows/route-coverage.yml`       | CI Action: runs route coverage on PR; uploads JSON report as build artifact.         |

### Usage

```bash
# Static check (CI-friendly, exits non-zero on mismatch)
python3 /app/scripts/route_coverage_check.py

# Static + live probe of every route
python3 /app/scripts/route_coverage_check.py --live --base http://localhost:3000

# Machine-readable
python3 /app/scripts/route_coverage_check.py --json > report.json

# Find unused legacy modals
python3 /app/scripts/audit_modals.py
python3 /app/scripts/audit_modals.py --delete-orphans   # interactive
```

### Install pre-commit locally

```bash
cd /app
pip install pre-commit
pre-commit install
# now every `git commit` runs the route-coverage gate
```

## 🩺 Diagnostic screens

- `/safe-mode` — auto-shown after 2 crashes; displays boot trace + recovery buttons.
- `/telemetry`  — live dashboard for security/audit/modal events.
- `/audit-routes` — registry-vs-runtime probe; tap any route to navigate.

## 🆕 Adding a new modal → native route

1. Create `/app/frontend/app/<name>.tsx`:
   ```tsx
   import { FooModal } from '../features/Foo/FooModal';
   import { makeModalRoute } from '../components/SafeModalRoute';
   export default makeModalRoute(FooModal, 'FooRoute');
   ```
2. Add to `/app/frontend/utils/routeRegistry.ts` (chosen category).
3. Optionally add a menu card in `/app/frontend/app/menu.tsx`.
4. `python3 scripts/route_coverage_check.py` → green = ship it.
