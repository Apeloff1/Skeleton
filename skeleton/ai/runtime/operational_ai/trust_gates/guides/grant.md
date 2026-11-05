# grant — AI runtime assurance

This boundary strictly validates a bounded source record before it can inform
AI runtime admission. Its verifier is executable, not a documentation-only policy.

## Input keys

- `actor_id` — `text` (exact schema ceiling)
- `tool_id` — `text` (exact schema ceiling)
- `expires_at` — `int` (exact schema ceiling)
- `now` — `int` (exact schema ceiling)
- `nonce` — `text` (exact schema ceiling)
- `rights` — `array` (exact schema ceiling)
- `scope` — `text` (exact schema ceiling)

## Required semantic invariants

- Delegation expires.
- No write/execute tool grants.
- Grant is bound to actor and tool.

## Operational proof

Review the schema and predicate, execute the two accepted and ten rejected
fixtures, then independently verify actual model, operator, rights, or device
evidence. A passed contract is never autonomous release authorization.
