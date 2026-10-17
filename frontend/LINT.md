# Frontend lint and long-session stability

The canonical lint configuration is [eslint.config.js](eslint.config.js)
(ESLint 9 flat config, Expo). The frontend pins `eslint` and
`eslint-config-expo` in `package.json`; do **not** use unpinned
`npx -y` commands or a stale `.eslintrc.cjs` recipe.

From `frontend/`, with the project dependencies installed:

```sh
yarn lint:ci
yarn typecheck
yarn test:stability
yarn test:stability:reconciliation
```

The stability suite includes deterministic Node regression tests for boot
recovery, request retries, storage retention, thermal queue saturation and
liveness, battery listeners, recovery single-flight behavior, session progress
ordering/coalescing, storage hydration, authenticated request isolation,
bounded network responses, scoped health polling, push notification teardown,
and timer cleanup. It does not replace
on-device endurance, installed-app E2E, or native lifecycle testing.

## Incremental lint debt retirement

The broader app still has pre-existing React Hooks lint debt. We do not
turn every legacy violation into a build blocker or suppress every rule
globally without accounting for it. The battery, thermal, and recovery
modules now opt back into `react-hooks/exhaustive-deps` and
`@typescript-eslint/no-unused-vars`. Future migrations should expand
that list only after fixing the affected hooks and adding lifecycle
regressions. Do not disable `react-hooks/rules-of-hooks`.

## Operational invariants

- Native listeners acquired after an async initialization step must be
  cancelled if the component unmounted while awaiting the device.
- A React state updater cannot call another state setter.
- Device observations should not be fabricated or replaced when another
  sensor sends a partial update; unknown battery readings are ignored.
- Queued work must settle after synchronous callback failures, and
  cancelled delayed work must not execute side effects.
- Background throttling survives thermal recalculation and cooldown.
- Recovery runs are single-flight, bounded, and do not update unmounted UI.

For a release verdict, also run the complete app and backend checks,
first-install checks, and a real multi-hour device exercise. Passing lint,
unit tests, or TypeScript compilation alone does not prove long-session
stability.

## Focused pull-request gate

The existing `Merge Readiness` workflow runs
`node --test scripts/test-long-session-stability.cjs` with an isolated
TypeScript transpilation dependency. This adds no workflow and does not
require the full Expo install. It is a focused runtime contract regression,
not a substitute for `yarn typecheck`, `yarn lint:ci`, the installed
application, or endurance/pressure E2E.

## Marathon pressure regressions (network and thermal)

The existing fast Merge Readiness job additionally runs
`scripts/test-marathon-pressure.cjs` beside the lifecycle suite; no new
workflow is created. The pressure suite checks explicit read-only
coalescing, non-coalesced writes, cache memory admission, streaming response
budgets, request-format isolation, safe fallback behavior for requests
with custom headers, reset fencing, and thermal observer failure isolation.

These checks are deterministic simulations. Release qualification still
requires `yarn typecheck`, `yarn lint:ci`, a real native install and
sustained device monitoring. A response body adapter that exposes only
`.text()` cannot be prevented from buffering its full body internally;
it is rejected after materialization if oversized. Streaming adapters
enforce the limit before full buffering.

## Session-transition and background-load invariants

The same Merge Readiness job now also executes
`scripts/test-session-transition-pressure.cjs`. It covers end-during-start,
module switches that await previous final progress, concurrent latest-wins
switches, unmount fencing, singleflight reminder installation and retry after
scheduling failures, plus finite background timer policies.

The session API has no durable offline outbox. These checks prove ordered
in-memory behavior and explicit local degradation, not crash-safe delivery
of unsent progress across process termination.

## Transactional offline academy cache

`services/offlineCache.ts` now writes downloads in 100-document staging
pages with bounded response budgets. A single committed-generation receipt
becomes authoritative **only after** every expected page and metadata row
has been acknowledged by AsyncStorage. Truncation, malformed counts, native
write errors and aborts leave the prior generation readable. Incompatible or
oversized collections must use `getCachedCollectionPage`, rather than
materializing the entire collection in memory.

`scripts/test-offline-cache-integrity.cjs` runs in the existing fast-gate
Node test step. This tests atomic publication, legacy compatibility, complete
count checks, cancellation, storage failure and bounded paging. New sync
generations are not pruned out from under older readers; explicit clearing
removes all owned generations. Crash-surviving orphan staging will require an
independently reader-safe reclamation policy in a later pass.

## Memory pressure and durable operation monitoring

`memoryGuard` now owns an idempotent native memory-warning listener and
optional heap sampling timer, with explicit teardown and bounded synchronous
shedding callbacks. RootLayout registers disposal of only regenerable
network/thermal caches; active projects, model weights, and durable receipts
are never memory-purged.

`operationStreamSession` uses bounded idle polling backoff for multi-hour
tasks; thrown transport adapters become truthful error states instead of
unhandled promise rejections. Concurrent replay is single-flight, user-facing
observers are isolated, and cursor-save/clear operations remain physically
serialized to prevent a late native acknowledgement resurrecting erased
cursor state. Clearing the cursor does **not** cancel server-side operations.

`scripts/test-memory-pressure-runtime.cjs` and
`scripts/test-operation-stream-endurance.cjs` run inside the existing
Merge Readiness check beside the offline transactional suite. These
simulate OS warnings, clock rollback, failures, concurrent replays,
native save races, and low-cadence marathon operation following.

## Long-session preference, timer and build-observer hardening

`utils/usePersistentState.ts` now fences late hydration against user edits,
serializes writes by storage key across hook remounts and flushes unsaved
debounced edits on unmount. Oversized/unserializable preference payloads are
refused rather than poisoning previously stored preferences. This helper is
only for bounded UI settings, not canonical game/AI checkpoints.

`utils/safeTimers.ts` suspends intervals in background and rearms the same
owned interval on foreground without duplicates. Async callbacks cannot
overlap, rejected callbacks are contained, completed timeouts no longer
remain in the hook registry, and an install/uninstall path owns the native
listener. Native intervals are capped at 1000 live registrations.

`utils/useNetworkStatus.ts` runs no redundant heartbeat when native NetInfo
or web connectivity events are available. In fallback mode probes own a
deadline, are nonoverlapping, and ignore stale responses after backgrounding
or unmounting. This observes reachability, not authoritative game-job state.

`src/product/buildJobLifecycle.ts` can observe multi-hour builds without
an arbitrary default step count. An explicit maxChecks remains an optional
monitoring budget. Transient status transport failures retry a bounded number
of times and end as *disconnected*, **not** a backend build failure.
Backend reported failure, cancellation and completion remain separate.

The existing Merge Readiness job includes three new fault-injection suites:
`test-persistent-preferences-endurance.cjs`,
`test-build-observer-endurance.cjs`, and
`test-timer-resume-endurance.cjs`. No additional workflow is introduced.

## Shared native storage memory budget and reachability regression

`safeStorage` retains at most 1,048,576 UTF-16 characters in its fast-read
mirror and refuses individual values above 65,536 characters for mirroring;
those values still remain native-stored. Eviction, replacement, removal,
version rollover and global shedding keep accounting consistent. RootLayout
sheds the mirror on OS memory pressure, fencing stale native read results.

`scripts/test-native-mirror-memory.cjs` simulates oversized values,
thousands of keys, late reads, rollovers and memory pressure.
`scripts/test-connectivity-probe.cjs` tests stuck endpoint deadlines and
background/foreground cancellation. Both run inside the existing
Merge Readiness check and stability test command, not as new workflows.
