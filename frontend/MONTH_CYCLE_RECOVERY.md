# Month-cycle AI / game work: durability and recovery contract

This covers **client reconnection to already-authorized backend work** across
hours, days, weeks, and months. It is not a promise that a phone continues to
execute JavaScript when backgrounded, the process is killed, or the OS reboots.
It is also **not** a server scheduler, training pipeline, new checkpoint
format, self-renewing authorization mechanism, or a workaround for provider
limits.

## Authority boundaries

| State | Owner | May the client synthesize it? |
| --- | --- | --- |
| AI/game work execution | Governed backend worker | Never |
| AI weights/checkpoints, project and game files | Backend durable storage | Never |
| Canonical terminal job status | Backend status/operation replay API | Never |
| Conversation content and committed assets | Canonical backend conversation/project API | Never |
| Client's last verified cursor | Operation session cursor store | Only after native save/ack protocol |
| List of jobs to inspect on reconnect | MonthCycleLedger | Yes, as observation receipts only |
| Future retry eligibility | Local MonthCycleRecovery | Yes; does not affect server lease |

**Data minimization:** receipt fields are bounded opaque operation IDs, consumer
IDs, kind, client incarnation, cursor, observation revision, last-seen timestamp,
next check timestamp, failures and observed terminal state. No prompts,
credentials, weights, model content, conversations, or user assets are stored in
this registry. Use a per-account opaque namespace; do not use a raw token or
credential as the namespace.

## APIs and lifecycle

1. On authenticated job creation or whenever a previously known job is opened,
   call `createNativeMonthCycleLedger(accountNamespace)`. Use the same
   namespace on subsequent app launches for that account.
2. For game-studio jobs, call `registerStudioGoalCycle(ledger, goal, consumerId)`
   after the server has accepted the job. For canonical operation streams,
   `OperationBrowserSession.resumeDurable(ledger, signal)` registers before
   contacting the replay endpoint.
3. At foreground/restart/user-requested resume, run
   `new MonthCycleRecovery(ledger, studioGoalCycleWorker(), {...}).reconcileDue()`
   with a bounded batch/concurrency budget. Game builds can use
   `buildCycleWorker(fetchStatus)`, with an authenticated, read-only status
   provider supplied by the app.
4. Run a new foreground pass when appropriate, or surface jobs with
   `ledger.inspect()` and `ledger.due()`. The coordinator starts no
   unowned background timer. When killed, nothing runs until the OS restarts
   the application or an independent authorized backend scheduler exists.
5. On unmount/account switch, call `recovery.stop()`, and discard in-process
   objects, not server jobs. To remove a client recovery reminder explicitly,
   call `ledger.dismiss(receipt)`. Neither operation cancels the backend job.
6. A complete/failed/cancelled state is recorded only from a canonical
   backend status response. Studio "completed" without
   `completion.verified === true` remains observationally running, pending
   server-side proof.

The ledger uses two alternating checksummed AsyncStorage slots. Physical writes
are serialized for callers sharing the same native storage object inside one
JS runtime. It can recover from a corrupt/torn most-recent slot using the
previous valid slot, but this is not a cross-process atomic transaction and
does not cryptographically authenticate storage. When both slots are invalid,
read/write fails closed rather than dropping active jobs.

The registry stores at most 128 work receipts per namespace and rejects new
admissions when full; it does **not** silently evict active jobs. Terminal and
dismissed receipts may be pruned after 180 days. Active receipts have no
duration-based eviction. Next-check timestamps must remain within seven days
of the observation, so a repeated invocation can schedule months ahead in
bounded increments. Each foreground reconciliation handles at most 32 due
receipts using at most four concurrent reads. Fetch deadlines, signal
propagation, isolated subscriber exceptions and exponential backoff bound the
cost of a disconnected device.

## Simulation and observability

- `test-month-cycle-ledger.cjs`: alternating slots, corruption fallback,
  cross-account namespace isolation, 800-day active retention, concurrent
  writes, saturation and status revision fencing.
- `test-month-cycle-recovery.cjs`: week/month elapsed time, bounded retries,
  due batching, concurrency, clock injection, cancellation, stuck native
  transport and malformed worker callbacks.
- `test-month-cycle-integration.cjs`: canonical stream registration before
  replay, verified terminal states, game build and goal read-only adapters.

All three run in the **existing Merge Readiness job**, together with earlier
long-session test suites. Isolated TypeScript transpile/test simulation is not
native device certification.

## Requirements for real unattended month-long execution

The backend requires a separately verified **durable work queue**, worker
leases with fencing epochs, periodic state checkpointing and immutable
checkpoint provenance, retry budgets, restart recovery, storage quotas,
permission-renewal policies and explicit human reauthorization where required.
The current game-studio goal client contains short server-side step and
authorization bounds (including a 60-minute maximum renewal per request).
This frontend recovery system does not lift those backend limits or obtain
permission to operate indefinitely.

Before claiming the app supports real unattended months-long AI production,
run power-loss and server-restart tests against actual persistent backend
storage; verify authorization expiry and ownership, checkpoint restore and
long-form canonical continuity; and measure bounded disk usage, RSS, VRAM,
thermal throttling, clock changes and network outages over multi-day hardware
soaks. Do not use unverified local observation receipts to declare a project
or model artifact complete.
