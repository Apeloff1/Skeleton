# Linux PSI pressure feedback

The existing offline inference owner samples the Linux kernel's 10-second
memory pressure stall information (PSI). The process's cgroup-v2
`memory.pressure` is preferred; `/proc/pressure/memory` is a measured fallback
only when the scoped interface is absent. Invalid or unreadable scoped PSI
remains unknown, never a fabricated zero.

Partial stalls above 15% or full stalls above 3% reduce local concurrency;
50% partial or 10% full stalls are critical and pause background admission.
Recovery requires low measured stalls and the existing hysteresis/cooldown.
These signals only tighten the operator's configured capacity. They do not
create a provider, a persistence authority, a new service, or GPU telemetry.

The feature is Linux-only. macOS and Windows retain their native probes and
explicitly unknown PSI fields. Deterministic tests are at
`skeleton/testing/test_linux_pressure.py`. Actual kernel/cgroup and
on-device saturation qualification remains separate from parser tests.
