# Atomic cooperative memory fair cycles (Studio C)

The `LongContextMemoryBudgetGuard.reserve_fair_cycle` operation reserves
multiple distinct streams atomically **within one process**. Requests are
validated as a bounded tuple (1–64), ordered deterministically by stream,
verified against the caller-supplied principal verifier, and checked against
aggregate and per-principal RAM limits before any reservation is published.
The observer must return a structurally consistent, explicitly non-authorizing
RAM/cgroup envelope; unknown telemetry revokes all outstanding reservations.

Every reservation carries an independent random identity, a bounded monotonic
expiry, and a SHA-256 stream identifier in the receipt (no stream names, tokens,
model weights, or prompts). Entropy errors, duplicate IDs, slow telemetry,
clock regressions, quota exhaustion, duplicate streams, and closed/forked
instances fail closed without partially publishing a fair cycle. The guard
revalidates memory and principal identity when each reservation is claimed.

A fair cycle is **not** a model-execution grant, hardware qualification,
cross-process memory allocation, GPU/VRAM lease, durable reservation, or proof
that RAM remained free after observation. Backend execution must separately
validate model/tokenizer/KV identity, current pressure, actual allocations,
and cross-process constraints. Restart and fork invalidate all local claims.

The close/reserve/claim/release/status paths now check the closed flag under
the same mutex as publication. A fork PID check happens before waiting on a
potentially inherited lock. Focused regression coverage includes fair-cycle
atomicity, identity collision, slow observer, forged telemetry, expiry, and
close-vs-observer concurrency. Exact-head CI and device qualification remain
required before release.
