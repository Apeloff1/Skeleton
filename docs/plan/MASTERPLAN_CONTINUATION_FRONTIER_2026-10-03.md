# Masterplan Continuation Frontier — 2026-10-03

This frontier continues the frozen Skeleton AI master plan **after the bounded P0/P1 production frontier has closed**. It is a planning and conservation authority, not a completion or sign-off authority.

Machine mirror: [`machine/ai_masterplan_continuation_frontier.json`](../../machine/ai_masterplan_continuation_frontier.json)

Independent validator: [`scripts/check_ai_masterplan_continuation.py`](../../scripts/check_ai_masterplan_continuation.py)

## Landed authority chain

| Stage | Source | Closed / scheduled | Explicitly deferred | Status |
| --- | ---: | ---: | ---: | --- |
| P1 trustworthy-production frontier | 421 | 107 | 314 | terminally closed |
| P2 bounded functional frontier | 314 | 57 | 257 | closed |
| P3-T0 expansion frontier | 257 | 23 | 234 | closed |
| P3-T1 autonomous-engineering frontier | 234 | 37 | 197 | closed |
| P3-T2 consolidated continuation | 197 | 32 | 165 | **planned** |

The first four rows are read from existing closure authorities. The final row is the next master-plan tranche and deliberately carries no completion, implementation-signature, verification-signature, or production-promotion authority.

## P0/P1 handoff law

The canonical functional gap inventory is 17/17 closed: 14 P0 gaps and 3 P1 gaps. The P1 terminal manifest remains authoritative even though historical execution maps and task backlogs stay active as planning/provenance ledgers.

A later planning ledger therefore cannot reopen P0/P1 by merely containing blocked or unsigned historical tasks. Reopening requires an actual canonical construction-gap regression, and continuation promotion fails closed until that regression is independently revalidated.

## Exact continuation source

P3-T1 leaves **197 exact volume identities**. P3-T2 must consume that set without loss or duplication.

The planned T2 partition is **32 scheduled / 165 queued**, with zero overlap and exact union back to all 197 source volumes. Every reference must resolve to the frozen `VOL-000..VOL-420` registry.

## Consolidated P3-T2 tranche

The next tranche unifies six dependency-ordered lanes:

1. Distributed data identity, cache and content addressing.
2. Ingestion, lineage, quality and dataset governance.
3. Training control, checkpoints, recovery and evaluation.
4. Reinforcement, curriculum and verifier programs.
5. Multimodal ingestion and retrieval acceptance.
6. Model governance, lifecycle and migration.

Two existing unmerged planning directions overlap. PR #2352's 19-volume native-training set is a strict subset of PR #2351's broader 32-volume learning/multimodal/model-lifecycle set. This frontier reconciles the overlap by retaining **one 32-volume planning owner**. Later implementation candidates may attach to those owners, but candidate presence never becomes closure, signature, or production evidence without exact-head validation and independent reconciliation.

## Atomic planning owners

The 32 scheduled volumes now have exactly one planning owner each. These are scheduling owners only; all six remain unsigned and uncompleted until current-main implementation evidence is independently established. Storage and data retain landed implementation-candidate records, while training, learning, and multimodal now carry branch implementation-candidate contracts with exact-head validation still pending. All five candidate-bearing owners remain planning-status `planned`; none has advanced to independent closure or `landed_unpromoted`.

| Task | Lane | Planned volumes | Depends on | Evidence state |
| --- | --- | --- | --- | --- |
| `P3T2-STORAGE-01` | `P3T2-L0` | VOL-133, VOL-135, VOL-136 | — | PR #2477 landed implementation candidate; exact-head validation pending |
| `P3T2-DATA-01` | `P3T2-L1` | VOL-137, VOL-138, VOL-139, VOL-140, VOL-141, VOL-142 | `P3T2-STORAGE-01` | planned only |
| `P3T2-TRAINING-01` | `P3T2-L2` | VOL-143, VOL-144, VOL-145, VOL-146, VOL-147, VOL-148, VOL-149 | `P3T2-DATA-01` | branch implementation candidate; exact-head validation pending |
| `P3T2-LEARNING-01` | `P3T2-L3` | VOL-150, VOL-151, VOL-152 | `P3T2-TRAINING-01` | branch implementation candidate; exact-head validation pending |
| `P3T2-MULTIMODAL-01` | `P3T2-L4` | VOL-153, VOL-154, VOL-155, VOL-156, VOL-157, VOL-158, VOL-159 | `P3T2-DATA-01`, `P3T2-TRAINING-01`, `P3T2-LEARNING-01` | branch implementation candidate; exact-head validation pending |
| `P3T2-LIFECYCLE-01` | `P3T2-L5` | VOL-179, VOL-407, VOL-408, VOL-411, VOL-412, VOL-413 | `P3T2-TRAINING-01`, `P3T2-LEARNING-01` | planned only |

The owner union is exactly the 32-volume scheduled set, with no duplicated or orphaned volume identity.

## Promotion boundary

P3-T2 remains `planned`. Storage and data have landed implementation candidates; training, learning, and multimodal have branch implementation candidates. None of those facts grants completion, signatures, or promotion. Exact-head validation and a separate independent closure authority must prove implementation/evidence reconciliation before any owner may advance beyond candidate state.

This frontier forbids self-closing the tranche, using file presence/LOC/old branch CI as current-main evidence, changing completion checkboxes or sign-offs, erasing any of the 165 queued volumes, assigning a source volume twice, or bypassing canonical provider/tool/authority boundaries.

## Next implementation order

Deepen through governed data identity and datasets, resumable native training, independent evaluation, bounded post-training, multimodal evidence, then model lifecycle/migration. Each lane remains provider-independent at its core and routes any external model I/O through the existing canonical provider boundary.

Shared-main CI repairs remain a separate integration concern. They can block landing evidence, but they do not change the phase-accounting authority above.
