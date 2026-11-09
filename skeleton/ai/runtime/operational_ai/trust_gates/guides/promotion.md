# promotion — offline AI runtime contract

**Scope:** Versioned, strict input admission for the `promotion` runtime boundary.

## Required input fields

- `head_sha` — `text` (bounded, not implicitly coerced)
- `checks` — `object` (bounded, not implicitly coerced)
- `independent_review` — `bool` (bounded, not implicitly coerced)
- `real_model_e2e` — `bool` (bounded, not implicitly coerced)
- `model_rights` — `bool` (bounded, not implicitly coerced)
- `installation` — `bool` (bounded, not implicitly coerced)

## Semantic authority conditions

- Every required final-head CI gate succeeds.
- Independent review and real device/model E2E are mandatory.
- Model rights, installation and exact SHA remain held.

## Operator review

Inspect `schemas/promotion.json` and `semantics/promotion.py`, execute twelve
fixtures for this gate, and independently establish the provenance of every
underlying claim. Passing syntax/semantics does not create external evidence.
No admission result may grant shell, network or branch-merge authority.
