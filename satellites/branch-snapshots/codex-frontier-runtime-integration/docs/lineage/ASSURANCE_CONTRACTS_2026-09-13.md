# Assurance contracts

The frontier assurance layer provides provider-neutral primitives for bounded execution, fail-closed admission, deterministic state identity, provenance, verification, and replay snapshots.

## Invariants

- Bounds reject invalid construction rather than silently widening limits.
- Quality gates pass only when every supplied check passes and at least one check exists.
- Decisions require explicit action and reason fields.
- Outcomes cannot represent simultaneous success and failure.
- Verification must explicitly pass before promotion.
- State digests use canonical key ordering.
- Snapshots retain the sequence and canonical digest of captured state.

These contracts are intentionally independent of frameworks, databases, vendors, and external providers.
