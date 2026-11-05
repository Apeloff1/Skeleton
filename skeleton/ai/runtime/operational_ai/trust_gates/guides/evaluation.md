# evaluation — offline AI runtime contract

**Scope:** Versioned, strict input admission for the `evaluation` runtime boundary.

## Required input fields

- `suite_id` — `text` (bounded, not implicitly coerced)
- `dataset_sha` — `text` (bounded, not implicitly coerced)
- `model_sha` — `text` (bounded, not implicitly coerced)
- `samples` — `int` (bounded, not implicitly coerced)
- `passes` — `int` (bounded, not implicitly coerced)
- `failures` — `int` (bounded, not implicitly coerced)
- `empty_errors` — `int` (bounded, not implicitly coerced)
- `approved` — `bool` (bounded, not implicitly coerced)

## Semantic authority conditions

- Evaluation includes actual samples.
- Outcome counts reconcile exactly.
- Evaluation evidence has caller approval.

## Operator review

Inspect `schemas/evaluation.json` and `semantics/evaluation.py`, execute twelve
fixtures for this gate, and independently establish the provenance of every
underlying claim. Passing syntax/semantics does not create external evidence.
No admission result may grant shell, network or branch-merge authority.
