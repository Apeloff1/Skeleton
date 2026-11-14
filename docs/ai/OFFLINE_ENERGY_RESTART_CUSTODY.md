# Offline energy restart and anti-thrash custody

The canonical energy CLI now imports and validates the real CpuWorkerPlan
type, repairing an execution-time NameError in energy worker admission.

EnergyHysteresis.checkpoint emits an integrity-only source-bound history.
restart_from_checkpoint verifies the exact pinned digest, schema, policy,
chronology and bounded state, then **restores zero worker grants**. Fresh
OS measurements and recovery hysteresis are required before new work.
A JSON hash cannot defend a coordinated rollback of the checkpoint and
its external digest, or attest to a rebooted monotonic clock epoch.

Invalid worker grants are rejected before consuming a monotonic tick.
The system does not change hardware power settings, certify GPU/Metal
execution, or reserve physical memory across processes.
