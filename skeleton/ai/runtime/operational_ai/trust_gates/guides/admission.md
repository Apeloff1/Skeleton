# admission — AI runtime assurance

This boundary strictly validates a bounded source record before it can inform
AI runtime admission. Its verifier is executable, not a documentation-only policy.

## Input keys

- `tenant` — `text` (exact schema ceiling)
- `deadline_ns` — `int` (exact schema ceiling)
- `now_ns` — `int` (exact schema ceiling)
- `queue_depth` — `int` (exact schema ceiling)
- `queue_ceiling` — `int` (exact schema ceiling)
- `requested_tokens` — `int` (exact schema ceiling)
- `token_ceiling` — `int` (exact schema ceiling)

## Required semantic invariants

- Reject expired work before allocation.
- Bound queued work per tenant.
- Bind requested tokens to operator quota.

## Operational proof

Review the schema and predicate, execute the two accepted and ten rejected
fixtures, then independently verify actual model, operator, rights, or device
evidence. A passed contract is never autonomous release authorization.
