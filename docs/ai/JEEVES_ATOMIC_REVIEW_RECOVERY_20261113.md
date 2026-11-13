# Atomic Jeeves world review restoration — source reconciliation 2026-11-13

This implementation recovers review-preview/CAS/approval custody from the historical
`feat/studio-a-review-replay-fence-20261107-r03` without replacing the current
laptop-first world and gameplay orchestration on `main`.

## Why
The current `LaptopFlow.review` publishes an edited world and subsequently
approves it as two separately leased operations, allowing a concurrent edit
between publication and approval. The older reviewed version holds a single
world writer lease across source CAS, authored proof, review invalidation,
world publication, and review receipt writing.

## Behavior
- `preview_edit(world_id, expected_digest, operation)` is read-only and
  returns the source/candidate/operation digests plus sorted modified, added
  and deleted scene/choice/ending IDs.
- `review(..., expected_candidate_digest=..., expected_operation_digest=...)`
  rejects changed source, intent or candidate before writing.
- The review is revoked before publishing source changes, preventing an older
  approval or interrupted A→B→A sequence from authorizing a new revision.
- If the review receipt write fails after the world edit, the world remains
  unapproved. Compilation and acceptance must fail until explicit new review.
- The current world, studio engine, builder, game save, offline and portable
  acceptance code outside these two methods remains unchanged.
- Canonical `skeleton/jeeves/worlds/laptop_flow.py` and mirrored
  `skeleton/ai/agents/jeeves/worlds/laptop_flow.py` use identical content.

## Qualification
Adapted without rewriting the historical source-level regression:
`skeleton/testing/test_jeeves_laptop_atomic_review.py` tests read-only
preview, expected operation/candidate pins, lease contention, prior approval
invalidation, interrupted writes/reversion, stale receipts and accepted
recovery. These are file-system simulation tests rather than live device or
release evidence.

**Review only.** Require exact-head focused tests plus existing Jeeves,
world canon, source-mirror, package, security, workflow and device gates.
No direct merge into main or release without confirmed qualification.
