# limits — original native learning stream

## Capability

**track finite token resource reservations.** Twenty-four distinct original synthetic records
exercise this capability. Each accepted source is backed by a canonical
identity, finite prompt, independently checked completion and explicit
candidate-only rights scope; it is not a pretrained weight or a model score.

## Ordered integration

1. Admit exact versioned `skeleton.native-candidate.example.v1` JSON.
2. Confirm rights status allowed, original license and declared training use.
3. Recalculate correct answer through `semantic_oracle.expected_answer`.
4. Reject duplicate prompt, ID, source digest or contaminated benchmark text.
5. Partition groups across train (18), validation (3), holdout (3).
6. Use training rows only in the native tokenizer and cloned model's SGD.
7. Store candidate checkpoint by content SHA-256 under private file custody.
8. Run independent native generation separately on validation/holdout items.
9. Check source/output digests and compare measured outcomes to champion.
10. Preserve separate, never-automatic promotion and release gates.

## Source and focused regression

- `skeleton/ai/runtime/operational_ai/native_candidate/examples/v1/limits`
- `skeleton/testing/test_native_candidate_limits.py`

These source tests verify the immutable dataset and expected answers. A pass
does not mean any real model learned the behavior or achieved an acceptable
quality threshold. Quality can only be measured by the native backend after
checkpoint verification and physical-device inference.

## Failure handling

A changed answer or rights marker changes source identity and must block.
An unknown model, altered training parameters, accidental holdout inclusion,
expired process lock, incomplete optimizer batch or ambiguous publication
requires review. No network inference fallback, shell or write-capable
model-authorized tool is part of these source records.

## Holds

Release, device, rights, installer, model promotion, CI, independent
evaluation, privacy and rollback gates remain separate from this domain.
