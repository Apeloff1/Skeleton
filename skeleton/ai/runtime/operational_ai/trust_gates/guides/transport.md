# transport — offline AI runtime contract

**Scope:** Versioned, strict input admission for the `transport` runtime boundary.

## Required input fields

- `host` — `text` (bounded, not implicitly coerced)
- `method` — `text` (bounded, not implicitly coerced)
- `auth_type` — `text` (bounded, not implicitly coerced)
- `token_bytes` — `int` (bounded, not implicitly coerced)
- `body_bytes` — `int` (bounded, not implicitly coerced)
- `body_ceiling` — `int` (bounded, not implicitly coerced)
- `content_type` — `text` (bounded, not implicitly coerced)

## Semantic authority conditions

- Transport only binds loopback.
- No anonymous or cookie-only authority.
- Bearer and body sizes are independently bounded.

## Operator review

Inspect `schemas/transport.json` and `semantics/transport.py`, execute twelve
fixtures for this gate, and independently establish the provenance of every
underlying claim. Passing syntax/semantics does not create external evidence.
No admission result may grant shell, network or branch-merge authority.
