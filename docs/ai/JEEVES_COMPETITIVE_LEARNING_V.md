# Jeeves competitive learning and runtime efficiency — phase V

This increment extends the native optimizer, existing candidate-training
worker and local inference owners. No new hosted provider, runtime service,
model download, permission authority or production weight change.

## Native and GGUF sampling integrity

LocalInferenceRequest has exposed temperature, top-k, nucleus probability,
minimum probability and repetition controls. The native adapter discarded
these controls and hard-coded greedy generation, and the GGUF command
used only its deployment temperature. Both now propagate explicitly
non-default sampling requests through the actual backend path.

For backward compatibility an all-default request retains existing native
greedy behavior and the GGUF deployment's pinned sampler defaults. This
means the request's default temperature=1.0 is a compatibility sentinel
when every other sampler field is also default: it is NOT an unconditional
request for stochastic temperature-one decoding. Explicitly non-default
profiles use the request's value. Native rejects top-k outside vocabulary;
GGUF rejects top-k outside the CLI integer range and conflicts with known
pinned extra-argument sampler options. Native speculation remains greedy
only. Execution-profile schema v2 separates results from previously
mismatched v1 decoder receipts. No claim of cross-backend token equivalence.

The CLI path is source-qualified only; exact flags and backend sampling
order must be independently verified for the pinned version. The legacy
generic extra-args interface is not asserted to be a complete sandbox.

## Token-linear optimizer preparation

Historical TinyTransformer.fit materialized each overlapping context
window before its first SGD update. It now retains tokenized sequences
once, computes the exact same total optimizer steps, and materializes one
context window at a time. Same order, cosine schedule, targets and hard
loss, with cancellation checks before and after each optimizer update.
This reduces window preparation storage from proportional to total
tokens times context length to proportional to total tokens plus a single
window. Training activations and model parameters remain separate memory
consumers. The governed Cortex mirror is kept byte-identical.

The real shadow trainer observes idle admission during tokenization and
optimization, stops after preemption, and rechecks champion identity
before and after candidate artifact publication. A partial interrupted SGD
update is never promoted, but a failed publication/custody step can leave
a private content-addressed candidate artifact for existing recovery.
Cancellation latency is bounded by a single optimizer step only to the
extent that the underlying graph finishes; it is not hard real-time.

## Real confidence-gated teacher retention

The canonical CPU transformer supports an additional hard/soft target
gradient. For each authorized training target t, the candidate uses
q = (1-alpha) one_hot(t) + alpha p_champion, then dlog = p_candidate - q.
It shares the existing transformer backpropagation and clipping. Unit
temperature only; no second hosted/foreign teacher. The original
supervised update remains intact and the default training policy remains
unchanged.

ShadowNativeTrainingPolicy.teacher_retention_ppm defaults to 0 (disabled).
An explicit value 1..500000 activates the existing shadow trainer's
teacher-assisted local training branch. Teacher target probability must
meet teacher_min_target_probability_ppm (default 100000); otherwise the
candidate receives an ordinary hard-label SGD update. Confidence is a
heuristic, not a guarantee of teacher correctness. Exact aligned token IDs,
model/checkpoint lineage, lawful materialized corpus, CPU graph, idle
lease and bounded step counts are mandatory. The champion is verified
and never receives SGD; the candidate is cloned. The optimizer receipt
includes teacher identity and actual soft-target step count. No heldout
samples or heldout-driven training selection are used.

This is executable candidate-only self-distillation/rehearsal; no actual
production checkpoint has been trained, evaluated or activated by this PR.
It does not claim a pretrained model reaches frontier model quality.

## Independent retention evidence

native_retention_evaluation.evaluate_retention runs the real canonical
next-token inference graph on separate pinned champion and candidate
runtimes using identical non-sliding heldout token prefixes. Requires
explicit lawful evaluation rights, exact dataset revision, independently
provided complete training inventory, fixed tokenizer and architecture,
bounded cases/work, critical cases and monotonic deadline.

Measurements include per-case next-token negative log likelihood,
next-token accuracy and forward KL divergence of distributions.
Apply critical-case top1 regression holds, both per-case and
token-weighted capability NLL holds, and global KL drift hold. Publish
existing ImprovementAxis records for per-capability accuracy to the
independent evaluator. The report is not a signed mirror decision or
promotion authority; rights provenance, safety, rollback, independent
evaluation and deployment admission remain external to this module.

Materialized train and heldout texts are screened for exact bytes,
normalized token identity, word-shingle Jaccard and containment. The
screen builds only heldout postings, uses full shingles (no probabilistic
lookup) and holds on input/work-budget exhaustion. Complete bounded
training inventory is required, not a sampled substitute. It cannot
detect all paraphrase, translation, semantic leakage or unreported source
data. Short nonidentical cases may escape shingle matching, and repeated
boilerplate may conservatively cause review holds. At most 4096 training
and 256 heldout examples are accepted per screening call; larger complete
corpora need a separately qualified sharded audit.

## Canonical checkpoint working memory

Large native weight graphs use incremental canonical JSON digest/byte
counting rather than a second monolithic serialized graph. Canonical
UTF-8, sorted keys, compact separators and finite float rules are unchanged.
Small graphs retain the fast conventional serializer. Shape validation
and actual current-byte hashing are still mandatory; admission and
per-token graph checks no longer serialize the same copied graph twice.
The model weight snapshot itself is still materialized, and APIs returning
a full checkpoint JSON string still allocate that string. This is a memory
improvement; Python incremental encoder can be slower than fast C encoding
on some hosts, and no speed result is asserted.

## Qualification repair

Previous exact-head 5fe94dcf05ff9dfee1347780db33ceef0e520b3c:
three independent AI-tree gates failed with identical four blockers:
object_audit.current_mapping_count, validation_state mapping counts,
missing top-level skeleton/admission classification, pending implementation
statement count. The live mapping array contains 183 entries and the
native owner array 181. Classify the existing repository writer lease as
retained outside the AI runtime; synchronize current counters and preserve
historical audit evidence and all unsigned cutover holds. No validator removed.

Sixteen focused test modules now belong to existing Jeeves source
qualification. New regressions cover actual CPU soft/hard gradient
equivalence, champion custody, preempted candidate work, retained
distribution evaluation, shingle screening, unchanged checkpoint hashes,
optimizer order, native sampling and GGUF command construction. Run
the full existing architecture, source, security, installer and device
qualification on the final tree. No executed test result is represented
by this document. Native production GPU/GGUF/Windows/WSL2, actual
training-corpus quality and physical capacity remain separately held.
Rollback: revert this increment, keep the approved checkpoint and
training manifests; no database schema or weight format migration.
