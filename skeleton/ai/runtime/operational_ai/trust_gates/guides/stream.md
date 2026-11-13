# stream — AI runtime assurance

This boundary strictly validates a bounded source record before it can inform
AI runtime admission. Its verifier is executable, not a documentation-only policy.

## Input keys

- `request_id` — `text` (exact schema ceiling)
- `chunks` — `array` (exact schema ceiling)
- `max_bytes` — `int` (exact schema ceiling)
- `terminal` — `text` (exact schema ceiling)
- `generated_tokens` — `int` (exact schema ceiling)
- `token_ceiling` — `int` (exact schema ceiling)

## Required semantic invariants

- Chunks are ordered without gaps.
- Streamed UTF-8 output fits byte ceiling.
- Token receipt fits generation reservation.

## Operational proof

Review the schema and predicate, execute the two accepted and ten rejected
fixtures, then independently verify actual model, operator, rights, or device
evidence. A passed contract is never autonomous release authorization.
