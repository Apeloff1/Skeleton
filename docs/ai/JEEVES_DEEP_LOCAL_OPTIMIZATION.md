# Jeeves deep local optimization — phase IV

This phase changes actual local execution paths rather than adding another
provider or parallel inference controller. Historical phases remain staged
in the same draft. No model weights, benchmark result, GPU residency claim,
release permission, or external inference dependency is introduced.

## A. Native CPU attention and sampling

The existing TinyTransformer cached decode no longer projects the whole KV
bank into separately sliced per-head matrices per token. Context-only cached
MHA calculates exact scaled-dot-product attention directly in the existing
full-width cache. It retains only one head's scores and probabilities at a
time. The public attention/weights API and training backward path remain
unchanged; no sparse/approximate attention or changed weight architecture is
claimed. Cancellation polls during long heads, with the original partial-KV
reset boundary still responsible for cleanup.

The stochastic sampler uses a bounded heap for small top-k subsets; larger
subsets continue using the stable sort. Equal probabilities preserve lower
token-index precedence. Seeded sampling and probability filtering retain
the original normalization and RNG trajectory. Source and governed Cortex
mirror are byte-identical at this increment.

The teacher-forced logprob path computes only the requested token probability
instead of allocating every normalized vocabulary probability. It preserves
the historical log floor and summation order. Optional interruption is
forwarded through real native graph work so training deadlines can be
observed during an expensive sample.

The CPU context-only algorithm reduces temporary allocation, but a Python
indexed loop may be slower than a sliced zip loop on some hosts. Measure
both latency and peak memory before claiming a speedup. No full-production
GGUF improvement follows from tiny native-source tests.

## B. Private CPU prefix retention

NativeConversationSession accepts an explicit prefix_cache_bytes=0 (default
off) or an operator-specified positive retention ceiling. This is the
repository-owned CPU transformer, not llama.cpp's independent process or a
GPU tensor cache.

- Same session, exact token prefix and unchanged model, tokenizer, runtime
  limits, architecture and device binding are mandatory.
- Reuse only cache origin with next_position equal to token count. If a
  learned/window-shifted origin is incompatible, recompute normally.
- Detach before execution. Failure or history mutation cannot publish
  retained partial state. A fork copies tokens, not KV. Restore and stream
  entrypoints do not copy an idle bank.
- Apply conservative Python container/scalar byte accounting, with a
  per-session operator cap and per-runtime aggregate idle cap of the lower
  of 256 MiB and runtime.max_kv_bytes, and no more than 32 idle leases.
  Weak keys do not own session references. No extra disk or cross-owner
  reuse. Clearing is ordinary Python object release, not secure erasure.
- Preserve canonical request admission, per-token model/tokenizer checks,
  device proof, generation receipt and terminal checkpoint. Active worker
  concurrency and physical allocation remain the existing runtime's
  responsibility; idle retention accounting is not a physical RAM guarantee.

The public status reports retained tokens, estimated Python object bytes
and potential previous-turn prefix reuse. It is not an attested TTFT result.
Neither the desktop GGUF subprocess nor ordinary HTTP turns are switched to
this optional API automatically.

## C. Actual private SQLite knowledge retrieval

The previous search materialized every document, every chunk and every
candidate score simultaneously. The actual OfflineKnowledgeLibrary now
verifies exact source and chunk SHA/offset custody in one read transaction,
one document at a time, and accumulates query document frequencies.
Within that same locked transaction, ranking streams the joined verified
rows without repeating the full source hash and chunk reconstruction.
Retain only top-k results (or a bounded pool of at most 48 when diversity is
enabled). Score sums use deterministic sorted term order; existing formula,
phrase bonus, stable tie-breaks, model/tokenizer filtering and citations stay
intact. No persistent query-result cache or trust shortcut across snapshots.

Duplicate write admissions still validate existing scope integrity, but
write chunks through a generator. Metadata listing and explicit source reads
no longer retain full unrelated document contents. A source's largest
individual text and selected returned source still require RAM; listing all
metadata still scales with document count. Full-scope scan remains linear
per pass; this is NOT a worldwide index or a Dragon archive storage migration.

The desktop and HTTP grounded generation paths now request relevance-gated
diversification. Keep the best ranked result and replace a redundant result
only with a nonredundant candidate of at least 70% of its score, using exact
passage bytes or strong same-revision offset overlap. No fuzzy cross-source
semantic equivalence (a negation or version change can change the fact).
Regular reference-search output retains its ranked default behavior.

This is a deliberately narrow implementation inspired by research on prefix
sharing and redundancy-aware retrieval (BatchLLM, arXiv:2412.03594, and
retrieval relevance/diversity, arXiv:2610.09412). Published benchmark gains
do not transfer to this implementation without measurement.

## D. Candidate training rehearsal

The existing governed capability sampler now avoids tied-loss duplicate
selection of the same easy/hard example and balances new specialist
coverage and subsequent hard replay across gaming, coding and AI domains.
Raw scores remain useful within a domain but cannot monopolize all remaining
slots simply because the domain has a larger loss scale. Each domain needs
two distinct admitted examples. Actual native teacher-forced scoring polls
the finite monotonic deadline; unknown scorer adapters retain their original
signature and are checked immediately after return. No heldout data is
supplied and no synthetic example or unreviewed training source is invented.
The scheduler itself changes no weights; independent candidate evaluation
and promotion still own the training/runtime authority.

## E. Local-only launch and qualification repairs

The documented llama.cpp CLI has multiple aliases for model downloads,
special remote presets, external shards/adapters and cache/state files.
Refuse the specific unpinned flags and unmanaged speculation aliases in
LlamaCppConfig.extra_args. Existing known operator chat template remains.
This prevents specific bypasses but is not a generic sandbox or proof of
network isolation. Reference:
https://github.com/ggml-org/llama.cpp/blob/master/tools/cli/README.md

Previous exact head de020bee09c365f2419fd8d6e32053d287c151e5 had:
- Sealed Context Guard run 43789664102 failed at canonical metadata/AI-tree
  parity. Log: two stale pre_move_readiness count fields. Derive 183
  governed mappings and 12 B3-owner-sensitive mappings from the actual
  live array; retain fresh-audit/cutover holds.
- Jeeves source run 43789664104 failed in Docker materialization parser
  before the optimization tests. Seven subtest failures: delimiter prefix,
  mixed quoting, unsupported or multiple heredocs, whitespace-only fake
  terminators. Use exact raw terminators, tab stripping only for <<-,
  reject unsupported delimiter syntax and preserve opaque script data.
- Previous independent browser workspace job and App Foundation E2E passed
  at that earlier head only. New commits require fresh qualification.

The existing exact-head Jeeves CI job includes fourteen focused suites,
including actual native attention/replay, private prefix retention,
streamed SQLite evidence and balanced candidate replay. Run those tests,
the Docker parser regressions, canonical architecture/tree checks,
existing native/runtime/device/installer security and full affected suites.
Keep source evidence distinct from production model/HW evidence.

## Qualification / rollback

Compare same approved checkpoint, corpus, seed and exact output token
sequences. Measure cold/warm CPU generation, long-context attention temporary
allocation, per-session prefix reuse, aggregate idle retention, lexical
retrieval wall time and peak memory at growing corpus sizes, and candidate
heldout quality. Do not equate authored tests with passing tests.
No GPU/hardware/Windows/WSL2, model-weight training, Dragon/Wiki automated
wiring, or release readiness claimed. Revert only this increment if
qualification fails; no private database schema or weight-format migration.
