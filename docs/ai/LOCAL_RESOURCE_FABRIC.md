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

## Four-mode Metal synchronization and multi-stream qualification

The opt-in Swift/Metal qualifier runs **real device-local GPU work** on
Apple Silicon. It exercises four distinct memory synchronization contracts
with a fixed kernel and SHA-256 proof, not mock GPU results:

1. **Serial CPU→GPU→CPU**: four rounds of CPU writes followed by a Metal
   command-buffer completion, then CPU readback; no host reads or writes
   overlap an in-flight GPU operation.
2. **Two Metal command queues**: four producer/consumer pairs with explicit
   `MTLEvent` signal/wait dependencies. GPU writes to a staging buffer on
   queue A, signals a monotonically increasing event value; queue B waits
   before reading that buffer, runs its own kernel and completes a readback.
3. **Three concurrent independent lanes**: three separate input/output
   buffer pairs are submitted before any CPU waits; buffers are never
   aliased across lanes, and results are checked after every completion.
4. **Two-way CPU/GPU shared-event handshake**: two more rounds use
   `MTLSharedEvent` GPU signals at odd values. A CPU callback registered
   through `MTLSharedEventListener` advances each event to the next even
   value, which unblocks an explicit GPU command-buffer event wait.
   The callback is bounded by a 15-second semaphore deadline. This is a
   GPU→CPU notification plus CPU→GPU acknowledgement, not passive polling.

The proof uses **13 real shared-memory Metal buffers, 17 completed
command buffers, 4 interqueue event handoffs, 3 independent parallel lanes,
2 shared-event CPU callbacks and acknowledgements and 832 verified
output values**.
All four modes must pass. The Python verifier independently calculates the
complete expected output digest and rejects missing, substituted, stale
v1, undercounted or unrecognized fields. A standalone v2 receipt can
never mark llama.cpp model/KV tensor synchronization as verified.

Run on an Apple M-series Mac with the Apple developer toolchain:

```bash
# Standalone multi-mode GPU test; does not require model weights
/usr/bin/xcrun swift scripts/qualify_metal_shared.swift

# Combine with the normal pinned GGUF host-KV backend qualification
python -m skeleton.app.offline_metal_qualification \
    --manifest /path/to/private-local-model-deployment.json \
    --shared-buffer-fence
```

The native source is `scripts/qualify_metal_shared.swift`; the Python
validation is `_validated_shared_fence_receipt` in
`skeleton/app/offline_metal_qualification.py`. The Swift process runs
without shell interpolation, with its stdout held in a private temporary
file and read at a fixed 8193-byte limit. A 180-second process timeout,
strict schema, checked output digest and source hash before/after execution
provide bounded failure behavior. macOS swap, SIP, GPU firmware and weights
are not altered.

**Scope separation:** This qualifies only the *probe's* real GPU buffer
handoffs, event signaling and command completions. It does not attach an
event, a buffer or a fence to the separate llama.cpp inference process.
Its model-scoped receipt fields remain
`driver_coherency_verified: false`,
`metal_event_fence_verified: false`,
`device_tensor_migration_verified: false`.
The independent probe evidence is nested under `shared_buffer_fence` and
must not be interpreted as model-specific KV synchronization. Actual M-series
hardware runs, native inference integration and process-failure recovery
are still required for release qualification.

Native KV diagnostic observations are bound by exact
`execution_receipt_digest` to avoid mixing the evidence from concurrent
local requests. Missing or evicted evidence fails closed.

## Concurrent local GGUF workers and continuous pressure recovery

Pinned Apple Silicon GPU local models now share a cooperative, process-lifetime
unified-memory lease ledger (`skeleton/app/offline_metal_leases.py`).
A lease is reserved **after** the prelaunch hardware check but **before**
`subprocess.Popen`, and released after the corresponding native child has
terminated and its process pipes have drained. Failed subprocess admission,
cancellation, a live resource-pressure refusal and normal completion all
release the lease. The coordinator is protected by a Python lock, so two
concurrent local workers cannot both consume the same reserved share of
physical memory.

Lease sizing conservatively combines estimated offloaded GGUF weights,
native runtime scratch, **and** KV residency against one physical RAM pool.
It compares the sum of active Skeleton-owned workers with the smaller of
current RAM and Metal recommended working-set margins. A second local worker
will be rejected when its projected allocation cannot fit, rather than
pretending that offloaded model weights and host KV memory are additive
free physical RAM. A worker can be retried when another process exits.
Direct tests exercise four concurrent workers, a fifth denied admission,
idempotent releases, recovered admission after completion and invalid claims.

The runtime additionally rechecks the Apple physical/Metal pressure guard
while generation is active (at most approximately 1 Hz), rather than
checking only before loading a potentially large GGUF. If the sealed native
profile is no longer admissible, inference is terminated and its child is
reaped using the normal typed local runtime lifecycle; no live tensor/KV
migration is asserted. A real local subprocess regression checks that the
watchdog aborts, drains, and releases the lease rather than abandoning a
running child. These safeguards do **not** increase the native model context
window or disable existing prompt/output authorization.

**Scope:** The lease ledger only coordinates **workers within the current
Skeleton Python process**. A separate Skeleton instance, a third-party
process, or another user's Metal workload is not governed by this ledger;
OS-reported working-set/physical-RAM probes remain approximate. Actual
device allocations, scheduling, Metal event signals, cache coherency and
GPU-to-host tensor movement are still controlled by native Metal/llama.cpp.
There is no system-level swap override, SIP change, external GPU memory
attestation, or model-KV page migration in this layer.

The optional Metal synchronization probe runs an immutable **private copy**
of its audited Swift source; the original checkout cannot be swapped
between validation and execution. Both the private source SHA-256 and the
bounded output receipt are checked. The four-mode Metal test and the native
GGUF host-KV qualifier still require **real Apple Silicon hardware** to be
accepted as device evidence.

## Native telemetry ownership and bounded qualifier source

The Apple Metal resource monitor releases each `MTLCreateSystemDefaultDevice`
retained Objective-C device when a sample ends, including early returns and
driver/selector failures. It also drains an autorelease pool per sample.
This matters because a long-running local generation now samples pressure
periodically; retained Metal objects would otherwise accumulate. Regression
tests mock both the native success and failure paths and require balanced
device/pool cleanup.

The optional device-qualification Swift source is read at a strict bounded
size and executed as a **private frozen copy** rather than directly from a
mutable checkout. The diagnostic process output is bounded and the result
checked against a fixed independent CPU digest. An unsigned or modified
source, a missing Apple toolchain, a non-Apple Silicon host, or unverified
model-specific synchronization cannot satisfy final release qualification.

## cgroup v1/v2 swap accounting

Linux cgroup v2 `memory.swap.max` measures swap-only bytes. The older cgroup
v1 `memory.memsw.limit_in_bytes` includes both physical memory and swap;
subtract the v1 physical memory limit to avoid double-counting host RAM as
available swap. Derive swap use from memsw usage minus memory usage. Missing
or contradictory v1 counters fail closed to unknown/zero swap capacity rather
than fabricating available virtual memory. The unlimited kernel sentinel is
not treated as a real quota. This is admission telemetry, not a swapfile or
kernel memory-configuration modification.

## Read-only staging is not a disk-spill allocation

The versioned `/v1/resources/plan` request accepts optional
`readonly_stream: true` for operator-selected, descriptor-verified mmap
reads. Such reads do not allocate a second source-sized disk copy or load
an entire source into resident Python objects, so their planning no longer
rejects a source solely because its length exceeds SQLite/WAL spill budget.
They still require measured host stream slots, bounded mmap windows and
stable source identity; I/O, cancellation and physical-memory failures
remain possible. Write/index/ingest plans retain the strict existing disk
and resident-memory admission. The evidence digest binds the read-only mode.

## Effective Linux CPU topology

The CPU scheduler now uses the intersection of observed online logical CPUs,
process CPU affinity and both cgroup v2 `cpu.max` and cgroup v1 CFS
quota/period ceilings. Fractional quotas round up to at least one executable
worker; an unlimited or unreadable v1 quota is not misread as zero capacity.
This controls admission/stream parallelism, not CPU pinning or privileged
kernel scheduling. Canonical tests cover a three-CPU affinity mask with a
1.5-CPU v1 quota and the unlimited-v1 fallback.

## Bounded read-only staging interruption

Operator-approved `/v1/resources/stage` accepts an optional finite positive
`deadline_s` for an application-level staging deadline. The canonical fabric
also accepts an in-process `threading.Event` cancellation signal for local
workers. Interruption is checked before file opening, at every bounded mmap
window, and before the final source identity check. An interrupted batch
returns no partial proof set and releases measured stream slots even when a
worker raises. This is cooperative per-window cancellation, not a guarantee
that an in-flight kernel page fault can be interrupted instantaneously.

Even read-only streaming requires two live bounded transfer windows of
measured RAM headroom before admission. A host reporting no free physical
memory is rejected instead of treating zero RAM as safe because the source
already resides on disk. The check scales with the live adaptive chunk size,
not with total source length or an arbitrary per-file limit.


## Source-bound staging manifest and offline UI

The private POST /v1/resources/stage response now includes a deterministic
ordered SHA-256 manifest digest, source count, byte count, and explicit
manifest_authenticated=false. The digest covers each verified source's
relative identity, byte count and SHA-256, not file contents or host paths.
It is a reproducible integrity identifier, **not** a cryptographic signature
or proof that an inference backend consumed the data. It cannot authorize a
GPU transfer or model tool call.

The offline web workspace exposes a guarded multi-file source-staging form.
It accepts 1–64 unique portable relative filenames, requires an explicit
operator approval, submits a bounded ten-second read-only verification, and
displays the full manifest digest for subsequent provenance binding.
Disconnect clears the selection and approval. The server independently
enforces file-path, symlink, byte-window, deadline and concurrent-stream
policy; UI validation is only an additional usability safeguard.


## Source re-verification after restart

An authenticated operator can POST /v1/resources/stage/reverify with the
original selected root, ordered relative paths, previously pinned
manifest_digest, approved=true, and a bounded deadline. The fabric reopens
each regular file with the existing path/symlink fences, rehashes every byte,
reconstructs the ordered manifest, and compares digests in constant time.
A source mutation or reordered path list produces HTTP 409, not a stale
success receipt. Missing/invalid input is rejected. This stateless recovery
requires no new database authority and never trusts an old digest alone;
it is available in the offline workspace via a separate approval control.


## Driver-measured GPU thermal hold

GPU telemetry now carries an optional driver-measured thermal limit, separate
from the current temperature. NVML uses the device's slowdown threshold when
available; Linux DRM uses hwmon temp1_max when published. No default 95 C
threshold is fabricated for unsupported drivers or Apple Metal. A device at
or above its reported threshold is excluded from GPU planning while CPU/disk
read-only staging remains available. The monitor reports thermal_throttled
per GPU; the planner reports thermal_holds and binds the count into the
deterministic evidence digest. This is advisory GPU admission, not a claim
to throttle hardware clocks or migrate an already executing GPU kernel.


## GPU thermal recovery hysteresis

A GPU admitted at a measured driver threshold is held out of new GPU
plans until its measured temperature falls at least max(2 C, 5% of the
published threshold) below the limit. Missing sensor data never clears an
existing hold, and disconnected devices are retired from the in-process
controller. This avoids repeated admit/reject oscillation during cooling;
it does not claim OS clock control, device-level isolation or persistence
across a process restart. The monitor exposes the number of held devices.


## Provider-free hardware resource CLI

The canonical offline application CLI supports a model-free hardware query:

    python -m skeleton.app.offline_cli --resource-monitor --json
    python -m skeleton.app.offline_cli --resource-monitor --json --resource-plan-bytes 1000000 --resource-streams 4

Optional --resource-root selects the local storage directory whose free-space
telemetry is measured. The JSON output uses the same versioned resource
fabric monitor and read-only plan contracts as the authenticated local API.
Unknown GPU telemetry is not treated as available VRAM. Conflicting model,
job, workspace or capability flags fail closed; invalid roots, nonpositive
stream counts and negative source sizes are rejected. The deterministic
test uses explicitly simulated hardware snapshots and is not device
qualification.


## Provider-free CLI source staging and replay

The same canonical offline CLI also supports explicitly approved read-only
source verification without a model or network:

    python -m skeleton.app.offline_cli --stage-sources --stage-approve --stage-root ./project --stage-path story.txt --json

The response includes a deterministic manifest_digest. A later invocation
can supply --stage-manifest-digest with the same ordered --stage-path values
to rehash current source bytes and reject mutation or reordering. Use
--stage-streams and --stage-deadline-s to request bounded concurrent reads.
The source count is limited per invocation for UI/CLI latency, not a maximum
total project file count; large catalogs must page their source selections.
A missing approval, symlink escape, malformed deadline or conflicting CLI
mode is rejected before claiming provenance.


## Mid-stream memory pressure recovery

Read-only mmap staging does not treat its initial hardware plan as an
unlimited resource lease. Every 16 bounded mapped windows, it re-probes
measured host RAM and requires headroom for two current adaptive windows.
If competing workloads consume that headroom, staging fails closed before
emitting a partial source manifest, releases all stream leases and records
a failed batch. The monitor exposes live_pressure_rechecks for diagnostics.
This is cooperative memory-pressure protection, not a claim to prevent
all operating-system OOM conditions or to control GPU driver allocation.


## Opt-in FIFO read-stream backpressure

The default stage and reverify operations remain fail-fast under concurrent
resource contention. The authenticated HTTP routes also accept a typed
wait_for_slot=true option with a finite deadline; the offline UI exposes a
separate checkbox. The canonical CLI supports --stage-wait only together
with --stage-deadline-s. Queued readers are admitted in FIFO ticket order
under the existing measured stream capacity, cannot be overtaken by new
fail-fast requests, and release their ticket on cancellation or deadline.
The monitor exposes waiting_stream_batches. This is a process-local queue,
not a claim of distributed scheduling or GPU kernel preemption.


## Linux cgroup-v2 memory event feedback

The offline resource fabric samples the kernel's memory.events.local file,
falling back to memory.events only when local counters are unavailable.
Cumulative high/max/OOM/OOM-kill counters are compared only against a previous
sample from the same scope; the first sample is a baseline, not a current OOM.
Invalid or missing telemetry remains unknown, never an invented zero reading.

A newly observed high/max event temporarily caps read-only staging at one
stream and vetoes shared/unified-memory GPU planning. OOM/OOM-kill deltas
reject new read-only staging and are rechecked during long reads. Counter
resets and missing samples do not erase existing holds. Recovery uses
monotonic five-second high and thirty-second OOM windows. This is cooperative
software backpressure, not GPU preemption, kernel swap reconfiguration or
proof that other processes cannot exhaust memory. The resource monitor exposes
sensor scope, observed deltas and current holds. Non-Linux platforms report
this Linux-only sensor as unavailable and retain their existing memory guards.


## Linux kernel I/O stall pressure

The same offline planner samples cgroup-v2 io.pressure (falling back to host
/proc/pressure/io) when Linux PSI is available. It parses the measured
some/full avg10 stall percentages, retaining their scope and cumulative
microsecond counters without presenting them as disk bandwidth or free bytes.
At >=15% some or >=5% full stalls, future staging is reduced to one stream.
It recovers only below <=8% some and <=2% full, avoiding oscillation; an
unknown sample retains a prior congestion hold. This is advisory cooperative
backpressure, not an OS I/O scheduler override. The resource monitor reports
whether the reading was actually measured and the current hysteresis state.
Windows and macOS remain explicitly unsupported by this Linux PSI probe.


## Linux cgroup CPU quota-throttling feedback

The controller reads v2 cpu.stat counters for scheduling periods, throttled
periods and throttled microseconds. It derives a throttled-period ratio only
from consecutive monotonic counter deltas, never from the cumulative total.
When at least 20% of sampled periods are throttled, future read-stream plans
are capped at one worker; they recover after a subsequent valid sample with
at most 5% throttled periods. Missing, reset or inconsistent counters cannot
clear an existing hold. The monitor reports whether the sensor was measured,
observed delta ratio and transition count. This is a CPU scheduling hint, not
an OS quota modification or a claim of universal platform support.


## Host swap-page churn protection

Linux /proc/vmstat pswpin/pswpout counters are sampled as host-wide page
traffic, never as free RAM. Consecutive monotonic counter deltas and the
measured OS page size yield a byte-per-second swap churn rate. When that rate
exceeds 0.2% of measured physical RAM per second, future source staging is
limited to one stream; a subsequent rate below 0.05% permits recovery.
Missing telemetry and counter resets preserve an active hold. This policy
never changes system swap or assumes host traffic belongs to Skeleton alone.
On platforms without measured page size or Linux vmstat, the sensor remains
unavailable rather than substituting guessed capacity. The resource monitor
exposes the actual observation scope, rate and backpressure state.


## Linux CPU/SOC thermal trip admission

Read-only Linux sysfs CPU/SOC thermal zones expose measured temperatures and
kernel trip points where available. Only a valid passive/hot/critical trip
can trigger a CPU thermal hold; no universal 90-degree threshold is invented.
A measured trip caps new source staging to one stream until every observed
tripped CPU zone cools at least five degrees below its own trip. Missing
trip metadata, unknown sensors and non-Linux platforms remain explicit
unknowns and cannot erase a prior measured hold. The monitor exposes each
source zone and its trip measurement, not an asserted CPU package temperature
on unsupported systems. This does not change firmware fan/thermal policy.
