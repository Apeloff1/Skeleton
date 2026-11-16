# Jeeves advanced adaptation and precision — phase VI

## Actual low-rank candidate learning

The existing fenced shadow-native worker supports an optional
NativeAdapterPolicy. Default is disabled, preserving historical full-SGD and
phase-V soft-target modes. These modes are mutually exclusive.

An admitted, cloned, untied CPU transformer provides actual frozen hidden
activations. Its output projection is adapted with the existing Cortex
LoRA factor representation, initially zero delta. We do not attach a
serving adapter or train the embedding, attention, FFN, position or bias
arrays. For the current target, form hard-label CE and frozen-champion
distribution KL gradients at the same effective logits, differentiating
both with respect to A and B using their pre-update values. If the hard
gradient opposes retention, remove its component along the retention
gradient before mixing and clipping. This is retention-priority local
gradient projection, not global multi-task PCGrad or a guarantee of
preserving every old task.

Training accumulates an approximate factorized diagonal output Fisher:
p_champion*(1-p_champion) and squared hidden activations, averaged
separately on admitted training prefixes. Normalized positive importance
weights make a sensitivity-weighted trust ellipsoid. This is Fisher-inspired
weight protection, NOT full elastic weight consolidation based on an
independent prior-task corpus. Exact low-rank Gram contractions bound both
the ordinary and weighted Frobenius norm without materializing a dense
delta on every optimizer step. Check the actual folded delta against both
radii before committing the new candidate output matrix.

Bound all optimizer steps, maximum rank, total factor parameters, estimated
factor and attention arithmetic work, token context and final projection
allocation. Plateau windows can increase rank within the admitted ceiling:
zero new B columns and rescale the existing factors to preserve their
function. No heldout values drive training or rank expansion. A weak or
unchanged candidate is not presented as completed training. Idle/lease
preemption polls during actual graph work. The private candidate alone is
folded after full successful optimizer work; a new runtime is admitted
after folding. The champion stays unchanged. No accelerator mode or tied
embedding/output support is claimed; reject unsupported graphs explicitly.
The base graph and merged result still occupy ordinary floating storage.

The existing LoRA implementation now also computes its returned input
gradient from pre-update factors and its output-adapter training loss from
the actual adapted logits rather than stale base-only logits. Source and
governed mirror bytes must match.

## Evidence and custody

The same shadow worker, dataset revision, training manifest, candidate
checkpoint and independent evaluation gates remain in control. An adapter
report sidecar is content-addressed and atomically published through the
existing private artifact owner. It includes the manifest/dataset hashes,
checkpoint byte digest, actual candidate model identity, factor digest,
folded projection digest, retention conflict/projection/expansion counts,
sensitivity hash and realized radii. The optimizer custody hash binds its
bytes. Worker receipts expose the sidecar path. No promotion authorization
is created; failure can leave private unreferenced artifacts for recovery.

## Layer/group precision sensitivity

The optional explicit calibration API implements a deterministic packed
symmetric integer codec at 4, 6 or 8 bits with FP32 scales and exact
partial-block padding. The reserved all-ones code, invalid sizes, scales,
padding and nonfinite weights are refused. It then runs the ordinary
reference CPU transformer on the decoded values, independently perturbing
each requested disjoint embedding/output/position/attention/FFN group.
Actual paired next-token NLL, accuracy and distribution drift feed the
existing retention evaluator. Select the smallest passing codec payload for
each group and re-run the combined candidate. Any combined regression holds
the candidate; no automatic publication. The calibration dataset must have
evaluation and calibration rights, pinned corpus and materialized training
inventory, pass lexical contamination screening, and exclude the separately
pinned final holdout inventory exactly. Final holdout text/scores do not
enter this process and a later independent evaluation remains mandatory.
Bounds constrain profile count, logical model bytes, weight value work,
paired evaluation steps and monotonic deadline.

Codec byte counts include packed codes and FP32 scales, not containers,
headers, alignment, runtime allocations, activations or KV cache. The
candidate is an ordinary float transformer. This is genuine precision
perturbation and sensitivity measurement, but not physical quantized
execution, a GGUF format, quantization-aware backpropagation, device
performance qualification or a claim that a mixed-precision profile has
already passed on real production weights.

## Qualification

At prior head 88c990baed6aa0694d780bfe69b64695af5393ac, Jeeves source
optimization job 133050424686 reported 203 passing tests and one failing
foreground/background isolation regression. The scheduler legitimately
preempted background execution; update the regression to require two
physical calls and a successful independent interactive result, allowing
only the intended background cancellation or a completed background result.
No scheduler guard is removed.

AI-tree exact identity job 133050423330 reported the unregistered phase-V
native retention overlay. Register it and the two phase-VI training-only
modules under the existing AIFT-TRAINING mapping. No ownership cutover or
independent signoff changes. Enroll the two new regression suites in the
existing exact-head qualification workflow, including finite-difference
gradients, weighted Gram-vs-dense norm, frozen base equivalence, cancellation,
durable candidate staging/sidecar, packed code validation, paired native
precision trials and combined-interaction holds.

The complete final tree still needs successful exact-head CI, full
architecture and security gates, independently reviewed datasets, production
native/GGUF/hardware/Windows/WSL2 capacity and quality evidence. No production
training run, deployment, GPU acceleration, measured gain or merge is claimed.
