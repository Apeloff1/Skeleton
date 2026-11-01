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

The `head-observe` command is side-effect-free and does not open or create a
spool root. Unsupported host telemetry is reported as unknown; no fallback
is promoted into an execution grant.

PSI reads now fence same-inode mutation with size, ownership, link count,
mtime and ctime checks, and reject hardlinked fixture files. A replaced
inode or in-place rewrite between descriptor stat, read, final stat and
pinned-directory name lookup invalidates the observation. Procfs may expose
synthetic zero file sizes, so file size is not treated as a read-length
assertion. These remain fail-closed diagnostics, not trusted sensor
attestation or complete protection from hostile same-UID filesystem actors.
