# Repository Mining Cycle — 2026-09-14

This cycle reopens the earlier consolidation verdicts and treats sibling repositories as design mines rather than merge candidates. Code is promoted only when it adds a capability not already present in Skeleton and can be integrated behind native project boundaries.

## Promoted primitives

### gameforge-middleware → Python spine

Source concept: `Zaibatsu.Gate/Audit/WormAuditLog.cs`.

Promoted as `backend/core/worm_audit.py` with:

- dependency-free immutable audit entries;
- SHA-256 predecessor chaining;
- strict sequence validation;
- startup chain verification;
- corruption/unreadable-ledger fail-closed behavior;
- serialized concurrent appends;
- flush + `fsync` before acknowledging an append;
- focused regression coverage under `backend/tests/test_worm_audit.py`.

This is an adaptation, not a transliteration: Python canonical JSON hashing replaces the C# delimited payload so field boundaries remain unambiguous.

### hyperforge-cockpit-sota → Expo frontend quality gate

Source concept: `scripts/browser-smoke-verdict.mjs`.

Promoted as `frontend/scripts/ui-regression-verdict.mjs` with:

- normalized rendered-text identity hashing;
- desktop/mobile viewport comparison;
- HTTP status, title, canvas and horizontal-overflow regression checks;
- console/page error emergence detection;
- body-collapse and same-size identity replacement detection;
- fail-closed malformed-baseline handling;
- deterministic exit-code classification;
- dependency-free Node test coverage.

The browser-launch harness was intentionally not copied because Hyperforge used a different web stack. Skeleton receives the reusable verdict engine; a native Expo browser capture layer can feed it later.

## CI

`.github/workflows/mined-primitives.yml` gates both promoted primitives independently with Python 3.11 and Node 24, matching Skeleton's declared runtime baselines.

## Next mining targets

- `gameforge-rs`: admission, cancellation, backpressure and request-budget semantics;
- Hyperforge cockpit: reusable 3D/ECS state-transition logic that is not coupled to TanStack;
- legacy Openworld/Newmove prototypes: simulation/gameplay algorithms only, excluding obsolete UI scaffolds and generated assets;
- Prood/Tutolage: re-diff for post-survey commits before retaining the redundancy verdict.
