# Linux swap occupancy and fail-closed serving recovery

The local inference sampler now reports measured host swap totals/free bytes
or finite cgroup-v2 swap limits and usage. Disabled, missing, unreadable or
malformed swap metadata remains explicitly unknown. Occupancy is telemetry,
not by itself evidence of active thrashing; PSI memory/IO stalls govern
backpressure. No kernel swap limit or M-chip RAM setting is modified.

Serving recovery no longer treats a fully unknown resource sample as healthy.
Nonfinite or negative latency/queue samples are rejected before EWMA updates.
Tests: `python -m pytest skeleton/testing/test_linux_swap.py -q`.
