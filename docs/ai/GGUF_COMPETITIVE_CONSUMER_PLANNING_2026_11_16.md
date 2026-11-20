# GGUF competitive consumer planning — 2026-11-16

This increment extends the existing operator-only planning path. It creates no
model, provider, persistence authority, runtime root or network dependency.

`python -m scripts.plan_consumer_gguf --model /private/model.gguf --auto-geometry --context 8192 --context-ladder 1024 2048 4096 8192`

Automatic geometry is restricted to known uniform GQA architectures; missing
dimensions, hybrid/recurrent/MLA architectures and mixed manual/automatic
inputs fail closed. The native context ceiling caps each estimated target.
Manual geometry remains available for separately reviewed model architectures.
The ladder is deterministic, bounded and includes remaining RAM. CPU and RAM
are supplied by the existing probe; these are not device qualification figures.
The estimator does not authenticate weights, account for all allocator overhead,
validate actual KV cache modes, load native code or prove model quality.

Competitive context: compare the same exact artifact, prompt corpus, scoring
version and hardware against Qwen, Gemma, Llama and gpt-oss candidate builds.
Record successful quality, failures, latency, peak host/device memory and
context precision separately. Large DeepSeek, Kimi and GLM systems are remote
quality reference points, not equivalent consumer hardware comparators.
No hosted fallback or automatic downloads are introduced.

## VOL-007 incremental evidence boundary

L00 existing inference owner; L01 typed bounded inputs; L02 local metadata;
L03 explicit operator-only planning; L04 no activation; L05 reject ambiguous
geometry; L06 reported remaining budget; L07 estimates separated from physical
measurement; L08 no network or provider credentials; L09 no persistent writes;
L10 regression tests; L11 architecture/source gate required; L12 rollback by
reverting this increment; L13 no qualification promotion without exact-head
tests and physical measurements. These are implementation notes, not sign-off.

Validate `python -m pytest -q tests/test_consumer_llama_budget.py tests/test_gguf_consumer_auto_geometry.py`.

## Paired local competitive diagnostic

Supply two to four existing digest-pinned greedy local deployments:

`python -m scripts.compare_consumer_gguf --profile baseline=/private/base.json --profile candidate=/private/candidate.json --repeats 2 > diagnostic.json`

The first profile is the comparison reference. Twelve public tasks test exact
UTF-8 output across reasoning, code, format and evidence grounding. Interleaved
rotating execution, matched prompts/token ceilings, repeated trials, explicit
failure denominators, paired exact wins/losses and wall-time ratios on jointly
correct tasks reduce misleading comparisons. Native receipt identity and hash
are checked; identity failures hold further work for that profile. The campaign
does not download anything, echo paths or raw prompts/results, run generated
code, confer promotion, or override existing deployment controls. Its soft
deadline prevents new attempts; it is not a hard subprocess cancellation.
The result is neither private holdout evidence nor a signed attestation.

Source tests use synthetic receipts and deliberately do not claim native model
performance. Run `python -m pytest -q --noconftest tests/test_compare_consumer_gguf.py`.

### Native pre-dispatch identity continuity

The comparator pins the raw manifest bytes as well as the canonical manifest
identity, passing the byte pin into the existing native qualification owner.
Both sync and async qualification now compare the backend's captured weight
and executable digests to the admitted manifest before inference. The
existing per-run rehash remains enabled. Paired wins/losses exclude
non-completed pairs and count those separately; they still appear as
non-successes in the full planned-attempt denominators. This is not an
OS sandbox or a signed measurement. Native device and exact-head CI remain held.

## Competitive implementation extension

- Existing paged KV manager and its byte-identical mirror now support atomic
  prefix acquisition through consumption, pin-aware migration and clearing,
  atomic pinned-capacity preflight, stable quantization identity, and bounded
  local tier pressure rebalancing. The caller must authorize the namespace
  and drain pinned use before invalidation. Physical tier movement depends
  on a conforming storage adapter; no implicit remote spill.
- Split GGUF metadata is parsed by the existing runtime reader. Unpinned single-file
  launch and planning deny split bundles. `python -m scripts.audit_consumer_gguf_shards`
  verifies 2–128 ordered SHA pins, actual file bytes, declared ordinal/count
  and tensor total with descriptor custody up to 1 TiB. This is a bundle
  intake audit; direct native activation now requires explicit ordered pins.
  Zero-tensor first shards remain unsupported.
- `python -m scripts.quantize_consumer_gguf` invokes an explicitly trusted
  SHA-pinned local llama-quantize executable with an optional pinned importance
  matrix, an allowlisted global encoding and exact anchored tensor overrides.
  Uses a private staging directory, per-file output limit, bounded wait and
  create-only candidate publication. Does not prove quantizer sandboxing,
  inspect all tensor payloads, limit arbitrary trusted child side-file totals
  or prove real device quality. Never enables requantization or activation.
- The native TinyTransformer runtime exposes cooperative interleaving and
  slot refill with per-stream replay custody and explicit aggregate KV
  admission. It is not fused accelerator batching or llama-server residency;
  caller must own exclusive runtime access.
- `python -m scripts.select_consumer_gguf --report diagnostic.json --report-sha256 <pin>`
  checks the complete diagnostic matrix and exact scorer identity, applies
  a worst-repeat quality floor per category, and ranks completed candidates.
  Different-weight alternatives are suggestions, not calibrated verifiers.
  No catalog modification or automatic deployment.

### External implementation references

- https://github.com/ggml-org/llama.cpp/blob/master/tools/gguf-split/gguf-split.cpp
- https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/quantize.cpp
- https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md

### Holds and rollback

Existing native qualification owners stay intact. All additions are explicit
opt-in except split artifact denial and KV custody corrections. Revert the
relevant increment and refresh the canonical mirror pin for rollback after
draining live use. Real GGUF quantization, native server residency and fused
batching, accelerator-specific kernel selection, live prefix reuse integration,
LoRA training, model promotion, full application routing, competitor quality,
Windows/WSL2, and source/architecture gates require independent qualification.
The source-only workflow adds all focused tests; green fixtures cannot validate
commercial model quality or physical GPU/RAM capacity.

## Executable multi-shard and physical accelerator continuation

- Native GGUF accepts an explicit ordered `model_shard_sha256` manifest list,
  retains the first shard path for llama.cpp, binds the whole ordered bundle
  as the inference model digest, charges all bytes in catalog and memory
  estimates, and rechecks descriptor-anchored SHA custody before and after
  dispatch. Owner-private POSIX directory mandatory. Other processes running
  as the same UID and system dynamic-loader closure remain trusted.
- Prepare with `python -m scripts.prepare_consumer_split_gguf`; pass the first
  shard, every ordered SHA pin, existing runtime, destination manifest,
  explicit model ID, context, GPU layers and bundle byte limit.
- `python -m scripts.serve_consumer_gguf_batch` launches one separately pinned
  llama-server over an owner-private Linux Unix socket, authenticates the
  child PID/UID before sending content, uses explicit GPU layers, context
  per slot, Flash Attention setting and native continuous batching. Supply
  pinned deployment/server, local prompt files and memory ceiling. Multiple
  batches reuse the same bounded session. Native reported GPU layer offload
  is required; it is not independent physical kernel/throughput proof.
- Optional same-session native slot spill uses explicit private disk root and
  byte ceiling, /dev/shm tmpfs for transient plaintext, chunk-authenticated
  AES-GCM ciphertext on disk, native save/erase and restore receipts. No
  cross-tenant or remote spill. tmpfs can swap; operators requiring no
  plaintext swap must disable or encrypt swap. Erase reclaims sequence
  capacity, not necessarily preallocated GPU memory.
- Torch native cache offloads the occupied K/V tensors to CPU with blocking
  transfer and releases active device references. It can then move the
  actual CPU tensors to encrypted disk and restore to CPU/device under
  exact scope, weight revision and byte ceilings. Allocator pools can retain
  freed backing bytes. Per-instance ephemeral keys deliberately disallow
  restart restoration of ciphertext.
- Native Torch fused equal-length batches execute batched Q/K/V projections,
  RoPE, SDPA and FFN tensor graphs with canonical independent decode/results.
  It is explicitly stateless (cache-free), with no silent CPU fallback
  in GPU mode. The native llama-server path delegates actual cached
  multi-sequence scheduling to libllama. No custom paged CUDA kernel is claimed.

Mandatory CPU Torch fixture job and private Unix child/process tests are
enrolled. Actual owner hardware and native upstream build qualification,
model tensor compatibility, GPU throughput, installed guarded application
integration, Windows/WSL2 and merge/release remain held. Local LoRA training,
adaptive reasoning and full long-context reconstruction are separate work.

## Competitive execution extension — paged kernels, reasoning, specialization

- `PagedBatchSession` owns real per-layer page pools, per-sequence
  page tables, suffix-only decoding, reclaimed page slots, overflow
  rejection and fail-closed cancellation. CUDA dispatch uses a custom
  Triton online-softmax page traversal kernel; the explicitly selected
  CPU reference is not physical GPU qualification. Existing native
  generation and replay event machinery is preserved. Paged storage
  preallocates the configured backing pool; it is not an allocator-free
  or cross-process shared paging system.
- `scripts.qualify_native_paged_kernel` executes matched single/batch
  native measurements and requires output parity, speed and latency
  floors before the trusted startup can select a measured CUDA profile.
  The profile is model, source, architecture, device and software bound.
  It is not signed third-party evidence or a guarantee on other prompts.
- The guarded native-transformer composition accepts that profile
  explicitly. The private resident GGUF session also has a guarded
  startup factory using the actual server tokenize/detokenize endpoints,
  exact prepared input custody, independent snapshot/reviewer authority,
  no unprepared inference, no operator batch bypass and no cache reuse.
  Installed application bootstrap must explicitly construct the factory;
  no default provider settings or existing installation are changed.
- Guarded adaptive reasoning tries authorized variants under an aggregate
  output-token reservation and wall deadline, then requires an independent
  evaluator with response-bound evidence and a minimum quality score.
  The existing canonical source must authorize each variant. No model
  self-rating or answer-derived authority is used.
- Native long-context reconstruction verifies immutable spool ancestry,
  selects exact lexical token spans with coverage-aware ranking, frames
  their provenance, executes the actual native model and revalidates
  storage before delivery. This is a bounded operator path, not semantic
  retrieval or proof of factual entailment.
- `scripts.train_native_lora_specialization` performs actual frozen-base
  Torch LoRA gradient training on selected native attention/FFN/output
  projections. Dataset rights/content/revision and target configuration
  are pinned; evaluation is held out, output candidate-only, base remains
  unchanged. No GGUF adapter training or external-model weight modification
  is claimed. The candidate can be merged into a separate native clone,
  not promoted to production.
- `scripts.benchmark_resident_gguf_holdout` runs distinct exact-pinned local
  models on matched resident engine settings with rotated order, operator
  holdout, output accuracy, end-to-end throughput and batch latency.
  No competitive superiority is asserted without an executed comparison.

The exact-head CPU fixture workflow includes real Torch gradient training,
paged reference tests and kernel measurement; source-only tests cover the
new guarded and reconstruction boundaries. CUDA/Triton device execution,
operator GGUF benchmark, full installed guarded application activation,
physical memory/throughput and Windows/WSL2 remain independent holds.

## Learned semantic long-context extension

The former lexical reconstruction path remains available. The explicit local
semantic profile adds actual token-level ONNX hidden states, contextual
pooling after encoding, dense/BM25 reciprocal rank fusion, parent centroid
navigation, segment-level MaxSim, exact identifier protection, neighboring
span recovery, overlap-aware diversity, and optional independent local
cross-encoder inference. Parent vectors are derived navigational features,
not generated summaries or independently verified assertions. Retrieved
evidence remains original exact source text or token IDs.

**Operator activation.** Install the optional `local-semantic` dependency
group from trusted local wheels (use `--no-index --find-links` for a fully
offline installation). Provision a self-contained token-level ONNX encoder
with rank-three `last_hidden_state` output and its tokenizer JSON, from a
trusted publisher and with reviewed license and artifact digests. The
runtime will not download models, execute remote model code, use custom
ONNX operator domains or follow external tensor references. The CPU
provider is explicit; ONNX native libraries and the pinned model graph
remain trusted executable computation, not an OS-sandboxed input.

Example semantic config (replace artifact hashes and model geometry with
actual reviewed values):
```json
{
  "schema": "skeleton.local.semantic-config.v1",
  "encoder_path": "encoder.onnx",
  "encoder_sha256": "REPLACE_WITH_EXACT_SHA256",
  "tokenizer_path": "tokenizer.json",
  "tokenizer_sha256": "REPLACE_WITH_EXACT_SHA256",
  "encoder_policy": {"dimension": 384, "max_tokens": 2048},
  "retrieval_policy": {"context_chars": 2000}
}
```
Optional `reranker` contains relative `model_path`, `model_sha256`,
`tokenizer_path`, `tokenizer_sha256`, and `policy` (one/two-column
classification logits, positive index and bounded pair count).

Start existing offline HTTP application with its normal model/database/token
arguments plus `--semantic-config PATH --semantic-config-sha256 SHA`.
No public configuration or request-body encoder selection is accepted.
The model-scoped SQLite authority verifies exact source hashes and leaves,
then stores derived vector features under source/context, model, tokenizer,
encoder and retrieval-profile identities. No stale source becomes eligible
after deletion. Cache bytes are disposable and checksummed; not a proof
against a malicious process that controls both DB rows and checksums.
This implementation uses bounded exhaustive dense search, not an ANN or
distributed archive index; existing source snapshot materialization remains
a scale limitation. Encoding and cache population happen on demand.

Native `generate_reconstructed_context(..., semantic_ranker=...)` can
select semantically relevant decoded source-token windows without lexical
overlap, optionally place strongest evidence near context edges, and pass
the original immutable source token IDs through normal native inference.
Decoded token windows are an encoder projection, not proof of lossless
reconstruction of raw original text. Output still requires independent
factual review.

**Hidden serving-engine improvements.** Paged native generation now yields
ready short/decode rows between bounded prefill quanta rather than waiting
for a long prefill barrier. An explicit trusted private session can borrow
already computed full immutable prefix pages from an active donor, retaining
reference counts and writing only private suffix pages. Sharing remains
default-off and never crosses session boundaries. The slot pool is still
preallocated; page reuse reduces redundant computation and logical occupancy,
not measured allocator reservation.

**Qualification.** `python -m scripts.benchmark_semantic_context` with
pinned semantic config and independently labeled local holdout JSON executes
paired BM25 and semantic recall/precision/MRR/nDCG, all-required multi-hop
coverage, no-lexical-overlap subset, latency and warm-cache observations.
Holdout JSON contains `documents` rows (id, sha256, text) and `questions`
rows (id, question, group, expected as [document-id, chunk-ordinal] pairs).
The report binds source and model identities and emits no raw corpus or
question text. Synthetic ONNX regression fixtures do not attest real model
quality, producer independence, end-user installation or GPU speed.

Design references: contextual retrieval (Anthropic, 2024), late chunking
(arXiv:2409.04701), RAPTOR (arXiv:2401.18059; this implementation uses
centroids, not abstractive summary trees), ColBERT (segment MaxSim inspired),
and vLLM block prefix reuse and chunked prefill scheduling.

## Scalable persistent ANN and pretrained admission

The immutable local disk ANN uses multiple independent SQLite files, random
hyperplane LSH bands, low-margin multiprobe neighbors, separately indexed
exact identifier anchors, exact cosine reranking of bounded candidates, and
thread or explicitly spawned process fanout. It does not load the full
vector corpus into RAM during queries. Every shard is hashed on admission
and checked for file identity drift before and after each query. The
manifest binds the source inventory, retrieval feature space, projection
geometry, runtime NumPy version and ordered file bytes. Incomplete or
failed shards never become a partial successful query.

Configured limits: 1–64 shards, 1–16 workers, up to 100 million indexed
leaves, up to 1 TiB index budget; these are safety ceilings, not physically
qualified storage or throughput claims. The index remains approximate:
collision buckets and candidate limits can reduce recall. The builder is
streamed per source document, but a single document is still verified and
materialized using the canonical document owner. Existing canonical source
writes and metadata snapshot scans retain their own scale limits. Process
workers are local trusted child processes, not a remote distributed cluster.

The offline knowledge library builds a generation from one SQLite read
snapshot. When the source inventory changes, the attached generation
fails closed until an explicit new generation is built and pinned. Query
candidate pointers are independently resolved against verified canonical
source slices and reranked before becoming citations. The derived index is
not a source authority. A stale immutable generation may still retain
historic derived vectors on disk; the operator must retire old private
generations when retention policy requires erasure.

### Build and attach

The `local-semantic` optional group is declared in both package metadata
surfaces. On an existing private library and reviewed local encoder:

```sh
python -m scripts.build_semantic_ann \
  --database /private/library.sqlite --model-digest MODEL_SHA256 \
  --tokenizer-digest TOKENIZER_SHA256 --config /private/semantic.json \
  --config-sha256 CONFIG_SHA256 --index-root /private/ann \
  --generation generation-001 --shards 8 --workers 4 \
  --worker-mode process --max-index-bytes 68719476736
```

Use the receipt's manifest SHA-256 with the existing offline HTTP startup
flags `--semantic-index PATH --semantic-index-sha256 SHA` together with the
semantic config flags. A private preexisting root is required. No default
installer activation or background rebuild is implied.

### Pretrained artifacts

`scripts.provision_semantic_models` supports explicit acquisition of a
fixed public catalog or import from operator-provisioned bare source Git
snapshots and exact local model files. No remote repository code is
checked out or executed. The published source commit binds tokenizer
Git blob content and the exact LFS pointer; the weight SHA-256 must match
the separate reviewed catalog. The installed retrieval runtime performs
no acquisition. Candidate config is published only after native CPU
encoder execution succeeds. Optional reranker admission also executes
the actual pair graph before publication. Runtime graph restrictions
remain enforced, including rejection of nonstandard operators and
external tensors.

Catalog: BGE-small-en-v1.5 FP32 / INT8 exports and BGE-reranker-base INT8,
from Xenova's fixed ONNX export revisions. Base model cards identify
MIT licensing; export redistribution requires separate license review.
The contextual mean-pooling implementation differs from the publisher's
standard embedding recipe and must not inherit publisher benchmark scores.

```sh
python -m scripts.provision_semantic_models \
  --destination /private/bge-package --encoder bge-small-f32 \
  --acquire-reviewed-public-models
python -m scripts.qualify_pretrained_semantic \
  --package /private/bge-package --output /private/diagnostic.json
```

Offline alternative: `--offline-snapshot /private/snapshots`, containing
each requested profile's `source.git` bare repository and `model.onnx`.
The operator must supply trusted local binaries, dependencies and artifacts.
Actual public diagnostic qualification uses repository-authored examples
with recall/precision/MRR/nDCG, multi-evidence coverage and ANN candidate
recall. It does not establish independent benchmark superiority. A
dedicated CI job acquires only public model bytes, executes local CPU
inference on the runner and publishes measurements rather than weights.
Physical CUDA/MPS, Windows, multi-host worker transport, actual large
index capacity and installed first-launch integration remain held.

## Incremental archive semantic wave

- Index v2 adds bounded sparse term postings alongside multi-probe LSH
  and exact identifier anchors. The immutable v1 generations remain readable
  under their original admitted feature and policy space. Candidate sampling
  remains approximate; no global exact BM25 score is claimed.
- Rebuilding a generation can reuse dense embeddings from a pinned previous
  generation only after exact source, coordinate, revision and span identity
  verification. New or changed leaves are encoded; deleted leaves are never
  copied forward. Full shard bytes are rewritten; this is incremental
  embedding reuse, not an in-place mutable ANN update.
- The existing disk-spilled file library has an explicit archive semantic
  adapter and CLI (`python -m scripts.semantic_archive`). It uses bounded
  leaf/halo windows and source verification within SQLite read snapshots.
  Resident SQLite substring operations can still consume SQLite-side memory.
  The disk-chunk path avoids assembling a document in Python. Query
  verification still scans selected complete sources and is budgeted.
- Managed generation publication uses the canonical chat SQLite store
  (`scripts.build_semantic_ann --managed-refresh`). The generation journal
  fences publication against both source watermark and active revision.
  Existing live HTTP startup may select `--semantic-index-root PATH` with
  the pinned semantic config. Interrupted jobs stay inactive; explicit
  operator recovery can fence an abandoned job. No unattended scheduler
  or automatic deletion of old private generations is implied.
- Optional `--semantic-multihop` expands bounded literal bridge terms from
  verified sources, evaluates clause facets and diversifies evidence.
  It shares the canonical grounding scope and retains original citation
  identifiers. It does not prove factual entailment or grant authority
  to retrieved instructions.
- One request-bound query embedding is reused across ANN, reranking and
  excerpt selection. Physical-memory/CPU admission can reduce concurrent
  local workers, never the required shard count. Logical admission estimates
  do not guarantee a native allocator's peak or enforce a hard OS memory cap.
- A new actual disk-scale diagnostic compares approximate candidates with
  streamed exhaustive cosine ranking over deterministic synthetic vectors.
  CI exercises 2,048 entries, not the 100-million-entry operational ceiling.
  Measurements include disk bytes, build time, admission time and recall.

Previous-head evidence (`0dfd95e944e3c3311f7a7019b5f5c550b5a44dba`,
Actions run 43795294031, job 133062712520): actual public pretrained BGE CPU
qualification passed. On the repository-authored eight-question diagnostic,
semantic recall@3 was 0.9375 versus lexical 0.5625, and semantic
nDCG was 0.8430 versus lexical 0.5205. Median semantic search was about
80.45 ms versus lexical 0.178 ms. This is measured evidence on a small
diagnostic, not independent benchmark superiority or current-head evidence.
The source-custody regression on that head rejected a stale index correctly
but obscured the error in a generic wrapper; this wave preserves the
typed stale-generation error. New exact-head regression results remain
required. Frontend type errors, repository credential-fixture hygiene,
independent devices, multi-host execution, large physical capacity and
installer rollout remain outside this qualification.


## Native placement and disk-query efficiency continuation

This stacked wave retains the parent's authenticated sharded GGUF, private
resident process, privileged application guard, encrypted KV spill, paged CUDA
and learned semantic source-bound evidence. No activation permission changes.

- Resident policy now admits explicit, bounded prefill thread counts (checked
  against host CPU affinity), NUMA placement, layer/row multi-GPU modes,
  positive relative split weights and a compatible primary GPU selection.
  Reviewed Qwen2MoE expert offload and GPU expert cache or reviewed dense
  Llama/Qwen2 FFN offload are mutually exclusive. Extra GPU expert cache bytes
  count toward the same conservative logical memory ceiling. Unknown
  architectures do not gain these controls. Experimental tensor splitting,
  remote device addresses and arbitrary argument injection remain unavailable.
- The actual resident server receives typed native options at startup, not
  metadata-only hints. The default supplies no new tuning arguments.
  Unsupported options on the exact pinned binary fail at startup; the code
  does not probe, substitute or download a different runtime. A native
  reported offload message is not a hardware profiler result.
- Private independent tokenization requests overlap within the resident slot
  bound. Preserve transport peer identity, bounded reads, declared-length
  completeness and rejection of expired results. Socket/OS scheduling still
  cannot be advertised as a strict hard total-request deadline.
- Disk ANN reads candidate rows in exact-order chunks of at most 128 IDs,
  reducing SQLite statement overhead while preserving per-vector float32
  cosine operations, deterministic ordering, allowed-source restrictions,
  immutable shard checks and complete fanout requirements.
- The existing holdout CLI has a new same-weight tuning mode. An explicit
  owner-provided JSON matrix is SHA-256 pinned. Example matrix:
  `{"baseline":{},"prefill":{"prefill_threads":4,"batch_tokens":1024,"microbatch_tokens":256}}`.
  Use one `--profile`, `--runtime-variants`, `--runtime-variants-sha256`
  and `--baseline baseline` with the existing pinned holdout and resident
  server arguments. All variants retain identical admission envelopes.
  Repeat order rotates. Candidate review requires exact paired response
  text/token/stop parity, a measured throughput floor and a p95 latency
  ceiling; no automatic activation or promotion. Reports include model,
  engine, library, profile and holdout identities and exclude raw answers.
- Focused source regressions cover invalid placement, fixed flags, chunk
  ordering/statement count/fail-closed missing rows/deadline, paired parity,
  tail latency and admission-envelope drift.

No comparative throughput measurements, physical GPU/multi-device/MoE
qualification, default installer changes, third-party SOTA certification,
large archive capacity certification, merge or release are claimed.
