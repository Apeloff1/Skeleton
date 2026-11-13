# snapshot plan — memory operational AI

## Production objective

Tenant-scoped consent, memory metadata and source retraction, expiration and physical deletion proof holds.

This is an executable bounded capability family over the shared offline
cognition core. It is not a separate model, does not fake GGUF completions,
and cannot escalate permissions from retrieved text or model suggestions.

## Binding and resource contracts

| Setting | Required bound |
|---|---|
| Family | `snapshot_plan` |
| Domain | memory |
| Source role | retrieval |
| Retrieval mode | hybrid |
| Context window | 4608 advisory tokens |
| Original content | 53248 UTF8 bytes |
| Target task latency | 55000 ms |
| Minimum independent evidence | 2 receipts |
| Scheduling priority | 4 |
| Lexical weight | 0.6 |
| Dense weight | 0.3 |
| Freshness weight | 0.1 |

## Concrete Python capability boundaries

1. **source** — Verify original UTF8 byte digest, explicit rights and bounded source extraction.
2. **search** — Run bounded lexical search only against correctly scoped source receipts.
3. **fusion** — Fuse independent ranking evidence with scope intersection and deterministic ties.
4. **rank** — Score only rights-approved source identities without tenant leakage.
5. **context** — Pack mandatory system/user context before optional untrusted retrieval.
6. **plan** — Topologically order typed AI work with cycle and token-budget holds.
7. **resource** — Admit model work against measurable tokens, memory and time budget.
8. **schedule** — Fairly order work by tenant weighting with hard deadlines.
9. **permission** — Check operation, source, scope and permit expiry without self-authorizing.
10. **native** — Delegate one generation to the actual source-approved SupervisedAI instance.
11. **replay** — Verify committed canonical inference receipts without generating again.
12. **memory** — Maintain private consent-scoped metadata and explicit deletion tombstones.
13. **privacy** — Aggregate allowlisted metrics without storing prompts or bearer secrets.
14. **evaluate** — Calculate bounded benchmark statistics and conservative Wilson confidence.
15. **audit** — Append and verify an actual SHA256 event chain with content integrity.
16. **recover** — Hold uncertain native outcomes rather than silently refunding or retrying.
17. **stream** — Transfer committed Unicode output using ordered frame credit and acknowledgments.
18. **tool** — Leave model-suggested tools inert pending independent operator authority.
19. **checkpoint** — Bind hash-chain and source identity without pretending external attestation.
20. **health** — Refuse work that exceeds observed capacity or lacks provenance evidence.

## Adversarial contract tests

Two valid source profiles must be admitted, and thirty-eight malformed
or unauthorized profiles must be rejected. Every capability has its own
real Python operation test, hostile-case test and profile-bound check.
The fixture is a source input, not an independent trusted operator signature.

## Mandatory external qualification

Approved model rights and installed bytes, true GGUF generation, target
laptop device pressure, private database cold-restart behavior, OS
cancellation, exact-final-head CI/security and independent human review
must succeed separately. This source contract cannot certify a release.
