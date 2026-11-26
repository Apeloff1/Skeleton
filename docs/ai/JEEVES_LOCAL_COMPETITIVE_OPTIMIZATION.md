# Jeeves local competitive optimization: phase III

This increment extends the existing GGUF/native inference owner. No new
hosted provider, model download, state owner, or permission boundary.
Prior phases preserve operating ceilings and add measured CPU tuning,
temporal evidence packing and reasoning economics.

## Asymmetric attention-cache precision

The existing typed llama.cpp K/V precision settings support a bounded
experimental matrix of f16, q8_0 and q4_0 choices. The logical estimator
accounts for GGML block rounding (32 elements plus scale: 34 bytes for
q8_0 and 18 for q4_0), explicit K/V dimensions, GQA head counts, layers
and known trained context. Unknown or non-regular geometry holds rather
than masquerading as a dense transformer. Logical storage is not measured
allocation, accelerator residency or a reason to decrease safety reserves.

The new kv_precision_qualification API compares exact model/runtime,
tokenizer, host, corpus and benchmark protocol. Compare the same
case, repeat, requested shape and actual output length. Capture
independent quality scores and exact target output hashes for a separate
explicit critical subset. Host RAM and device allocation are measured
separately; never add them as if they were independent on UMA.
No missing, failed or truncated comparable trial can promote a candidate.
Keep a Pareto set across worst host and device memory, median elapsed
time and minimum quality. A human chooses and re-admits an approved
manifest; nothing changes the live model automatically.

KIVI motivates investigating asymmetric key/value compression:
https://proceedings.mlr.press/v235/liu24bz.html
This implementation does NOT implement that paper's 2-bit algorithm or
claim its reported performance.

## Native single-model speculative decoding

The initial CPU-only greedy llama.cpp profile supports explicit
request-local ngram-simple, using the target model's native verification
rather than loading a second draft model. This is an opt-in experimental
profile, off by default. Existing default manifest/profile shape is
preserved. These configuration fields must all be supplied:
- speculation_runtime_sha256: exact independently verified executable
  SHA-256 matching the deployment's runtime pin
- speculation_ngram: integer 2–24
- speculation_draft_tokens: integer 1–64
- speculation_min_hits: integer 1–32
- speculation_reserve_bytes: independently measured additional host
  capacity reservation, at least 128 MiB and at most 4 GiB

Requires explicit gpu_layers=0, temperature=0 and adequate known effective
context. Initial mode excludes structured/tool output. The managed native
command emits the documented ngram-simple flags; its backend must actually
support them. No automatic probing, downloading or fallback is permitted.
Unknown backend flags fail using the existing process error behavior.
Unmanaged speculative switches, remote draft acquisition, extra model
selection, shared lookup files, synthetic acceptance flags are refused.
Both the consumer planner and GGUF memory estimator charge the separate
reserve. The original resource profile cannot change these fields.
Native performance and other admission paths still need independent
qualification, especially because launcher support differs by revision.

Native reference:
https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md
https://github.com/ggml-org/llama.cpp/blob/master/tools/cli/README.md

Before approving any speculative profile, qualify baseline and candidate
using native_speculation_qualification.Pair and actual independently
observed Trials. Pin exact target token sequence, finish reason, requested
input/output shape and actual generated count. Any changed token sequence,
failure, host reserve overrun, unmatched case, or unacceptable latency
tail holds. Require measured median improvement. A favorable verdict is
advisory operator-review evidence, not a permission token. If the native
backend cannot expose target token IDs, this exact equivalence gate remains
unqualified; decoded text is not a substitute. Benchmark cold and warm
runs separately, with pinned seeds and identical stop policy.

The request-local LocalDraftWindow is a separate bounded proposal/reference
kernel for future direct native verifier integration. Sliding token window
and bounded n-gram counts use only the admitted request. Competing next
tokens abstain; verified expensive or poorly accepted proposals shorten
future drafts and enter cooldown. Target-only results update history;
scope, prefix and pending round are bound, and output ceiling is preserved.
The Python window is not automatically used by llama.cpp or a native
transformer. No draft from it can be treated as generated output.
No persistent lookup index or cross-principal draft reuse.

## Local retrieval fusion

evidence_rank_fusion offers a bounded offline BM25 pass over the existing
verified source excerpts. Optional local semantic channels supply ordered
identities bound to the same snapshot/scope. Reciprocal-rank fusion avoids
mixing incompatible scores. Scores influence ranking only; original
source bytes, revision, claim and provenance remain intact. Exclude
withdrawn or temporally invalid records before scoring, even if a channel
ranks them first. Do not silently truncate contradictions or required
claims. prepare_ranked_request composes the ranker with prior evidence
packing and canonical LocalInputBudget. It refuses an already sealed or
mismatched request; the source owner must revalidate and seal after packing.

No embedding model, worldwide BM25 index or Dragon/Wiki auto-wiring is
created; this ranking API can consume already authorized local rank lists.
Exact full-prompt token counter and final context guard still own admission.

## Qualification / rollback

The existing exact-head Jeeves local-only source qualification workflow
now includes the optimization test suite. This is source-level regression
coverage, not production GGUF or device evidence. Preserve CI, architecture,
security, first-install, native and Windows/WSL2 holds. Run all existing
affected inference/deployment tests and canonical construction validators.
For rollback revert this increment and preserve original approved manifests,
source/model bytes, sealed receipts and private data.

Outstanding: independently observed GPU and CPU device measurements,
actual pinned CLI speculative run and target token equivalence, correct
backend support and rights, native target-verifier integration for the
Python window, Dragon/Wiki/desktop automatic wiring, true live latency,
physical tensor prefix reuse, trained weights and long-horizon quality.
