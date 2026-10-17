# Startup, storage and recovery qualification

**Owner:** frontend application shell and existing `frontend/utils` / `frontend/src/boot` modules.
**Scope:** stability changes in PR #4086. No new service, provider or state authority is introduced.

## Safety contract

1. **Boot is not a remote-readiness test.** Phase 0 proves local readiness. Unavailable backend services must remain visible as degraded optional phases and must not prevent a usable recovery screen.
2. **Crash-loop evidence is durable.** Safe Mode entry preserves the crash counter; only an acknowledged clean Product mount clears it.
3. **Caches are advisory.** A warm-boot cache cannot bypass the current process's critical local checks. Crash history becomes clean only after `/product` mounts.
4. **Storage is never assumed committed.** Timeouts, exceptions and conflicting in-flight writes are failures; timed-out native work remains guarded against later write reordering. Mirrors cannot certify durability.
5. **Preserve user state.** Automatic pruning is restricted to explicitly disposable telemetry; recovered sessions, projects, credentials, feature preferences and diagnostic evidence are not subject to blanket TTL deletion.
6. **Contain faults.** A caught screen exception offers Retry, Home and Safe Mode; it does not force a cross-screen navigation. Retrying is bounded, not recursive.
7. **Recovery is non-destructive by default.** Wipe All is exceptional, explicitly confirmed and never claims success when deletion fails. Reset Welcome and Try Product retain all unrelated data.
8. **Diagnostic recording is best effort.** A full/unavailable disk cannot block navigation. Trace payloads are bounded, redacted and serialized in an order that avoids older snapshots overwriting newer ones.
9. **Lifecycle ownership is explicit.** Network heartbeat and app-state listeners are cleaned up on root unmount; stale responses from suspended or prior sessions are discarded.

## Additional launch/retry invariants

- The Retry button never resets `@boot/crash_count`. Only a successfully mounted Product route acknowledges a clean boot.
- A retry increments an attempt generation **before** cancelling its prior runner. Late listeners, watchdogs, warm-cache reads and background telemetry from earlier generations must not commit state to the new attempt.
- The low-memory path defers self-cleaning until a confirmed Product mount, rather than running destructive or I/O-intensive maintenance before local readiness.
- Optional service and prewarm requests propagate their AbortSignal where supported, and report unavailable network services as degraded, never as passed checks.

## Cancellable stage runner invariants

- Boot cancellation remains terminal even in environments without a native
  `AbortController`: late completions cannot report success.
- Cancelling twice is idempotent, with pending/running stages recorded as
  `skipped` and the cancellation reason retained.
- Stage snapshots and dependency arrays are returned by value, preventing
  diagnostics subscribers from mutating the authoritative runner.
- The existing fast CI test gate exercises cancellation and snapshot isolation.

## Automated PR enforcement

The existing `Merge Readiness` workflow now executes all three recovery
regression suites when a pull request changes `frontend/`. It uses Node 24 and
a small isolated TypeScript test-compiler installation; it does not install
the entire Expo dependency tree or add a new always-on workflow.
An exact-head successful workflow log must contain the frontend test step.
The full frontend TypeScript compilation and native smoke tests remain
separate release requirements and must not be inferred from this lightweight
PR gate.

## Local acceptance

Run from the repository root:

```sh
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
cd frontend
yarn install --frozen-lockfile
yarn test:startup-recovery
yarn typecheck
yarn export:web
```

These are separate from the existing backend/installer checks and cannot be substituted by a successful Python-only workflow. Use a full frontend dependency installation in CI or on a development host. Do not report a test as passed until its exact-head run is observed.

## Manual fault-injection matrix

| Failure | Expected behavior |
| --- | --- |
| Offline backend / severed tunnel | Local shell or Safe Mode remains responsive, service state shows degraded |
| AsyncStorage read exception/hang | Entry does not remain indefinitely on spinner; safe fallback available |
| AsyncStorage write rejection or timeout | Mutation returns failure, stale mirror is discarded, later mutations cannot overtake pending native work |
| Corrupted launcher cache / future timestamp | Launcher starts from valid default layer |
| Corrupt trace JSON or circular diagnostic metadata | Recovery UI remains usable, diagnostic data is safely dropped/bounded |
| Critical local boot check fails | Launcher shows failure and Retry/Safe Mode; no fake success from watchdog |
| Noncritical stage throws synchronously | Stage records failed, dependents skip, all relevant phases terminate |
| Memory pressure during boot | Optional work can be shed; critical readiness is not bypassed |
| React screen throws repeatedly | Retry budget ends in an interactive fallback with safe navigation |
| Background during heartbeat request | Timer pauses; stale response must not create a false healthy status |
| Wipe All user cancels | No data changed |
| Wipe All deletion fails midway | Error shown, no success navigation, partial-deletion possibility disclosed |

## Release and rollback

- Verify that a storage wipe is refused while unresolved native writes remain. Repeat crash-recovery tests with telemetry service unavailable; screen recovery must remain interactive.
- Pin the exact PR head. Verify the frontend TypeScript check, the recovery test suite, web export and CI results for **that head**, not an earlier commit.
- On Android, reproduce cold start, force-close and three consecutive failed starts. Confirm a clean Product mount; confirm Safe Mode can be opened without data loss. Repeat offline and with low free disk space.
- Verify Docker-first-install separately using `python -m skeleton app doctor --live --studio --json`. This cannot be inferred from frontend checks.
- Do not delete Docker volumes or local projects as a routine repair.
- If regressions appear after promotion, roll back the PR merge using a dedicated revert (or release rollback) without touching durable volumes, and preserve crash traces for investigation.

**Not an acceptance receipt:** These steps describe required verification. No full native test, full TypeScript compile or production crash-free guarantee is implied by the existence of this document.
