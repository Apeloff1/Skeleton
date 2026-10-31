# Durable offline execution-intent journal

`FairStreamExecutionJournal` and `JournaledExecutionOwner` are an
app-owned implementation of the canonical `DurableExecutionOwner` seam.
The app provides a **separate** securely opened SQLite connection, the
execution HMAC key, and a trusted backend implementing
`run_and_commit(permit, checkpoint) -> (consumed_tokens, result_digest)`.
The backend must durably publish the actual result **before** returning.

A single-use lease moves from absent -> RUNNING -> COMMITTED. RUNNING is
committed to disk **before** invoking any backend. Backend exceptions, crash
gaps, and incomplete commits leave RUNNING in place; the lease is never
automatically retried. COMMITTED contains a canonical HMAC-authenticated
receipt and can be read through `recover_committed_receipt` only for explicit
external reconciliation. Reading it does not execute a model or acknowledge
the canonical scheduler. The operator must first verify the custody session,
independent trusted high-watermark, and durable result publication.

The journal stores only IDs, generation, checkpoint digest, consumed token
count, result digest and signed receipt. No prompt, output, model weight,
provider credential or secret key is persisted. Row capacity is bounded and
SQLite main-database page capacity must be configured separately via the
private SQLite opener. A journal file alone is **not** a monotonic anchor;
a database rollback or same-UID attacker remains outside its security claim.

This is CPU-only admission/receipt custody, not a GPU allocator or device
qualification. Tests use synthetic backends, crash simulation, forged
receipts and deterministic restart scenarios.
