# App-owned guarded offline stream execution

The canonical app integration seam is
`skeleton.app.offline_dispatch_bridge.OfflineAdaptiveDispatchService`.
It composes the existing source-bound fair scheduler, SQLite custody,
independently trusted CAS anchor, canonical live pressure sampler and a
caller-owned authenticated model execution backend. The app must supply
already-authorized, securely opened storage and independent keys; this
module does **not** invent key custody, open arbitrary filesystem paths,
create an untrusted rollback anchor, or expose model prompts in status.

`submit` and `cancel` commit custody before returning. `execute_next`
samples live OS resources, creates at most one pending lease, rechecks
resource pressure immediately before dispatch, then calls the trusted
backend's `execute_and_commit`. Only a canonical execution-owner MAC
receipt can advance durable custody. A crash after backend work but before
acknowledgment leaves the lease pending and requires explicit reconciliation;
no restart may blindly execute it again.

`status` reports generation, pending lease count and quarantine state
without keys or prompt bytes. The execution result reports only source
identity and non-sensitive pressure metadata. A thermal/disk/unknown
sensor hold must not be converted into a success or a GPU qualification.
The current implementation is intentionally single-flight until
multi-lease atomic receipt and cross-process physical reservation contracts
are qualified. The deterministic tests simulate OS measurements and an
execution owner; they do not certify CPU/GPU/M-chip throughput, device
compatibility, physical memory coherence or release readiness.
