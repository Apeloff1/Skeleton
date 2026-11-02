# Cooperative Linux RAM budget guard

`LongContextMemoryBudgetGuard` composes the read-only two-sample memory
envelope with an independently trusted principal verifier. This is a
**process-local reservation ledger**, not an allocator, backend authorization,
device certification, cross-process lock, or inference lease.

States: absent → reserved → claimed → released, expired or revoked. The
guard uses strict request types, a non-reentrant lock, a monotonic TTL,
fork rejection, per-principal and global byte limits, and cryptographically
random reservation identifiers. Each claim checks authorization again,
reobserves headroom for **all outstanding bytes**, and rejects stale or
forged non-authorizing telemetry. Sensor failures revoke the local ledger;
restart never recovers reservations as active. No principal identities or
raw model tokens are emitted in status.

The execution backend must still enforce authorization, CPU capacity,
GPU/Metal device policy, tokenizer/KV compatibility, durable disk quota,
thermal and energy pressure, and actual memory allocation. Kernel
headroom can change immediately after observation. The guard cannot
prevent another process from allocating RAM.

Focused tests:
`python -m unittest tests.flgb.test_long_context_memory_budget`
and `python -m unittest tests.flgb.test_long_context_memory_envelope`.
Exact-head CI and device qualification remain held.
