# Durable swarm recovery composition

`SwarmDurableBridge` composes two existing recovery layers instead of replacing either one:

- `SwarmRecoveryManager` remains the canonical serializer for runtime and tenant recovery history. It owns bounded history, archive versioning, per-checkpoint checksums, the archive checksum, and restore behavior that requeues persisted leases.
- The durable checkpoint backend provides process-restart durability, worker lease fencing, outer-run checkpoints, and replay visibility for orchestration work after the latest durable boundary. `SQLiteRunStore` is the built-in tested implementation, but the bridge accepts any backend matching its narrow structural `DurableCheckpointStore` contract.

The bridge stores the recovery manager's exported archive verbatim as the durable checkpoint payload and records `RECOVERY_ARCHIVE_VERSION` as the durable checkpoint `state_version`. Restore requires the outer state version and embedded archive version to agree before the archive is handed back to `SwarmRecoveryManager.from_archive()` for checksum and structural validation.

## Capture flow

```python
from skeleton.agents.swarm_durable import SwarmDurableBridge
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmRuntime
from skeleton.state import SQLiteRunStore

store = SQLiteRunStore("var/runs.sqlite3", max_payload_bytes=8 * 1024 * 1024)
store.create_run("run-42", {"kind": "swarm"})
store.claim_run("run-42", "api-worker-3")

manager = SwarmRecoveryManager()
runtime = SwarmRuntime()
bridge = SwarmDurableBridge(store)

capture = bridge.capture(
    "run-42",
    "api-worker-3",
    manager,
    runtime,
)
```

`capture()` first creates the normal in-memory swarm checkpoint, then commits the manager's checksummed archive through the durable store. If the durable commit fails, the new swarm checkpoint and matching tenant checkpoint are discarded so the layers do not report different latest recovery points. Older retained swarm history is left untouched.

## Outer orchestration boundary

A swarm durable checkpoint can be attached to a completed outer run step with `after_step_id`. On recovery, `bridge.load()` returns both the verified swarm recovery manager and the generic `ResumeState`. The outer orchestrator can therefore restore the swarm control plane and separately reconcile any outer steps persisted after the swarm checkpoint.

This is intentionally different from treating swarm tasks as generic durable-store steps. Swarm task state remains owned by `SwarmRuntime`; generic steps represent orchestration-side effects and replay boundaries. Keeping those namespaces separate avoids two competing task state machines.

## Lease semantics

The durable store's worker lease protects writes to the outer run. Swarm worker leases are independent and remain owned by `SwarmRuntime`. A process that loses the outer durable lease cannot create a new durable swarm checkpoint. During restore, any swarm task that was persisted as leased is requeued by the existing hardened swarm recovery path rather than being trusted as still owned by a dead process.

## Archive size

`SwarmRecoveryManager` allows archives up to `MAX_RECOVERY_ARCHIVE_BYTES`, while `SQLiteRunStore` defaults to a smaller generic payload ceiling. Deployments that intend to persist large swarm recovery archives must configure the durable store's `max_payload_bytes` deliberately. A too-small durable limit fails the commit and `capture()` rolls back the newly-created in-memory checkpoint rather than truncating recovery state.

## Failure handling

The bridge fails closed when:

- the durable checkpoint `state_version` is not the supported swarm archive version;
- the embedded archive version disagrees with the durable envelope;
- the archive checksum or record checksums fail validation;
- the outer worker does not own a live durable lease;
- the durable payload exceeds the configured store limit.

Archive validation errors are normalized to `DurableSwarmError` at the bridge boundary while the original exception remains available as the Python exception cause for diagnostics.
