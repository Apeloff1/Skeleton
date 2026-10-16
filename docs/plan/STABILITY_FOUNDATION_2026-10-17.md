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
