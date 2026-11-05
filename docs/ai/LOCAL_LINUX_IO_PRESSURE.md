# Linux IO pressure feedback for offline inference

Linux cgroup-v2 `io.pressure` is preferred over host `/proc/pressure/io`.
Measured ten-second partial/full IO stalls are tagged with provenance;
malformed or unreadable scoped telemetry is unknown, not healthy zero.

Partial IO stalls above 30% or full stalls above 10% reduce local inference
concurrency. At 70% partial or 30% full stalls, background work pauses.
Existing operator ceilings, cancellation, fairness and hysteretic recovery
remain authoritative. No GPU/CPU performance claim is inferred from IO PSI.

Tests: `python -m pytest skeleton/testing/test_linux_io_pressure.py -q`.
