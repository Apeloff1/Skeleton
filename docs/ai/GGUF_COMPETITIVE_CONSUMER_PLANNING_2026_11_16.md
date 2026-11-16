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
