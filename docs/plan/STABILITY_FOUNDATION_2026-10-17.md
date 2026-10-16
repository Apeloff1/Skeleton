# Stability foundation — crash-loop integrity and redundant startup

Date: 2026-10-17. Scope: the existing Expo application and its canonical launch path; no new capability owner, runtime root, database, provider, or supervising process.

## L00 — Intent and ownership
**Goal:** a native/JS restart, slow flash storage, offline server, visual skin change, or failed optional stage must not falsely claim a clean launch, endlessly escalate recovery, or destroy a healthy UI tree. The frontend owns screen recovery; `skeleton/app` continues to own application assembly and `backend` continues to own the API.

## L01 — Dependency map
Entry `frontend/app/index.tsx` → `bootTracer.bootGuard` → `LaunchCascade` → `BootLauncher` → local phase-0 checks → `/product`. Phase 1 server/network work remains optional. `/safe-mode` and static fallback layers are independent escape hatches.

## L02 — Compatibility
- Preserve legacy numeric `@launcher/attempt:v1` receipts.
- Use timestamped attempts for new fallback escalations. Expiration depends on the **attempt**, not an unrelated cached health score.
- Preserve `@boot/crash_count`, trace archive, manual safe-mode navigation, and the welcome flag.
- No external API, route, storage-key, provider, or network contract changes.

## L03 — Admission and authority
Only a completed **current-process** critical local stage can authorize the BootLauncher ready state. A warm health cache is advisory; memory pressure and a timer cannot claim critical readiness. `/product` acknowledges a clean boot after two committed animation frames, not when a launcher promises to navigate. Manual user navigation to recovery stays available.

## L04 — Runtime control flow
The launcher is no longer a timer-driven sequence through static screens; the static fallbacks remain on-screen until a human chooses. Layer-level error boundaries can still escalate. The BootLauncher watchdog moves to an independently usable static layer if checks stall.

## L05 — State semantics
Launcher recovery attempts are bounded 0–3 and expire after one hour based on their own timestamp. A legacy number is accepted unchanged until the next write. A persisted attempt is never upgraded to authoritative application health. Boot crash counters remain intact through boot, prewarm, retries, and memory pressure.

## L06 — Failure, resilience, recovery
| Injected failure | Intended behavior |
| --- | --- |
| Native AsyncStorage write fails or hangs | Critical physical persistence probe fails/times out; static recovery remains available |
| Backend unreachable | Product is still locally navigable; advisory health probe errors are caught |
| Warm boot cache reports success, new local storage fails | New phase-0 critical check wins over cache |
| Watchdog fires while checks stall | Escalate to static fallback, **not** a fabricated ready state |
| Memory warning during unfinished stage | Shed optional workloads; do not promote incomplete phase-0 |
| User reads fallback for more than 3.5 seconds | No timer-driven escalation to safe mode |
| Crash repeats before product paints | Crash count remains, allowing `bootGuard` to offer safe mode |
| User changes skin / persisted skin hydrates | Re-render palette without remounting all children |
| Unhandled advisory health request error | Caught locally, no unhandled promise rejection from first product render |

## L07 — Observability
Existing `bootTracer`, console trace, stage snapshots, boot telemetry and safe-mode archived session traces remain the evidence plane. Watchdog now emits `watchdog_fired` with `criticalOk` and `phase0Done` values, not `force_ready`.

## L08 — Capacity / performance
Avoid root subtree destruction during skin hydration and unneeded native-storage probes accumulating keys. Do not block product navigation on trace or welcome-flag persistence. Native memory/CPU profiling remains necessary; no frame-time or heap improvement is claimed without a device trace.

## L09 — Security and privacy
No external credentials or provider calls introduced. Startup receipts contain only numeric layer and timestamp. Neither cache nor timer can override critical startup evidence. Crash telemetry's existing redaction boundary is unchanged.

## L10 — Evaluation and test plan
New policy tests: `cd frontend && yarn test:stability`. Also run `yarn typecheck`, `yarn export:web`, `yarn test:product-journeys`, and the mandatory repository construction checks from `AGENTS.md`. These are **not** substitutes for actual native start/crash/restart tests.

Release blockers requiring device evidence:
1. Three consecutive forced terminations before product commit, then safe-mode recovery, then normal boot.
2. Broken/hung AsyncStorage, nearly full disk, and an offline API on Windows/web and Android.
3. Product route mount, switch skin, navigate back, verify no provider or route state loss.
4. Kill/restart during fallback layer persistence and validate receipt expiration/migration.
5. Validate Expo native build + Windows first-install launcher, real model-inference and state recovery separately.

## L11 — Deployment and rollback
The changes are compatible with legacy receipts. Rollback means revert this branch/PR; no schema migration required. Retain the safe-mode route and manual retry controls as reference paths. Do not claim release-ready before exact-head typecheck and native evidence.

## L12 — Operator controls
Expose manual retry, continue-anyway, safe mode and the existing boot log. None is removed. If the critical probe is unavailable, avoid silently clearing diagnostics; operators can still choose the product shell through the static fallback.

## Supplemental hardening — same source-compatible release slice
- `frontend/app/index.tsx` latches a single entry decision: a late native storage result cannot flip an already displayed cascade into Safe Mode.
- `frontend/components/NonCriticalHostBoundary.tsx` isolates each auxiliary host (network status, toast, action sheets and development overlay). An outer root error boundary catches provider failures independently of the route boundary.
- `frontend/utils/safeStorage.ts` treats timed-out writes, deletes and prunes as **unverified failures** rather than successful mutations. It does not cache fallback reads from an unresponsive native storage call. Crash counter and trace archive are exempt from cache pruning.
- `frontend/app/safe-mode.tsx` clears the in-process storage mirror after a raw storage wipe.
- The LaunchCascade no longer blocks initial hydration on durable diagnostic writes or silently renews the timestamp of an already persisted fallback just because the app restarted.
- All changes stay inside the declared frontend recovery owner and use the existing operator controls.

Additional regression cases needed at platform level: simulate failed `AsyncStorage.setItem`, delayed completion after timeout, a read timed out before underlying success, and auxiliary-host render exceptions. Verify storage rollback/read-after-write behavior and preserve the trace archive after seven days.

## L13 — Closure and residual risk
This slice closes source-level **false-readiness**, **fallback timer**, **skin remount**, and **physical probe** defects. It does **not** establish that the reported production/native crash is fixed. Unresolved: device crash logs, runtime resource exhaustion, API/process supervision, first-install recovery drills, full TypeScript build, and complete end-to-end application playthrough. These require exact-head checks and platform evidence before signing them closed.


## Second large stability batch — 2026-10-17

The existing owners were extended in place, with no new database authority or
background process. The additional code changes address the following failure
classes:

| Milestone | Code/evidence | Protection |
| --- | --- | --- |
| Retry policy | `frontend/utils/requestRecoveryPolicy.ts` | Finite retry/timeout/response budgets; no implicit replay of unkeyed POST/PUT/PATCH/DELETE |
| Full HTTP transport | `frontend/src/utils/apiClient.ts` | Capped attempts, deadlines spanning response bodies, no breaker poisoning by 4xx, no half-open lease on cache hit |
| Defensive HTTP transport | `frontend/utils/safeFetch.ts` | Abortable retry delay, cancellable caller signal, body-level timeout and bounded memory use |
| Crash telemetry | `frontend/utils/crashTelemetry.ts` + existing root/screen/global handlers | Burst budget, de-duplication, bounded concurrency and deadline without replays |
| Cold-start stage runner | `frontend/src/boot/runner.ts` | Synchronous stage failures yield terminal results; retry and backoff caps; child abort per timed-out attempt |
| Background observer ownership | `frontend/src/hooks/useTunnelStatus.ts`, `frontend/src/utils/tunnelHeartbeat.ts`, `frontend/app/_layout.tsx` | Single delayed startup, removable AppState listener, invalidated stale in-flight responses |
| Boot tracing | `frontend/utils/bootTracer.ts` | Coalesced writes/render notifications, serialized native writes, bounded recovery reads, previous-session rotation before writes |
| Offline Windows browser | `skeleton/app/windows_launcher.py` | Dead worker is reclaimed; shutdown is not invoked against an already-dead serving thread; browser failure does not kill active service |
| Service health | `skeleton/app/health.py` | Missing public probe is not a pass; invalid/non-finite retry/timeout budgets rejected |
| Failure injection | `skeleton/testing/test_app_stability_recovery.py` | Tests of dead worker, key removal, missing health contract, invalid polling inputs |
| Focused frontend policy tests | `frontend/scripts/test-request-recovery.mjs` and `test-startup-stability.mjs` | Legacy fallback compatibility, bounded retries, no implicit write duplication, transient HTTP classification, memory budgets |

**Compatibility and security:** This intentionally changes the historical
implicit retry behavior for unkeyed writes: a network fault now returns a
failure receipt rather than silently resubmitting a potentially already-committed
mutation. Keyed writes can still retry when the server supports idempotency keys;
client-side keys alone do not prove server deduplication. HTTP response budgets
default to 8 MiB and may be explicitly raised to at most 64 MiB for large
game-workspace requests. This is a bounded response safeguard, not a streaming
data plane; large assets still require streamed/chunked owners.

**Test evidence:** The original recovery policy and first request policy
regressions were executed together against SHA-matching local files and passed
9/9. The subsequently added response-budget test and Python failure-injection
suite require fresh exact-head execution. GitHub changed-file/secret/malware
checks are different from TypeScript/native runtime tests; they cannot qualify
the assembled product.

**Outstanding qualification:** `cd frontend && yarn typecheck && yarn
test:stability && yarn export:web`; Python stability/recovery tests; cold install;
Windows offline-browser service failure; low-storage/OOM Android startup;
device crash log capture; Docker service restart with backing-store outage;
full AI checkpoint inference and game playthrough. The PR remains a candidate,
not an attested crash-free release.

**Rollback:** Revert the stability PR; no persistent schema migration. Retain
safe mode, startup attempts, launcher controls and the canonical configuration
authority. The stricter request policy should be validated against every
mutating endpoint that expects a server-owned idempotency key.

## Best-practice review — recovery data integrity (2026-10-17)

This is a corrective review of the earlier stability changes, not an added
supervisor or independent runtime. Existing frontend ownership is retained.

- **No false acknowledgement:** `bootGuard` no longer clears the crash counter
  just for choosing Safe Mode. Manual navigation to Product and resetting the
  welcome preference likewise do not claim a successful boot. `markBootClean`
  remains the acknowledgement path after the Product route renders.
- **Bounded backpressure:** `LatestSnapshotWriter` permits at most one native
  trace write in flight plus one latest pending snapshot. Even an indefinitely
  hung AsyncStorage promise cannot build an unbounded chain of diagnostic
  writes. Best-effort trace persistence may lose intermediate breadcrumbs
  during an outage; the last memory snapshot and prior-session archive remain
  diagnostic fallbacks, not evidence of guaranteed durable writes.
- **Reset fencing:** startup-reset suspends trace writes, drops the pending
  snapshot, waits for the in-flight write with a bounded budget, and returns
  `false` rather than falsely claiming success if it cannot establish
  safe removal. A storage adapter that hangs or misorders native writes remains
  outside the JS-level guarantee.
- **Data-preserving recovery:** a non-destructive startup reset is offered
  before full wipe. The prior immediate wipe action now explicitly confirms
  irreversible deletion, disables concurrent actions and reports failures.
  Ordinary retry and welcome reset preserve projects and crash evidence.
- **Protected diagnostics:** trace labels are bounded and redacted before
  logging; unserializable metadata cannot break crash logging. Safe Mode
  diagnostic reads run independently of optional feature flag hydration, and
  async rejections are handled during unmount.
- **Executable evidence:** the committed `test:stability` task now includes
  four trace-writer fault-injection tests alongside the original ten pure
  policy tests. All **14/14 passed locally** on Node 22.16 with source files
  byte-identical to the Git blob hashes. This is focused policy/queue evidence
  only—not proof that React Native, Windows, native storage, or the production
  game studio have passed installation or end-to-end testing.

Release blockers remain: exact-head TypeScript compilation, Expo export,
Native Android restart/OOM/low-storage, full Python recovery tests, Windows
first-install, and complete AI/game-playthrough operation. Do not merge based
solely on focused tests, source completeness or mergeability.


## SOTA reliability audit — durable state and failure amplification

This is a **corrective P0 risk-reduction pass**, not an attested production
release. Its acceptance model is no acknowledged authoritative-state loss,
correct failure classification, bounded auxiliary resource use, zero hidden
mutation replay, and a recovery UI that works when optional systems fail.

### Highest-severity defects corrected

1. **Severe data retention fault (P0):** Generic `safeStorage.pruneExpired`
   previously admitted the broad `@codedock/`, `@boot/`, `@feature-flags/`
   and `@telemetry/` namespaces for automatic seven-day removal. Keys under
   these families can represent projects, preferences, settings, and crash
   evidence. `storageRetentionPolicy.ts` now explicitly admits only the
   advisory `@boot/last_ok:v1` key and `@telemetry/cache/` derived rows.
   Caller-supplied prefixes cannot expand that admission. Background full
   key scans are opt-in, and old metadata records for disallowed keys cannot
   trigger deletion. The mirror/epoch book-keeping is bounded and stale
   native read results cannot overwrite newer in-process state.
2. **Competing write authority:** Opportunistic `selfCleaner.ts` no longer
   truncates and rewrites `@boot/trace` behind the dedicated boot-tracer
   writer. It also no longer deletes arbitrary entries from Expo's shared
   cache directory when total size exceeds a threshold. It only considers
   named, regenerable Skeleton scratch entries, and skips directories.
3. **Timed-out reset / late write races:** `resetBootState` keeps the trace
   writer fenced if the underlying native removal is unresolved. A timeout
   is not proof that a native mutation was cancelled. Diagnostic session
   rotation now uses bounded reads, so a hung native adapter cannot block
   every later boot trace flush.
4. **Duplicate-write admission:** Automatic write replay now requires both
   a stable idempotency key *and* explicit verification that the particular
   server endpoint implements deduplication; a client header alone is
   insufficient. Safe reads retain bounded retries.
5. **Crash and API failure amplification:** A telemetry operation retains
   its concurrency slot until the native fetch actually settles, even if
   AbortController is ignored. The primary API transport has abortable
   retry sleeps and excludes raw URLs, query strings and untrusted transport
   exception text from breadcrumbs and fallback errors. The secondary
   transport resolves caller cancellation promptly without waiting for a
   misbehaving native adapter's timeout.

### Verified in this pass

- **18/18 deterministic Node tests passed** (startup receipts, bounded write
  queue and reset fence, retry/idempotency/response budgets, storage deletion
  allowlist). Tests were executed on Node 22.16 with `--experimental-strip-types`.
  The seven tested source/test files each matched their actual Git blob hash.
- The three pure TypeScript policy/queue modules passed a separate strict
  `tsc --noEmit` check with ES2022/ESNext settings.
- No new top-level runtime service, provider boundary, persistent database or
  CI workflow was introduced.

### Non-compensable remaining release qualifications

- Exact-head full `frontend` TypeScript build, Metro/Expo native bundle and
  browser export (a pure-module strict compile is **not** this).
- Real Android cold-start, repeated force-stop, memory pressure/OOM, offline,
  locked/slow storage, interrupted update, corrupt cache and rotation of
  inactive/foreground states.
- Windows frozen installer: first install, dead serving thread, port reuse,
  native model checkpoint inference, and bounded shutdown under failure.
- Docker backing-store outage, health and recovery transitions, durable
  database snapshots, restore/reconciliation, and unacknowledged write replay.
- End-to-end creator project persistence, scene saves, checkpoint restoration,
  Jeeves runtime, and full game playthrough with model access.
- Failure-injection tests for slow/late native storage writes and app-authored
  state authority migrations, and release rollback on a real installed build.

**Residual semantic risk:** A JavaScript timeout cannot cancel all underlying
native writes; physical persistence sequencing for authoritative user records
requires a server/SQLite transaction or explicit native acknowledgement,
rather than optimistic AsyncStorage mirrors. React error boundaries do not
catch kernel/OS OOM kills or all native exceptions. Large response caps on
React Native adapters that only provide `response.text()` are best effort
after buffering; asset streaming needs a dedicated production data path.
These limitations are release blockers, not claims of solved behavior.

**Operational rollback:** Keep PR #4085 isolated until exact-head
qualification. Revert the PR for any durable-state regression; preserve
database, model and project state. Do not clear user state to pass health
checks or mark a boot clean before a user-visible product render. Keep the
minimal existing security/hygiene checks; do not reintroduce redundant CI
workflows merely to increase the reported number of passing checks.
