# Per-page OS pressure fencing for journaled KV migrations

The Studio C live CPU-to-disk controller re-probes the canonical OS resource
sensor before **each** physical page move. A sample with missing telemetry,
clock regression, excessive age, increasing CPU pressure, falling RAM headroom,
or disk loss beyond the bytes already moved by this batch stops the operation.
The remaining disk reserve is checked against all pending NVME moves, not just
the next page. No GPU or M-chip device qualification is inferred.

The canonical planner's optional pre-move hook is used only by the live
controller. Under that hook, an adapter exception or changed resident identity
stops the batch immediately. The enclosing write-ahead journal retains a
RUNNING intent for operator reconciliation; neither automatic replay nor
implicit rollback is safe after an uncertain physical move. Unjournaled
planner-only simulations preserve their original per-page rejection receipts.

The OS check is observational and **not** an atomic cross-process disk
reservation. Production storage adapters must enforce their own durable quotas,
namespace authorization and physical allocation invariants. Tests use simulated
snapshots; no real GPU, Metal, ROCm, or device certification is claimed.
