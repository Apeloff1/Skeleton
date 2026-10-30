# Device-local adaptive resource fabric (2026-10-30)

## Scope and real execution authority

This is a **private offline runtime resource manager**, not a public-hosting quota. It
observes available physical RAM, Linux swap/cgroup swap, Windows pagefile/commit,
CPU load and quota, local disk capacity, Linux memory PSI, plus GPU VRAM when
NVML or supported Linux DRM telemetry is available. Unknown GPU memory is never
assumed to be zero-cost or available.

The new `skeleton.app.offline_resource_fabric.AdaptiveResourceFabric` provides:

- Hardware snapshots and an automatically smoothed resource-pressure score.
- Conservative deterministic admission and planning for concurrent work.
- Verified read-only, windowed file-backed memory mapping (page-cache staging).
- Concurrent local read streams with bounded windows, stable source identity and
  SHA-256 proof; source content is never returned by the status API.
- Success/failure and measured-throughput feedback for future parallelism.
- An authenticated loopback monitor and per-workload planner in the offline app.
- An explicitly approved multi-source staging route (POST /v1/resources/stage).

**The manager cannot independently allocate VRAM or establish CPU/GPU cache
coherence.** Existing inference backends own physical allocations. An eligible
GPU planning result is *not* proof of a completed transfer. This distinction
is essential for integrated GPUs: reported GTT/shared/UMA memory is backed by
host RAM and must not be added to free physical RAM or dedicated VRAM.

## Residency / dataflow

```text
Local sources
  -> operator selection and path / file identity validation
  -> live host / container / GPU telemetry
  -> adaptive planner with hard admission fences
  -> read-only windowed mmap staging (system page cache)
     -> SHA-256 proof / stable regular file identity
     -> bounded concurrent streams and throughput feedback
  -> existing offline document path:
     -> resident SQLite FTS5 if physically affordable
     -> otherwise verified SQLite chunk/FTS5 disk spill, atomic commit
  -> canonical inference backend (independent GPU ownership)
```

The Linux mmap path binds individual path components through `O_DIRECTORY`
and `O_NOFOLLOW`, and final files are opened read-only. The Windows path
re-checks canonical paths, source identity and modification metadata; it
does not claim an atomic kernel-enforced no-follow parent-path fence.

A mapped file is read-only from this process's perspective, but that does
**not** make DRAM immutable, GPU-coherent, or physically dedicated. Page-cache
eviction and swap paging are OS mechanisms; mapped pages are not a separate
hardware RAM tier. The application deliberately retains a separate disk spill
path rather than forcing heavy swapping. Runtime-side GPU tensors, KV caches,
device synchronization and DMA require specific driver/backend integrations.

## Stability and precision

- RAM, swap and PSI saturation reduce resident budgets and parallel streams.
- Fast-rise / slow-recovery pressure smoothing prevents oscillation.
- A throughput-feedback controller adjusts future read parallelism. It does
  not train or execute a model or override safety decisions.
- Disk spill only occurs when there is real free volume for SQLite/FTS/WAL
  amplification; insufficient headroom rolls back without truncation.
- Immutable content checks use SHA-256 and stable descriptors. An unknown
  source identity, invalid path or changed file is rejected.
- GPU shared host memory is *not* additive to physical RAM; telemetry cannot
  prove whether zero-copy access exists for a given activated backend.
- The resource monitor samples on explicit API requests and periodically
  while the authenticated local web UI is connected. No background agent,
  cloud upload or remote telemetry is created.

## API

- `GET /v1/resources`: private, current host/device observations, adaptive
  scores, read throughput, honest capability flags.
- `POST /v1/resources/plan`: `source_bytes` (required integer),
  `desired_streams` (optional positive integer), `requested_gpu_bytes`
  (optional), `allow_gpu` (optional boolean). Returns a **plan** not a
  driver allocation.
- `POST /v1/resources/stage`: `root` (selected directory),
  `paths` (unique relative filenames), `approved: true` and optional
  `desired_streams`. Hashes selected immutable views concurrently; only
  relative source names and proof metadata are returned. Caller must hold the
  existing loopback bearer authorization.

## Qualification not yet claimed

Full VRAM tier migration and multi-GPU prefetch requires native llama.cpp/
driver-level allocations and copy/event synchronization receipts. Actual
model tensor and KV-cache offload, pagefile optimization, cross-device
coherency and load-time model reconfiguration are **not** implemented by
this file-reader and planning layer. GPU visibility is driver-dependent.

Production acceptance requires exact-head CI, deterministic tests, device
tests under host/WSL2/cgroups, GPU device-loss scenarios, partial disk I/O
and power/thermal changes, profiling with real model weights, and replay-
verified error/recovery handling. No release hold should be weakened merely
because this controller returns a favorable plan.

## Apple Silicon M-series virtual-memory extension

`offline_resources.py` reads public macOS `hw.memsize`, `host_statistics64`
free/inactive-page observations, and `vm.swapusage` **without changing kernel
swap settings**. These are approximate observations: compression and wired
pages are not extra free RAM. When macOS telemetry cannot be read, the manager
uses its optional platform-appropriate fallback or refuses unsafe admission.

`offline_resource_fabric.py` queries Metal's `hasUnifiedMemory`,
`recommendedMaxWorkingSetSize` and `currentAllocatedSize` for an Apple Silicon
default device. A Metal budget is capped by **both** current physical memory
and the recommended GPU working-set remainder. Metal does not report a
separate GPU RAM pool on M-series chips; the computed budget is advisory,
not verified global free memory. No OS private memory cap is bypassed.

`offline_longform_virtual.py` implements real application-managed virtual
longform storage alongside, rather than inside, the macOS swapfile:
- Selected local UTF-8 inputs streamed with descriptor-based source admission.
- Private SQLite/WAL `FULL` durability, pagewise optional zlib compression,
  SHA-256 source identity, ordered per-page digest and rolling hash chain.
- Full archive/projection verification with **O(one page plus requested window)**
  decoder memory, including fail-closed corruption and unexpected page checks.
- Authenticated `POST /v1/resources/longform/ingest` (explicit approval),
  `/verify`, `/window`, and `/search`. Per-read return payloads are
  bounded by **live RAM headroom**; the archived source size is not capped.
- User-facing offline workspace to stage a selected manuscript and search
  its saved pages. Returned pages are **untrusted source evidence**, not
  silently installed as model instructions or new model context.

Metal `shared` buffers can be accessed by CPU and GPU but require proper
command completion/synchronization. A read-only host mmap file is **not**
an automatically Metal-coherent allocation. Native Metal/llama.cpp tensor
paging, KV-cache migration and verified synchronization events remain a
device-qualified backend follow-up, not a claim made by this extension.

References:
- https://developer.apple.com/documentation/metal/mtldevice/recommendedmaxworkingsetsize
- https://developer.apple.com/documentation/metal/mtldevice/currentallocatedsize
- https://developer.apple.com/documentation/metal/mtlstoragemode/shared
- https://support.apple.com/guide/activity-monitor/view-memory-usage-actmntr1004/mac

## Advanced runtime admission and long-form Merkle paging

The locally activated GGUF runtime now registers one immutable Apple-Silicon
resource preflight if Metal GPU offload was selected. Immediately before
rendering a prompt or starting the llama.cpp subprocess, the manager re-probes
physical RAM pressure and the available Metal recommended working set. If the
**existing, sealed** offload profile no longer fits, it refuses the request
without changing model identity or pretending that a live CUDA/Metal tensor can
be migrated into a swapfile. Users can retry after pressure clears or reload
their pinned deployment with fewer GPU layers. The preflight is admission
defense, not a guarantee against concurrent pressure or a GPU-residency proof.

New long-form archives atomically build a SHA-256 binary Merkle tree of
individual compressed-page **original byte** digests and page indices. A
selected page is verified by its O(log N) siblings against the manifest root.
This makes repeated chapter/page retrieval scale with the *selected* page
count, not total archive bytes. Explicit `verify` still checks the complete
original SHA-256, ordered hash chain and all saved FTS content; legacy
archives with no Merkle root continue to use full verification. The search
API explicitly states `search_completeness_proven: false`: a valid matching
page proves that page's contents, not that no other matches exist.

The trusted local SQLite archive manifest is not externally signed. An
attacker with authority to rewrite the entire archive *and its root* could
forge local evidence; for external attestations, bind the archive's source
SHA-256 and Merkle root to an independent trusted signed receipt. The current
implementation does not claim this external custody.

## Native KV-cache residency and precision (M-chip runtime)

The pinned local llama.cpp deployment supports an **explicit** `kv_cache_location`
value of `backend` (the unmodified native default) or `host`. A host value
emits the actual native `--no-kv-offload` flag; it does not copy live GPU
buffers into virtual RAM, and it does not claim the native KV buffer has a
driver-certified CPU residency or a completed Metal synchronization fence.

Operators may independently choose `kv_cache_type_k` and
`kv_cache_type_v` from `f16`, `q8_0`, or `q4_0`. These map to
llama.cpp `--cache-type-k` and `--cache-type-v`. They are omitted by default
to preserve pinned prior behavior. Changing type can affect output fidelity:
it must be a deliberate deployment decision with real regression testing,
not a hidden automatic response to memory pressure. Both flags and the host
placement directive are guarded as **managed flags**, so untrusted arbitrary
`extra_args` cannot override the machine-authorized model profile.

The Apple Silicon planner reserves physical CPU/host memory for any explicitly
host-resident KV budget **before** computing the available Metal working set.
This is one physical unified RAM pool. Under memory pressure the native
launch preflight may reject a request; it never simulates in-process GPU/CPU
migration. The config, resulting command flags and report are bound into the
local execution-profile digest and the per-run receipt.

Actual native stderr is captured with the existing bounded pipe. Recognized
`llama_kv_cache` and `llama_kv_cache_unified` CPU/device allocation log
lines are parsed into small **backend-reported** KV-byte measurements. Raw
log text is never included in durable telemetry; only its SHA-256 and the
limited parsed counters enter the inference receipt. If a host-only directive
is explicitly requested and that backend reports GPU KV buffers, the result
is rejected. Missing log lines imply unknown placement; the system **never**
converts silence into evidence of CPU residency. Even correctly parsed logs
are not driver-level attestation or independent cache-coherency proof.

A selected native runtime version must support the explicit flags. An old or
mismatched pinned executable can fail closed on unsupported arguments. The
deployment's executable checksum is the authority; Skeleton does not fetch or
substitute an unapproved runtime. Mac device testing must cover loss of
Metal memory budget, CPU-KV requests, buffer-report omissions, quantized
cache quality and exact-head rollout checks. Driver-level live KV migration,
Metal synchronization event receipts and memory-compression control remain
unimplemented, and kernel swap/SIP settings are not changed.

## On-device qualification procedure (macOS M-series)

With a user-owned, immutable GGUF and pinned llama.cpp executable already
recorded in a deployment manifest, set the manifest's `config` to include
`"gpu_layers": N` for an actual supported positive N and
`"kv_cache_location": "host"`. A model's default KV dtype remains unchanged
unless the operator explicitly selects a supported K/V type.

On the Apple Silicon device, from the project root:

```bash
python -m skeleton.app.offline_metal_qualification --manifest /path/to/private-local-model-deployment.json
```

The device qualification uses the normal offline `load_gguf_deployment` path,
executes one small bounded request, and captures the pinned model SHA,
pinned runtime SHA, execution digest and the limited backend-reported native
CPU/device KV buffer totals. It returns a nonzero status when any required
proof is missing, contradicted, not running on M-series hardware, or actual
Metal GPU layer admission is zero. It does not print source bytes, prompts,
raw stderr or secrets. The receipt is a local deterministic audit artifact,
not independent driver attestation.

`qualified_host_kv_diagnostic` means only **the pinned native backend
reported a CPU KV buffer while the chosen Apple Metal offload mode was active,
and no GPU KV buffer was reported**. It does not certify DMA, Metal event
fences, runtime tensor migration, numerical equivalence across K/V cache
types, or macOS swap modification. Test each chosen cache precision,
memory-pressure condition, interruption and process/device failure separately.

## Real Metal shared-buffer fence qualification

A **separate, opt-in** Swift/Metal qualifier performs genuine Apple
Silicon CPU↔GPU shared-memory command execution. It constructs a 64-element
read/write pair of `MTLBuffer` allocations using `storageModeShared`,
runs a deterministic GPU compute kernel, waits for each Metal command buffer
to complete, and verifies the CPU-visible output after *two* independent
CPU modifications. The native Swift source is at
`scripts/qualify_metal_shared.swift`.

Run on an Apple M-series Mac with the Apple developer toolchain installed:

```bash
# Standalone low-level shared-buffer probe; no model files needed
/usr/bin/xcrun swift scripts/qualify_metal_shared.swift

# Or combine with the existing pinned llama.cpp host-KV qualification
python -m skeleton.app.offline_metal_qualification \
    --manifest /path/to/private-local-model-deployment.json \
    --shared-buffer-fence
```

The Python validator requires an exact declared schema, two completed
command buffers, 128 individually verified values, and the **independently
computed SHA-256** expected from the fixed Metal kernel. The probe file is
hashed before and after the subprocess call and the result parser requires a
bounded JSON response. Any compiler, platform, synchronization, digest, or
backend failure returns **unqualified**; none of these paths change macOS
swap, SIP, GPU firmware, or installed model weights.

**Scope separation:** Successfully running this standalone probe demonstrates
that the *probe's* shared Metal buffers were coherent after the observed
command completions. It is not evidence that the separate pinned llama.cpp
process synchronized, migrated or paged any actual model tensor or KV-cache
allocation. The local GGUF qualification keeps
`driver_coherency_verified: false`,
`metal_event_fence_verified: false`, and
`device_tensor_migration_verified: false`. The standalone proof is saved
under a separate `shared_buffer_fence` field and must not override those
model-scoped qualification claims.

Native KV diagnostic observations are now additionally associated with
the exact `execution_receipt_digest` from the completed model inference,
rather than relying on a mutable "last request" diagnostic. The bounded
in-memory receipt map avoids confusing two overlapping local generations.
Missing or evicted evidence fails closed.
