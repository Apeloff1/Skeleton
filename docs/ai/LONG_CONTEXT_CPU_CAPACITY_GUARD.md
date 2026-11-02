# Cooperative CPU capacity guard

The runtime exports CpuCapacityRequest, CpuCapacityLimits and
LongContextCpuCapacityGuard through the canonical model-runtime package.

The guard reserves bounded *in-process* CPU token and disk-request budgets,
never backend execution authority. It requires an independent application
principal verifier, generation-fenced durable stream observations, a verified
tokenizer digest, available observed spool capacity, and repeated normal
telemetry. It rechecks telemetry, authority and window identity before claim.

The state machine is absent -> reserved -> claimed -> released. Pressure,
expiry, clock regression, fork and close revoke or invalidate reservations.
No reservation is persisted or restored after a crash. An inherited lock is
never acquired after fork. Client-visible digests do not attest sensor
authenticity. This component does not qualify GPU, Metal, VRAM, disk
publication or cross-process scheduling.

The backend must independently revalidate authorization, pressure, stream
CAS and durable consumption before executing or advancing a token window.
This guard cannot be used as an interprocess lock or release certificate.

Focused regression: python -m unittest tests.flgb.test_long_context_cpu_guard
Follow with canonical spool/progress/telemetry suites and exact-head CI.

## All-or-nothing fair cycles

reserve_fair_cycle accepts a tuple of independent stream requests and a
bounded quantum. It verifies every principal, head observation and aggregate
spool capacity before publishing any in-process reservation. A single stale
head, duplicate stream, insufficient token/byte budget, oversized quantum,
or unverified disk observation rejects the entire cycle without reserving
capacity for early streams. Each stream receives at most one quantum.
This is fairness within a single cooperative cycle only; the backend must
still enforce cross-process coordination and independent execution authority.
