# Recovered analytics and repair integrity

Canonical analytics now bounds direct inputs, deduplicates exact transport
retries, rejects conflicting event identity, partitions sessions by player
and session, namespaces anonymous counting units, and prevents session-local
timers leaking across separate sessions. Death-only cohorts now participate
in minimum-cohort filtering. Zero-cohort serialized cells cannot carry
nonzero observations; invalid counters, duplicate cells and invalid
confidence/rates are rejected. Existing per-cohort minimums do not establish
differential privacy or anonymity.

The B039 loop now detaches callback inputs, validates typed outcomes,
checks monotonic time after each synchronous callback, rejects late candidate
promotion and refuses proposal admission when the known route cost alone is
over budget. The budget remains cooperative: running callbacks cannot be
preempted or external provider spend undone. Provenance records retain
evaluated late attempts without promoting the resulting artifact. Focused
regression sources are registered; exact-head execution is pending.
