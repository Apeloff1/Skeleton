# Native AI admission checkpoint recovery

Operator and contract supplement to [RUNTIME_CORE.md](RUNTIME_CORE.md).


## Canonical scheduler recovery and deployment pins

`restore_admission_scheduler(snapshot)` rejects type coercions, unknown or
missing fields, contradictory active/KV state, forward-dated sequences,
duplicate enqueue sequences, invalid token budgets, over-capacity entries,
noncanonical collection order and mismatched telemetry capacity. It does not
acquire external authority. Callers restoring persisted state should pass
`expected_policy`, `expected_limits`, `minimum_sequence` and
`expected_digest` read from **independent trusted** deployment metadata.
Sequence floors mitigate accidental stale-state rollback; a checksum alone does
not prevent replay or certify the checkpoint's publisher.

Retained KV identities are reserved while their cache entries exist. A new
request cannot silently reuse such an identity: explicitly evict/release
retained state before reusing it. Active records must retain identical KV
byte reservations and pinned flags, while queued requests never own KV entries.

`restore_admission_scheduler` currently caps retained KV checkpoint entries
at 65,536; productions expecting larger pools must set and validate an
architecture-governed bounded storage policy before changing that limit.

Focused suites:

```bash
python -m unittest tests.flgb.test_admission_checkpoint -v
python -m unittest tests.flgb.test_admission_checkpoint_strict -v
python -m unittest tests.flgb.test_runtime_admission_scheduler -v
```

Retries also enforce the bounded admission queue before modifying active
request state. A full queue makes `retry` fail atomically, keeping the
running request and resident KV available for explicit cancel, completion,
or a later retry after space becomes available. Constructor limits are typed.

## Deterministic admission state-machine stress tests

`tests/flgb/test_admission_checkpoint_state_machine.py` executes seeded,
interleaved submit, admit, retry, complete, cancel and KV pin transitions.
Every state is restored with trusted policy/limits/sequence pins; the test
requires exact checkpoint parity, bounded KV, queue and active occupancy,
atomic failed submissions/retries and equal traces for identical seeds.
The retained KV eviction scenarios exercise both pinned and unpinned state.
This is finite model-based randomized regression, **not** a claim of exhaustive
formal verification or production workload qualification.

```bash
python -m unittest tests.flgb.test_admission_checkpoint_state_machine -v
```

### Explicit retained KV release

`RuntimeAdmissionScheduler.release_retained_kv(request_id)` releases only an
inactive completed request's retained KV entry. It never releases active
decode state or queued ownership, and rejects missing identities without
mutating scheduler state. Pinned retained KV may be explicitly freed by a
authorized operator/control caller; callers must enforce tenant/request
authority upstream. The release increments the scheduler sequence and is
covered by checkpoint recovery tests, allowing deliberate later request-ID
reuse without evicting unrelated caches.

## Finite construction budgets

`AdmissionLimits` rejects runtime configurations beyond 4,096 active
requests, 65,536 queued requests, 4,096 requests per batch, 1,000,000 tokens
per batch, a 63-bit KV byte bound and a 1,000,000-point age boost. Checkpoint
restore uses the same `AdmissionLimits` constructor and cannot replay an
attacker-supplied vast quota merely by recomputing its SHA-256 checksum.

The public scheduler lifecycle methods also reject control characters,
invalid UTF-8 surrogate identities, unhashable inputs and oversized IDs
without changing queue, KV or sequence state.

The implementation remains an in-process deterministic scheduler, not a
multitenant allocator, cryptographic identity service or execution engine.

## Resident KV bookkeeping capacity

The scheduler and checkpoint loader share a 65,536-entry architecture limit
(`MAX_RESIDENT_KV_ENTRIES`). `admit()` defers requests when admitting would
exhaust the resident allocation-record budget, even if spare KV bytes remain.
A caller can release an inactive cached entry explicitly before retrying.
This avoids serializing an apparently valid live scheduler state that the
strict recovery parser would later reject on restart. The guard never frees
active, pinned or completed retained entries implicitly.
