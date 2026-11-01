# Cgroup-v2 cumulative event deltas

`CgroupEventMonitor` samples bounded, descriptor-pinned `memory.events` and `cpu.stat` files. It detects increments in OOM, OOM-kill and CPU throttling counters. A first sample never produces a delta; a missing source, symlink, hardlink, inode swap, malformed record, counter regression, cgroup identity change, monotonic clock regression or expired interval resets the observation baseline.

The monitor is process-bound and guarded by a thread lock. It rejects inherited state after fork. It never persists or reuses stale event counters across restart. A zero delta is **not** evidence of safe CPU, RAM, thermal, energy or device operation. The sampled directory is not proof of process membership; no result is an execution lease or authorization. To use this in an actual execution controller, independently verify the process cgroup, live resource budgets, policy identity, and all required device telemetry. Never infer normal pressure from a single cumulative sample.

Focused regressions: `tests/flgb/test_long_context_cgroup_events.py`.
