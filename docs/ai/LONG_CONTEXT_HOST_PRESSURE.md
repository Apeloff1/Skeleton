# Conservative host PSI observation for long-context planning

The `head-observe` operator command reports bounded CPU and memory PSI
observations on Linux, with explicit unknown thermal and energy signals.
It does not inspect or claim GPU, Metal, M-chip, or other device qualification.
No PSI reading authorizes inference, proves trusted telemetry, or permits
removal of the backend's live admission and pressure checks.

The observer reads only the literal `cpu` and `memory` files under
`/proc/pressure`, using descriptor-pinned, no-follow opens. It bounds input
to 4096 bytes, rejects malformed or duplicate PSI lines and nonfinite or
out-of-range percentages, checks named file identity before returning, and
rechecks the directory identity. Missing telemetry, path substitution,
unrecognized platforms, and parse failures return UNKNOWN rather than
assuming safe resources.

CPU avg10 >= 10% is elevated and >= 50% critical. Memory avg10 >= 5% is
elevated and >= 20% critical. These are conservative diagnostic thresholds,
not calibrated admission thresholds for a specific device or workload.
Thermal and energy remain unknown, so the complete observation still holds.
The CLI exposes no model prompts, tokens, weights, secret keys or filesystem
paths. `pressure_signals_attested`, `device_qualified`, and
`is_admission_grant` are always false.

Focused tests: `python -m unittest tests.flgb.test_long_context_host_pressure`.
Exact-head CI and security gates are still required before promotion.
