# path — offline AI runtime contract

**Scope:** Versioned, strict input admission for the `path` runtime boundary.

## Required input fields

- `relative_path` — `text` (bounded, not implicitly coerced)
- `root_id` — `text` (bounded, not implicitly coerced)
- `entry_type` — `text` (bounded, not implicitly coerced)
- `bytes` — `int` (bounded, not implicitly coerced)
- `byte_limit` — `int` (bounded, not implicitly coerced)
- `suffix` — `text` (bounded, not implicitly coerced)
- `immutable` — `bool` (bounded, not implicitly coerced)

## Semantic authority conditions

- Traversal/absolute path is denied lexically.
- Path suffix is identity-bound.
- Per-file bytes are bounded and source immutable.

## Operator review

Inspect `schemas/path.json` and `semantics/path.py`, execute twelve
fixtures for this gate, and independently establish the provenance of every
underlying claim. Passing syntax/semantics does not create external evidence.
No admission result may grant shell, network or branch-merge authority.
