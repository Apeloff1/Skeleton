# Cooperative CPU token-quantum deadline

The canonical in-flight CPU resource guard now bounds the elapsed monotonic
time of an admitted token quantum, in addition to its token count, CPU load,
RAM, swap, disk and measured thermal checks.

- The default maximum is 5 seconds per quantum; policies may tighten it or
  extend it to at most 30 seconds. The clock is the operating system's
  monotonic nanosecond source. Injected clocks are allowed only in explicitly
  simulated tests.
- Admission records the monotonic start after a fresh OS resource probe.
  Checkpoint and status re-read the clock. A deadline breach, clock rollback,
  invalid clock value or clock failure permanently aborts the local guard,
  clears its token authorization and requires the execution owner's durable
  journal reconciliation. It never automatically replays model execution.
- A simulated decision cannot authorize real inference. The CPU backend must
  cooperate by checking the guard at quantum boundaries; this is **not**
  preemptive scheduling and cannot forcibly interrupt a hung native kernel.
  The outer process supervisor must independently enforce hard process and
  hardware quotas. No GPU, Metal or M-chip qualification is implied.
- No model text, tokenizer material, weights or keys enter deadline telemetry.

Focused deterministic regression coverage is in
`skeleton/testing/test_tail_inflight_guard.py`.

## Application lifecycle fencing

`OfflineTailInFlightSession` now treats a terminal CPU quantum deadline or
clock failure as a cross-component uncertain outcome. It marks the app session
quarantined and requires the independent execution journal to be reconciled
before further work. A failed first-token or checkpoint boundary cannot
silently publish a successful tail profile. Invalid requests that leave the
guard healthy still raise their original admission errors.
