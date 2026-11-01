# Live pressure-bound fair planning

`LongContextLivePlanner` binds the existing durable fair-stream planner to
a freshly sampled `LongContextTelemetryFusion` observation. It never accepts
user-entered pressure flags. Only an exact, schema-checked, checksum-consistent
normal envelope can inform a proposal. Unknown sensors, unproven event
baselines, OOM/throttling and malformed/forged observations downgrade every
pressure signal to unknown, forcing the underlying planner to hold.

The adapter audits stream heads and tokenizer ancestry through the existing
planner. It verifies that a telemetry hold cannot be silently promoted by
a future planner regression. A valid proposal is still **not** a token lease,
hardware qualification, model permission or disk allocation authorization.
The live-plan digest is an unkeyed correlation checksum.

Operator command: `head-plan-live` accepts the same bounded stream candidates,
token budget, quantum and checkpoint limits as `head-plan`, but no pressure
override flags. It reads local pressure immediately before the proposal.
