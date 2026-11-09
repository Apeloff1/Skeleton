# Dragon milestone batch — signed freshness, Jeeves guarded retrieval, canary replay
**Date:** 2026-10-12 UTC · **PR:** #3605 · **Scope:** research-controlled application retrieval weights

## M1 — Resolve the first reproducible exact-head CI regression
Dragon Source Safety run 38309655518 finished with 3 failures and 109 passing tests. All three failed at the exact same source location in DragonWeightCanary.audit: persisted signed canary evidence includes its canonical `schema` field, but the code passed `schema` to the SignedCanaryPair dataclass constructor, which has no such parameter. The decoder now validates the full exact field set and explicit schema discriminator, then constructs SignedCanaryPair with only genuine dataclass fields and separately stored signature. This preserves HMAC validation and external assessor signature verification. No safety test is skipped or relaxed.

## M2 — Independently signed freshness ledger to prevent serving stale research
DragonKnowledgeFreshnessLedger maintains owner- and knowledge-digest-scoped SQLite events. Each event contains an externally signed reviewer statement binding knowledge, source-set and active retrieval-index digests. The ledger uses a separate HMAC custody key, monotonic independent-review timestamps, bounded seven-day validity, owner/knowledge-specific compare-and-swap revisions, and full genesis-to-head replay on every read. Missing or tampered events, truncation, stale/expired receipts, mismatched index/source sets, and changed-source or revoked-rights events fail closed. Explicit permanent revocation cannot be undone under the same knowledge identity.

The chain is *not* a substitute for independent publisher fact-checking: reviewer signatures attest the reviewer's decision, not that facts are true. The original 100 scrutiny matrices, source corroboration, sandbox holdouts, operator approval, and custody of reviewed weights remain separate mandatory prerequisites.

## M3 — Jeeves guarded retrieval and safe canary control
JeevesFreshnessGuard wraps only previously approved DragonDurableWeightVault versions. It verifies the vault's full HMAC replay via audit, demands a signed current source-set/index freshness receipt before returning booked retrieval IDs, then rechecks both the vault generation/head and selected freshness head to catch mid-request updates. With a canary, candidate and control receive *separate* evidence checks. If the candidate is stale or the signed canary is halted, only a current control may serve. If both are stale or invalid, routing refuses; it never falsely substitutes an expired baseline.

This is a read-time, application-level retrieval routing fence; it does not rewrite neural model weights, auto-train from video or RSS, grant publisher rights, auto-increase exposure, or independently assert model improvement.

## M4 — Adversarial regression gates
New tests/test_dragon_evidence_freshness.py exercises the signed review lifecycle, foreign owner and bad signer, expiration, stale→re-review with changed source sets, immutable revoked state, SQLite tampering, head truncation across restart, approved-index routing, invalid active release, control-only canary fallback, and concurrent generation change. Exact-head Dragon Source Safety compiles both new modules and runs their regression suite beside the full existing video/RSS/canary tests.

## Remaining hard blockers
- The new freshness ledger and guard are callable components; production Jeeves serving must explicitly use the guard rather than the existing unguarded routing interface.
- Source-group assertions require independent external reviewers and already-authorized source acquisition. No autonomous model weight rewrite is claimed.
- PR #3605 remains draft until all required exact-head jobs pass. CI status must be checked against the newly pushed commit, not previous green heads.

**Timestamped improvements (2026-10-12 UTC):** (fixed signed canary replay schema); (added monotonic independently signed source-freshness fencing); (revoked evidence prevents stale retrieval use); (canary fallback validates control knowledge separately); (HMAC journal truncation and concurrent activation covered by regressions).