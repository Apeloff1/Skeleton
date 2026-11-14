# Independent real-model comparison

Evaluation loads previously published champion and candidate checkpoints
through the descriptor-bound private source. It verifies checkpoint hashes,
then independently restores both native model identities.

Validation and holdout partitions are disjoint from training. Model outputs
are generated with the real native inference graph; no expected answer is
substituted for model output. The deterministic source answer serves as the
judge for the corresponding original task.

The paired evaluation calculates actual exact-match scores over identical
source IDs, and counts improvements, regressions and unchanged cases.
The report preserves per-case output digests and model/tokenizer identity.
A positive measured delta is evidence for model review, not automatic
promotion or admission.

The constructor refuses training data as an evaluation partition, refuses
comparing a model to itself as an improvement, and rejects missing,
untrusted or mismatched checkpoints.

Independent rights review, near-duplicate contamination analysis, device
qualification, exact-head CI, operational recovery and an explicitly
separate release authority remain mandatory. The paired evaluation itself
sets `release_certified=false`.
