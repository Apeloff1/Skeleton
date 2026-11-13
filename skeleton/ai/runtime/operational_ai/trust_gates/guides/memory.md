# memory — offline AI runtime contract

**Scope:** Versioned, strict input admission for the `memory` runtime boundary.

## Required input fields

- `tenant` — `text` (bounded, not implicitly coerced)
- `source_tenant` — `text` (bounded, not implicitly coerced)
- `source_id` — `text` (bounded, not implicitly coerced)
- `approved` — `bool` (bounded, not implicitly coerced)
- `revision` — `int` (bounded, not implicitly coerced)
- `expires_at` — `int` (bounded, not implicitly coerced)
- `now` — `int` (bounded, not implicitly coerced)

## Semantic authority conditions

- Memory scope matches tenant.
- Explicit caller consent is mandatory.
- Memory consent has bounded lifetime.

## Operator review

Inspect `schemas/memory.json` and `semantics/memory.py`, execute twelve
fixtures for this gate, and independently establish the provenance of every
underlying claim. Passing syntax/semantics does not create external evidence.
No admission result may grant shell, network or branch-merge authority.
