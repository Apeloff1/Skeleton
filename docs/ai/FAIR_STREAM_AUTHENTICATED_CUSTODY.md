# Authenticated fair-stream custody (integration candidate)

The canonical offline FairStreamScheduler produces deterministic admission
plans but its unkeyed SHA-256 checkpoint is not an authenticity guarantee.
This extension adds independent custody and execution HMAC keys, generation
fencing, copy-on-write state transitions and explicit lease reconciliation.

**Required integration sequence:** Load separate keys from canonical local
secret custody. Restore only when generation AND digest match the durable
high-watermark. Plan from freshly measured hardware budgets. Persist the
returned envelope with durable generation CAS BEFORE dispatch. The trusted
model execution owner signs an execution receipt ONLY AFTER durable result
commit. Reconcile the exact pending lease, then atomically persist the new
envelope before scheduling more work. After a crash, pending leases remain
fenced until authentic completion evidence is available.

This is an in-process library, NOT a durable transaction manager. Do not
expose it as production execution until the canonical durable store, CAS,
execution outbox, secret custody, and exact-head tests are integrated.
Neither test fixtures nor a signed digest qualify real GPU/Metal/ROCm devices.
