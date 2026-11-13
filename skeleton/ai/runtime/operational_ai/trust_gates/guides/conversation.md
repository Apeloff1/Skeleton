# conversation — AI runtime assurance

This boundary strictly validates a bounded source record before it can inform
AI runtime admission. Its verifier is executable, not a documentation-only policy.

## Input keys

- `session_id` — `text` (exact schema ceiling)
- `messages` — `array` (exact schema ceiling)
- `max_bytes` — `int` (exact schema ceiling)
- `revision` — `int` (exact schema ceiling)
- `final_role` — `text` (exact schema ceiling)

## Required semantic invariants

- Inference begins after an actual user turn.
- History bytes are bounded.
- Terminal role agrees with transcript tail.

## Operational proof

Review the schema and predicate, execute the two accepted and ten rejected
fixtures, then independently verify actual model, operator, rights, or device
evidence. A passed contract is never autonomous release authorization.
