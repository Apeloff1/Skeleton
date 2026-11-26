# Guarded offline fair-stream execution boundary

`GuardedFairStreamDispatch` binds the existing canonical SQLite CAS,
independent trusted high-watermark, fair scheduler and live OS resource sampler
to an execution-owner protocol. The application must provide a trusted
`DurableExecutionOwner.execute_and_commit` implementation backed by its
already-authorized local native/provider engine. The owner MUST enforce real
backend memory quotas and cancellation, commit the output durably, and only
then return the canonical signed execution receipt. This adapter never loads
weights, signs results, invents GPU measurements or claims hardware qualification.

`plan_live` calls the canonical live sampler itself, constrains each round to
one pending lease (until atomic multi-receipt generation fencing exists), and
persists the plan through SQLite and the independent high-watermark before
issuing a permit. `execute_once` validates the exact pending lease and its
generation/digest, re-probes the selected storage volume and RAM/thermal/pressure
budget immediately before calling the trusted owner, and acknowledges only the
authenticated receipt. Backend failure, invalid receipt or ambiguous commit
quarantines execution; the pending lease must be reconciled by the trusted
execution owner, not retried or silently cancelled. A pressure denial does not
execute the backend and may be reconsidered after a new measurement.

**Security boundaries:** A caller-constructed `MeasuredStreamBudget` with
`measurement="os_probe"` is not proof of actual OS telemetry; dispatch must
use the canonical sampler path. The Python process, injected sampler and
execution-owner implementation must be trusted. This does not create a
cross-process physical reservation, immutable shared pages, trusted key vault,
independent anti-rollback anchor, GPU transfer, or Apple Silicon qualification.
SQLite connection custody, external CAS/key lifecycle and crash-consistent
result publication remain explicit requirements of the host application.
The deterministic tests use simulated OS samples and a simulated execution
owner and do **not** certify a real device or release.
