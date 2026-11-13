# sampling — AI runtime assurance

This boundary strictly validates a bounded source record before it can inform
AI runtime admission. Its verifier is executable, not a documentation-only policy.

## Input keys

- `request_id` — `text` (exact schema ceiling)
- `temperature` — `number` (exact schema ceiling)
- `top_p` — `number` (exact schema ceiling)
- `max_output` — `int` (exact schema ceiling)
- `context_window` — `int` (exact schema ceiling)
- `seed` — `int` (exact schema ceiling)
- `repetition_penalty` — `number` (exact schema ceiling)

## Required semantic invariants

- Output is strictly smaller than context.
- Finite nonzero sampling temperature.
- Top-p probability is positive.

## Operational proof

Review the schema and predicate, execute the two accepted and ten rejected
fixtures, then independently verify actual model, operator, rights, or device
evidence. A passed contract is never autonomous release authorization.
