# retrieval — offline AI runtime contract

**Scope:** Versioned, strict input admission for the `retrieval` runtime boundary.

## Required input fields

- `source_id` — `text` (bounded, not implicitly coerced)
- `text` — `text` (bounded, not implicitly coerced)
- `span_start` — `int` (bounded, not implicitly coerced)
- `span_end` — `int` (bounded, not implicitly coerced)
- `excerpt` — `text` (bounded, not implicitly coerced)
- `source_sha` — `text` (bounded, not implicitly coerced)
- `approved` — `bool` (bounded, not implicitly coerced)

## Semantic authority conditions

- Exact UTF-8 byte spans bind excerpts.
- Source SHA256 binds retrieved bytes.
- Untrusted retrieval cannot add authority.

## Operator review

Inspect `schemas/retrieval.json` and `semantics/retrieval.py`, execute twelve
fixtures for this gate, and independently establish the provenance of every
underlying claim. Passing syntax/semantics does not create external evidence.
No admission result may grant shell, network or branch-merge authority.
