## Integration notes

The supervisor package is intentionally additive. Existing Night Shift and Idle Shift workers should consume orders through `PlanQueueAPI`; they should not request individual assignments from `SMBShiftManager` or `SecretaryBot`. `PlanReadAPI` remains the read-only inspection surface, while `WorkerControlAPI` is limited to clock/heartbeat state where direct status reporting is needed.

For large fleets, prefer the scheduled studios' aggregate workforce snapshots over per-worker supervisor traffic. Existing service/process management should own the scheduler process lifecycle.

Provider credentials remain runtime-only. Do not copy keys into code, plan items, logs, or model prompts.
