# Native CPU token-lease deadline custody

The canonical NativeTokenPressureGuard now bounds each native CPU lease by both token-probe count and a monotonic elapsed-time quantum. The default is 15 minutes; the explicitly configurable ceiling is 24 hours. The quantum applies to an execution lease, not a user file, model context or total project lifetime. Longer jobs require independently authorized, durably reconciled subsequent leases.

At the start of each authorized lease, the guard captures the monotonic clock. Before and after each live OS pressure probe, and before successful completion, it checks the clock. A deadline overrun, clock regression, invalid reading or unavailable clock permanently trips that guard instance. No implicit resume or retry occurs. The durable execution journal remains the authority for any outcome that may already have executed.

This is cooperative cancellation: the native runtime must invoke the interrupt callback at every token. It does not forcibly preempt a blocked native kernel, terminate a process or certify any GPU/M-chip device. An app that requires hard wall-clock termination must also own a separately isolated, killable worker process and durable result reconciliation. No result may be marked successful when the final monotonic deadline check fails.

Regression tests cover elapsed-time exhaustion before another token, slow OS probes, backward clocks, expiration at completion, missing clocks and invalid duration configuration. They use deterministic clock and OS-probe doubles and do not qualify physical devices.

### One-use native pressure lease custody

Each guard instance now burns a canonical typed CPU lease ID at admission, even
when generation later fails. Successful completion does not reset that identity.
A bounded 4096-entry lifetime replay fence prevents unbounded retention; a
capacity failure quarantines the guard instead of silently clearing history.
Callbacks are additionally bound to the exact in-memory execution epoch, so
stale callbacks cannot sample a later lease. This is defense in depth only:
SQLite journal and authenticated high-watermark remain authoritative across
process restarts, and none of these controls qualify GPU/M-chip execution.
