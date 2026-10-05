# Max-workload manifest — 2026-09-13

## Delivered

- Prood inventory.
- Tutolage inventory.
- gameforge-rs inventory.
- Consolidation execution gate.
- Promotion gates.
- Cross-source parity matrix.

## Active execution lanes

1. **Kernel parity:** cache, pool, backpressure, buffers, coalescing, quorum.
2. **Runtime parity:** event bus, idempotency, saga/event-sourcing semantics.
3. **Jeeves parity:** system laws, tutor boundaries, learning matrices.
4. **Game parity:** NPC, game-logic, animation contracts.
5. **Memory parity:** provider-neutral retrieval boundary; Chroma as adapter.
6. **Provenance:** source revision/path on every promoted behavior.
7. **QA:** contract tests before implementation replacement.
8. **Merge:** consolidate only after gates pass.

## Hard exclusions

- Wholesale FastAPI/Axum route copying.
- MongoDB/ChromaDB as kernel requirements.
- Provider-specific AI calls in core contracts.
- Frontend/build/cache/generated artifacts as canonical domain code.
- Secrets, local environment state, credentials, and machine-specific paths.

## Shipping criterion

The consolidation is considered materially advanced only when a source capability has either been promoted with tests or explicitly characterized/rejected with provenance. Inventory without disposition is insufficient.
