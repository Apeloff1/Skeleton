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
