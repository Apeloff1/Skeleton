# tokenizer — AI runtime assurance

This boundary strictly validates a bounded source record before it can inform
AI runtime admission. Its verifier is executable, not a documentation-only policy.

## Input keys

- `model_id` — `text` (exact schema ceiling)
- `digest` — `text` (exact schema ceiling)
- `vocab_size` — `int` (exact schema ceiling)
- `bos_id` — `int` (exact schema ceiling)
- `eos_id` — `int` (exact schema ceiling)
- `unk_id` — `int` (exact schema ceiling)
- `context_window` — `int` (exact schema ceiling)
- `normalization` — `text` (exact schema ceiling)

## Required semantic invariants

- Token IDs remain distinct and in vocabulary.
- Normalization is explicit.
- Context limits are verified against manifest.

## Operational proof

Review the schema and predicate, execute the two accepted and ten rejected
fixtures, then independently verify actual model, operator, rights, or device
evidence. A passed contract is never autonomous release authorization.
