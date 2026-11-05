# replay — offline AI runtime contract

**Scope:** Versioned, strict input admission for the `replay` runtime boundary.

## Required input fields

- `request_id` — `text` (bounded, not implicitly coerced)
- `model_sha` — `text` (bounded, not implicitly coerced)
- `expected_model_sha` — `text` (bounded, not implicitly coerced)
- `request_digest` — `text` (bounded, not implicitly coerced)
- `stored_digest` — `text` (bounded, not implicitly coerced)
- `revision` — `int` (bounded, not implicitly coerced)
- `replayed` — `bool` (bounded, not implicitly coerced)
- `has_generation` — `bool` (bounded, not implicitly coerced)

## Semantic authority conditions

- Replay is model-epoch pinned.
- Request digest must match stored receipt.
- Replayed requests must not regenerate.

## Operator review

Inspect `schemas/replay.json` and `semantics/replay.py`, execute twelve
fixtures for this gate, and independently establish the provenance of every
underlying claim. Passing syntax/semantics does not create external evidence.
No admission result may grant shell, network or branch-merge authority.
