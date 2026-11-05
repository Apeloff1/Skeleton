# cancel — offline AI runtime contract

**Scope:** Versioned, strict input admission for the `cancel` runtime boundary.

## Required input fields

- `request_id` — `text` (bounded, not implicitly coerced)
- `state` — `text` (bounded, not implicitly coerced)
- `now_ns` — `int` (bounded, not implicitly coerced)
- `deadline_ns` — `int` (bounded, not implicitly coerced)
- `generated_tokens` — `int` (bounded, not implicitly coerced)
- `acked` — `bool` (bounded, not implicitly coerced)
- `backend_active` — `bool` (bounded, not implicitly coerced)

## Semantic authority conditions

- Cancelled request is no longer active.
- Deadline-expired work cannot remain running.
- Cancellation acknowledgment is explicit.

## Operator review

Inspect `schemas/cancel.json` and `semantics/cancel.py`, execute twelve
fixtures for this gate, and independently establish the provenance of every
underlying claim. Passing syntax/semantics does not create external evidence.
No admission result may grant shell, network or branch-merge authority.
