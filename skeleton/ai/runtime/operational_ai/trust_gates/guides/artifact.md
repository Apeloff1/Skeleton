# artifact — AI runtime assurance

This boundary strictly validates a bounded source record before it can inform
AI runtime admission. Its verifier is executable, not a documentation-only policy.

## Input keys

- `model_id` — `text` (exact schema ceiling)
- `digest` — `text` (exact schema ceiling)
- `bytes` — `int` (exact schema ceiling)
- `shard_bytes` — `array` (exact schema ceiling)
- `license` — `text` (exact schema ceiling)
- `approved` — `bool` (exact schema ceiling)
- `source` — `text` (exact schema ceiling)

## Required semantic invariants

- Shard sum equals declared model bytes.
- Licensing approval is an operator input.
- Provenance cannot be inferred from source text.

## Operational proof

Review the schema and predicate, execute the two accepted and ten rejected
fixtures, then independently verify actual model, operator, rights, or device
evidence. A passed contract is never autonomous release authorization.
