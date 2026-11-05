# tool — AI runtime assurance

This boundary strictly validates a bounded source record before it can inform
AI runtime admission. Its verifier is executable, not a documentation-only policy.

## Input keys

- `grant_id` — `text` (exact schema ceiling)
- `tool_id` — `text` (exact schema ceiling)
- `args` — `object` (exact schema ceiling)
- `risk` — `text` (exact schema ceiling)
- `approved` — `bool` (exact schema ceiling)
- `request_id` — `text` (exact schema ceiling)

## Required semantic invariants

- Only read-only tools are admitted.
- Caller approval is independent of model output.
- Traversal and absolute tool paths are denied.

## Operational proof

Review the schema and predicate, execute the two accepted and ten rejected
fixtures, then independently verify actual model, operator, rights, or device
evidence. A passed contract is never autonomous release authorization.
