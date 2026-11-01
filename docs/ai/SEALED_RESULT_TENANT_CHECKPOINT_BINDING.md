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
