# priorities — native candidate training source

## Purpose

Train on original, finite examples of **fixed four-tier severity map independent of model persuasion**. This is
one of 24 separate learning capabilities and includes 24 source records.
Every question and expected completion is an original synthetic example,
not a model-authored output or extracted third-party dataset.

## Operational flow

1. Parse source records as strict canonical JSON; reject unknown fields.
2. Check explicit `skeleton_original` rights and candidate-training scope.
3. Verify record identity, group identity, provenance and SHA-256 digest.
4. Compare the answer with an independent ground-truth function.
5. Deduplicate normalized input, grouping and complete source identity.
6. Assign whole groups into deterministic 18/3/3 train/validation/holdout.
7. Admit only training examples to a native tokenizer and cloned model.
8. Check model-specific real tokenizer coverage before gradient updates.
9. Retain validation and holdout exclusively for independent inference.
10. Treat candidate checkpoints as untrusted until separate review.

## Files

- Source: `skeleton/ai/runtime/operational_ai/native_candidate/examples/v1/priorities/`
- Source integrity: `native_candidate/semantic_oracle.py`
- Unit checks: `skeleton/testing/test_native_candidate_priorities.py`

Each validation receipt binds its exact source item and output digest. The
model score remains unknown until genuinely generated answers are measured.
A perfect corpus contract test is **not** a real model-training pass, proof
of learning quality, clean device install or release certification.

## Adversarial checks

Malformed identifiers, duplicate source keys, modified correct answers,
unbounded input, missing rights, cross-group leakage, changed model identity,
ambiguous effects and incomplete snapshots must remain blocked. No trained
weights are committed to source Git, and no game-system code is touched.

## Release disposition

Only explicit, operator-approved native training may create a candidate.
Production admission, model promotion and merge/release remain separate
fail-closed decisions requiring exact-head security, consumer and model gates.
