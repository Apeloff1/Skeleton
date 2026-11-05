# Persistence operational AI assurance module

## Purpose and trust boundary

This domain provides **twelve independent computations** over supplied numerical
observations. Each computation checks exact field membership, finite nonnegative
counters, a bounded result, and an input SHA-256. It never imports model text,
issues tool grants, invokes a provider, or declares a model qualified for release.

## Measurement inventory

| Contract | Meaning | Required counters |
|---|---|---|
| `audit_parity` | Independent audit coverage of authoritative commits | `audited_turns,committed_turns` |
| `receipt_replay_rate` | Durable replay usage | `replayed_receipts,receipt_requests` |
| `sqlite_conflicts` | SQLite compare-and-swap contention ratio | `sqlite_conflicts,total_transactions` |
| `outbox_backlog_ratio` | Unacknowledged event fraction | `pending_outbox,total_outbox` |
| `db_file_growth` | Observed persisted file growth | `database_bytes_now,database_bytes_before` |
| `checkpoint_age` | Age of last attested checkpoint | `now_ns,last_checkpoint_ns` |
| `orphan_fraction` | Requests without a live owner | `orphan_requests,all_requests` |
| `transaction_failure_ratio` | Failed transaction fraction | `rolled_back_transactions,attempted_transactions` |
| `restoration_integrity` | Revalidated state content fraction after restart | `matching_hashes,expected_hashes` |
| `wal_bytes_ratio` | WAL size relative to main database file | `wal_bytes,database_bytes` |
| `immutable_file_coverage` | Stored artifacts guarded against mutation | `immutable_files,recorded_files` |
| `revision_gap` | Unverified revisions in durable storage | `latest_revision,verified_revision` |

## Correct invocation and failure behavior

Import the named module from `skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence`
and call `measure()` with exactly the required numeric counters. An unexpected,
missing, nonfinite, Boolean, negative, or oversized value is rejected.

Counters need independent source custody: production deployments should derive
inputs from the authoritative SQLite spine, Linux kernel observations,
operator-authorized model metadata, or separately executed evaluation data.
These computations do not verify their own external inputs and are **not**
release evidence unless the input collection is independently attested.

## Regression guarantees

Each contract is covered by independent exact-oracle, deterministic fingerprint,
missing-field, unexpected-field, Boolean, negative, nonfinite, oversized,
zero-denominator and wrong-input-type regression tests. They are run only
after the implementation is complete. Never interpret a skipped real-model
test as a passing result.

## Integration

The domain registry exposes a closed set of names. The `measure()` function
can support a future readiness report but must remain observational. For
release admission, consult authoritative final-head workflow checks and
real checkpoint/hardware qualification rather than these scores.
