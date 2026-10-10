# P3-T2 Training, Learning, and Multimodal Implementation Candidates

Status: **implementation candidates; not closed, signed, verified, hardened, or production-promoted**

Authority:
- continuation frontier: `machine/ai_masterplan_continuation_frontier.json`
- master plan: `machine/ai_master_plan.json`
- shared candidate evidence contract: `skeleton/ai/runtime/p3t2/evidence.py`
- exact-head batch validator: `scripts/check_p3t2_continuation_candidates.py`

## Batch scope

This batch advances three dependency-ordered P3-T2 owners from planning-only
toward executable implementation-candidate status without changing the
tranche's `planned` authority.

| Task | Lane | Exact volumes | Dependency |
| --- | --- | --- | --- |
| `P3T2-TRAINING-01` | `P3T2-L2` | VOL-143..VOL-149 | `P3T2-DATA-01` |
| `P3T2-LEARNING-01` | `P3T2-L3` | VOL-150..VOL-152 | `P3T2-TRAINING-01` |
| `P3T2-MULTIMODAL-01` | `P3T2-L4` | VOL-153..VOL-159 | data + training + learning |

The union is exactly **17 volumes, VOL-143 through VOL-159**, with no overlap
or orphan inside this batch.

## What was already implemented

Current main already contains substantive implementation and executable
regressions for these volumes. This batch does not duplicate those runtimes.
Instead it binds them back to the current continuation frontier and makes their
remaining independent-evidence obligations executable.

Training and learning also retain canonical/AI-tree mirror parity:

`skeleton/training -> skeleton/ai/training`

The candidate validator checks the exact `AIFT-TRAINING` source tree identity
and byte parity for every mapped module owned by VOL-143..VOL-152.

## Evidence anti-stitching

A candidate proof is rejected unless it binds:
- one exact 40-character Git revision;
- one execution subject;
- one planned task and lane;
- one exact volume identity;
- non-empty evidence references;
- an observation digest;
- distinct producer and verifier identities.

A lane receipt must cover its exact volume set once and only once. Proofs from
different revisions or execution subjects cannot be combined.

A multi-lane continuation receipt additionally binds dependency receipt digests,
so downstream evidence cannot silently swap in a different training or
learning result.

These receipts are intentionally non-executing and expose
`promotion_authority=false`.

## Candidate contracts

- `machine/ai_p3t2_training_candidate.json`
- `machine/ai_p3t2_learning_candidate.json`
- `machine/ai_p3t2_multimodal_candidate.json`

Each contract preserves:
- `completion_checkbox=false`;
- `implementation_signed=false`;
- `verification_signed=false`;
- `may_self_close=false`;
- exact-head CI;
- current-main reconciliation;
- independent closure;
- single-revision and single-subject evidence;
- independent verifier identity.

## Validation

The focused workflow is
`.github/workflows/p3t2-training-learning-multimodal.yml`.

It checks out the exact PR head, validates the masterplan and continuation
authority, validates each candidate and the combined dependency chain, and runs
the exact per-volume regressions plus cross-plane training/learning/multimodal
acceptance.

A green candidate workflow is necessary evidence for landing the candidate. It
is not independent closure authority and does not set any completion checkbox.

## Collision boundary

`P3T2-LIFECYCLE-01` is deliberately excluded from this batch because active
volume-specific implementation branches already own VOL-407, VOL-408,
VOL-411, VOL-412, and VOL-413. VOL-179 remains part of that lifecycle owner.
This avoids creating parallel implementations or competing ownership while
those changes are in flight.

## Next closure step

After landing on current main, a separate exact-main validation and independent
closure authority may reconcile candidate evidence for training, learning, and
multimodal. Only that later authority may change maturity, signatures, or
completion state.
