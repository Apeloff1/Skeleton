# quota — AI runtime assurance

This boundary strictly validates a bounded source record before it can inform
AI runtime admission. Its verifier is executable, not a documentation-only policy.

## Input keys

- `tenant` — `text` (exact schema ceiling)
- `prompt_used` — `int` (exact schema ceiling)
- `output_used` — `int` (exact schema ceiling)
- `new_prompt` — `int` (exact schema ceiling)
- `new_output` — `int` (exact schema ceiling)
- `tenant_ceiling` — `int` (exact schema ceiling)
- `global_remaining` — `int` (exact schema ceiling)

## Required semantic invariants

- Spent plus pending tokens are jointly bounded.
- Pending usage fits global remaining quota.
- Prompt reservation cannot exceed tenant ceiling.

## Operational proof

Review the schema and predicate, execute the two accepted and ten rejected
fixtures, then independently verify actual model, operator, rights, or device
evidence. A passed contract is never autonomous release authorization.
