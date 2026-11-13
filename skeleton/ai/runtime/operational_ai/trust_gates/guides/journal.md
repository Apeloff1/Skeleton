# journal — offline AI runtime contract

**Scope:** Versioned, strict input admission for the `journal` runtime boundary.

## Required input fields

- `stream` — `text` (bounded, not implicitly coerced)
- `sequence` — `int` (bounded, not implicitly coerced)
- `prev_sha` — `text` (bounded, not implicitly coerced)
- `event_sha` — `text` (bounded, not implicitly coerced)
- `kind` — `text` (bounded, not implicitly coerced)
- `payload_sha` — `text` (bounded, not implicitly coerced)
- `epoch` — `int` (bounded, not implicitly coerced)

## Semantic authority conditions

- Genesis previous digest is zero.
- Event cannot be its own predecessor.
- Only known event kinds are admitted.

## Operator review

Inspect `schemas/journal.json` and `semantics/journal.py`, execute twelve
fixtures for this gate, and independently establish the provenance of every
underlying claim. Passing syntax/semantics does not create external evidence.
No admission result may grant shell, network or branch-merge authority.
