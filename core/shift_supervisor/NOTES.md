## Integration notes

The supervisor package is intentionally additive. Existing Night Shift and Idle Shift workers should call `WorkerControlAPI` for clock/heartbeat state and `PlanReadAPI` for their queue. Existing service/process management should own the scheduler process lifecycle.

Provider credentials remain runtime-only. Do not copy keys into code, plan items, logs, or model prompts.
