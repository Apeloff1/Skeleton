# Native admission lifecycle and replay custody

The registry now separately bounds simultaneous staged plaintext (256) and
process-lifetime request identities (10,000). Revocation and claim retain their
one-use tombstones; no eviction weakens replay. The durable journal remains the
authoritative replay fence across process restarts. Pressure guard lease history
uses the same 10,000 lifetime ceiling.

Before authenticated native admission, the app checks the journal and encrypted
result vault for known replay and remaining capacity, including existing queued
requests. The vault conservatively budgets its maximum possible output size for
each queued request. These checks do not replace transactional execution claims
and publication rechecks or reserve physical disk across processes.

Finite retention remains deliberate. Operator-authorized archival and rotation
with an independent anti-rollback anchor are required before the durable
journal/vault reach their limits. There is no automatic eviction or result loss.
