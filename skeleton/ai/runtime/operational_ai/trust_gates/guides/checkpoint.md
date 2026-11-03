# checkpoint — offline AI runtime contract

**Scope:** Versioned, strict input admission for the `checkpoint` runtime boundary.

## Required input fields

- `model_id` — `text` (bounded, not implicitly coerced)
- `model_sha` — `text` (bounded, not implicitly coerced)
- `tokenizer_sha` — `text` (bounded, not implicitly coerced)
- `format` — `text` (bounded, not implicitly coerced)
- `bytes` — `int` (bounded, not implicitly coerced)
- `max_bytes` — `int` (bounded, not implicitly coerced)
- `step` — `int` (bounded, not implicitly coerced)
- `approved` — `bool` (bounded, not implicitly coerced)

## Semantic authority conditions

- Activation requires operator approval.
- Checkpoint bytes obey resource ceiling.
- Model/tokenizer digests are nonzero.

## Operator review

Inspect `schemas/checkpoint.json` and `semantics/checkpoint.py`, execute twelve
fixtures for this gate, and independently establish the provenance of every
underlying claim. Passing syntax/semantics does not create external evidence.
No admission result may grant shell, network or branch-merge authority.
