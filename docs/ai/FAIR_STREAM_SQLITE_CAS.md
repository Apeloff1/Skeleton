# Transactional offline fair-stream custody

The canonical `fair_stream_queue` planner remains the only scheduler.
`fair_stream_custody` authenticates its state and execution receipts.
`fair_stream_sqlite` supplies a transactional single-session CAS boundary
so a failed write does not mutate the in-memory planner or authorize dispatch.

## Integration contract

1. Open a trusted, private SQLite database through the app's secure bootstrap.
   The adapter accepts a connection rather than resolving user-supplied paths:
   the caller is responsible for symlink-resistant opening, restrictive file
   permissions, disk reserve, encryption-at-rest where required, and backup.
2. Retrieve custody and execution keys separately from local secret custody.
   Never put either key into the SQLite row, CLI output or a Git-tracked file.
3. Obtain the **independent** durable high-watermark (generation + digest)
   before `load` or `transition`. The SQLite row itself is not an anchor:
   an attacker can roll back the whole database, including its MAC.
4. On a new session, `initialize` once. For each command, use
   `transition(expected_generation=..., expected_digest=..., action=...)`.
   SQLite `BEGIN IMMEDIATE` serializes cooperating writers; the update is
   fenced on the exact previous generation and digest.
5. After COMMIT, advance the external high-watermark. Only then dispatch a
   newly planned lease after fresh measured resource probes. If a crash occurs
   between those steps, quarantine and reconcile; never infer permission to
   re-run a pending lease from the absence of an execution receipt.
6. Only the trusted execution owner may sign a result **after** its durable
   completion intent. `acknowledge` authenticates and binds the receipt.
   Unsigned, stale, duplicated, cross-session and wrong-key receipts fail.

This module is an integration candidate, not a secure database opener,
trusted execution engine, provider credential manager, GPU reservation, or
on-device hardware qualification. A full local app must supply independent
high-watermark custody and secure bootstrap before production dispatch.

Simulated canonical regression tests cover crash/restart, replay, CAS conflict,
receipt forgery, tampering and rollback detection. No device claims.
