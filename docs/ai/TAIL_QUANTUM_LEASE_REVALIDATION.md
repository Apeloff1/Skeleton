# In-flight CPU quantum lease revalidation

A generation returned by `admit_quantum` can now be rechecked through
`OfflineTailInFlightSession.validate_quantum_lease` before backend token
execution. The recheck enforces exact generation, bounded requested tokens,
the original monotonic deadline, and a fresh RAM/disk/CPU/thermal sample.

If pressure becomes unsafe, the entire quantum is revoked and the request
enters HOLD. An expired quantum becomes ABORTED and requires journal
reconciliation. Rechecking never extends the deadline, never allocates
physical memory and never qualifies GPU/M-chip/ROCm execution. Simulated
receipts continue to report `continue_execution=false`.

The trusted backend must call this method at the actual token dispatch
boundary and honor a false `continue_execution` immediately; an app receipt
is not a kernel-enforced cancellation mechanism.
