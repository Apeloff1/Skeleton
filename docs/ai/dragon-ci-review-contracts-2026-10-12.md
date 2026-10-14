# Dragon milestone — exact-head safety regression reconciliation

**Recorded:** 2026-10-12 UTC  
**Scope:** PR #3605, Dragon branch `feat/dragon-wisdom-review-20261010`.

## Verified regression baseline

Feature-branch workflow run 38293319780:
- **Dragon Frontend: success** — component, wire, wisdom, native-delivery and TypeScript checks succeeded.
- **Dragon Python: failure** — 1,285 passed, 3 failed, 20 skipped. Failures were stale exception expectations and a previously moved sparse-weight `WORD` import.
- **Dragon Source Safety: failure** — a durable lease denial message did not match the old regex; two preflight calls omitted the now-mandatory independent rights attestation; the type-check test incorrectly expected `ValueError` instead of fail-closed `TypeError`; a workboard test read only the first 30 source IDs in a 248-candidate catalog.

## Milestone 1 — Reconcile independent rights and durable worker controls

The revoked-license preflight now supplies the signed external rights attestation, so verification reaches and exercises the revoked-grant authority rather than failing from a missing argument. The unready-source preflight also supplies independent rights attestation. The durable second-lease test now accepts the specific `no runnable durable proposal` rejection while retaining the real global ticket, host cooldown, exclusive lease, and resource boundaries. All production rights and worker safety code remains fail-closed.

## Milestone 2 — Restore shadow-weight suite and catalog pagination verification

The shadow-weight test imports the `WORD` tokenizer from its actual module `skeleton.ai.game_builder.dragon_almanac_weights`, preserving direct comparison of compiled sparse postings against the reference integer scorer. Its invalid human-review case accepts the correct `KeyError` from the canonical ledger when no review ID exists: unknown approval remains rejected. The specialist read-only workboard test iterates bounded source pages and checks the actual selected source, instead of assuming a specific digest sorts into page one.

## Milestone 3 — Run authenticated backend separately

A new `Dragon Authenticated Research Backend` GitHub Actions job tests the research and Dragon Academy routes independently of the large Python suite. It installs its own runtime and keeps read-only source custody tests visible even when unrelated tests fail earlier. The regular Python and Source Safety gates remain enabled and must pass independently.

## Non-goals and acceptance

No live external crawler, privileged rights approval, model promotion, XP minting, or forced merge. The changes correct actual pytest expectations and orchestration of tests, not enforcement. Claims of success must be based on the **new exact-head** Python, Source Safety, Backend and Frontend results.

**Timestamped improvements (2026-10-12 UTC):**
- (Revoked source rights still fail before network requests, with complete preflight inputs.)
- (Unknown human approvals fail closed and are recognized by the regression suite.)
- (Sparse shadow-weight ranking stays compared against its original independent scorer.)
- (Workboard checks source state across full bounded pagination.)
- (Authenticated backend gets independent CI visibility.)
