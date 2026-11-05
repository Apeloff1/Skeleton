# actor — AI runtime assurance

This boundary strictly validates a bounded source record before it can inform
AI runtime admission. Its verifier is executable, not a documentation-only policy.

## Input keys

- `tenant` — `text` (exact schema ceiling)
- `user` — `text` (exact schema ceiling)
- `request_id` — `text` (exact schema ceiling)
- `model_sha` — `text` (exact schema ceiling)
- `tokenizer_sha` — `text` (exact schema ceiling)
- `scope` — `text` (exact schema ceiling)
- `rights` — `array` (exact schema ceiling)

## Required semantic invariants

- Caller scope must bind exact tenant and user.
- Model text cannot grant write/admin rights.
- Wildcard principal identities are denied.

## Operational proof

Review the schema and predicate, execute the two accepted and ten rejected
fixtures, then independently verify actual model, operator, rights, or device
evidence. A passed contract is never autonomous release authorization.
