# Result-vault checkpoint tenant and memory binding

Before invoking an irreversible offline inference backend, the encrypted
result vault now independently validates the unique pending lease, the
matching request identity, exact tenant equality and integer-only per-token
memory accounting. This prevents a weaker backend adapter from accidentally
accepting a cross-tenant or boolean-aliased checkpoint. Invalid or duplicate
requests are rejected **before** plaintext generation.

The durable session and execution journal remain authoritative for checkpoint
MACs, monotonic CAS, replay fencing and authenticated result release. This
validation is defense-in-depth, not an independent user ACL. The app must
authenticate the caller and verify a committed journal receipt before any
read_committed operation. CPU-only execution remains unqualified for GPU,
Metal, ROCm and M-chip devices.

## Durable request-identity replay fence

The encrypted vault requires a verified, non-partial SQLite UNIQUE index
over `(session_id, request_id)`. Before CPU generation, it checks for an
already-published request even if a caller presents a different lease ID;
the same check repeats inside `BEGIN IMMEDIATE` before commit. A duplicate
request cannot re-execute merely by changing the lease identifier. A missing,
non-unique, partial or incorrectly shaped replay index fails closed on reopen.
Existing duplicate rows prevent index creation rather than being silently
deduplicated. This complements the journal's durable RUNNING state and the
independent session high-watermark.

The result-read regression fixture now supplies the tenant and per-token
memory bindings required by the production vault. Regression coverage includes
restart replay, distinct valid requests and tampered index rejection. No
hardware or release qualification is implied before exact-head validation.
