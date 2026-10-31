# Monotonic energy admission hysteresis — Studio C

This dependent source component consumes the real energy admission plan and
prevents rapid background-worker oscillation when battery/thermal readings
fluctuate. It is an in-process controller, not a persistent scheduler or
hardware governor.

A critical or stale observation sheds workers immediately. Recovery requires
multiple healthy samples, a monotonic cooldown and a bounded upward step.
The controller never exceeds the measured CPU/memory/energy worker budget.
Clock regressions and malformed policies are rejected. Every decision has
a deterministic SHA-256 receipt bound to the source energy plan digest.

Canonical callers should instantiate one controller per actual local worker
pool, supply monotonic nanosecond timestamps, and enforce the returned limit
before starting more work. Cancellation and drainage remain the existing
runtime owner's responsibility. Restart starts with zero admitted workers
until fresh healthy observations establish a new safe limit; this module
does not pretend to restore live process workers or change system thermal
settings.

Focused canonical tests:

    python -m pytest -q --noconftest skeleton/testing/test_offline_energy_hysteresis.py

The operator-facing command supports sequential real observations with
--hysteresis-samples 2..32 and --hysteresis-interval-ms 0..1000. It emits
bounded per-sample receipts and the final admitted worker count; it never
starts workers or claims to alter physical device thermal controls.
