# Jeeves native startup — live RAM, cgroup and licensed-source admission

The first usable offline laptop needs a guard **before the GGUF loader**,
not just a warning after a model exhausts memory. The desktop now adds
an independently checked, read-only, *just-in-time* native preload
admission when **Protect active native GGUF child against observed
host/cgroup/disk pressure** is enabled.

This is in addition to the existing operator-approved installed-source
rights/manifest check, model weight hash verification, capacity reservation,
native child isolation, SQLite custody, and the post-start RAM/disk
pressure monitor. It is not a new model runtime, cloud provider,
virtual-memory allocator, or hidden memory store.

## Actual startup sequence

1. The UI collects the exact **model root**, private SQLite root,
   context/output token ceilings, CPU threads, GPU layers, inference
   deadline and capacity reservation.
2. When the operator enables host pressure protection, the UI adds
   `--enforce-preload-safety` to the trusted native subprocess arguments.
   The child's parser rejects unknown options and refuses startup without
   explicit `--approve-native`.
3. **Before calling `activate_checked`**, the child rereads the original
   installed GGUF source manifest and checks the installed content and
   original rights-declaration approval. It never treats source-only
   inspection as independent legal rights proof.
4. It measures real `/proc/meminfo` RAM and the private SQLite
   filesystem's available bytes, then observes the process's actual
   cgroup memory headroom, CPU quota and available CPU affinity.
5. A conservative finite working estimate includes actual installed
   model bytes, bounded native scratch (at least 512 MiB), estimated
   KV-context memory that grows with requested context length, and
   per-CPU-thread scratch. It reserves at least 1 GiB or one-eighth
   of effective available RAM for the operating system.
6. Admission is refused if measured RAM, effective cgroup headroom,
   disk floor, CPU quota or the operator's original capacity budget
   cannot hold that estimate. *Swap and unmeasured GPU VRAM are never
   counted as free RAM.* Selected token/thread/model sizes are never
   silently changed.
7. On a feasible shape, the exact existing `activate_checked` source
   fence launches one isolated GGUF child and SQLite owner. The
   preflight snapshot is bound to the actual activated model SHA-256
   **before a new chat session is allocated**.
8. The child's ready frame includes only finite observation quantities
   and source identities. The desktop parent reconstructs and validates
   every typed field, the original requested context/output/threads,
   GPU layer request, capacity budget and actual active GGUF digest.
   Missing, mismatched, forged or unexpected admission metadata holds
   the startup instead of giving the UI a false green status.
9. After native readiness, the separate live pressure supervisor
   monitors the actual child at configured intervals. A running process
   can still be terminated on later pressure without reissuing uncertain
   native work. The original source/rights lease and SQLite commit
   checks remain responsible for every model-generated result.

## What the memory estimate means

The gate is deliberately **conservative but not omniscient**. The
local model's actual attention geometry, allocator fragmentation,
GPU-driver memory and transient native tensors still require real
device qualification. The gate does not assert that the entire GGUF
will definitely fit after it is accepted; it prevents known impossible
loads without relying on obsolete advisory settings.

An operator choosing 131,072 context tokens will face a much larger
KV estimate than a 2,048-token laptop session, rather than having
context declared free. A cgroup-limited 2-core/4 GiB process cannot
inherit a host machine's much larger unconstrained resource budget.
A source package whose rights approval or actual model bytes are
unavailable cannot skip straight to native inference.

The existing **Suggest measured CPU/RAM profile** UI can still
offer an advisory conservative profile. It does not authorize an
inference; the preload guard **reobserves** actual resources immediately
before startup.

## Status and qualification

The preloader's response reports only measured quantities and
`physical_device_qualified=false`, `gpu_vram_verified=false`,
`real_native_generation_executed=false` and
`release_certified=false`. It does not open private prompts, read
SQLite history, invoke native generation, start model tools or execute
shell commands.

For a source-only API caller the guard remains an explicit opt-in
for backwards compatibility. The interactive desktop already
enables its host pressure monitor by default, so protected desktop
startup now includes both pre-load and live-child resource gates.

The target laptop must still provide a genuinely installed and approved
GGUF, a measured Windows 11/WSL2 device test, real persisted SQLite
replay, native process cancellation, GPU/memory pressure and all
required exact-head security and release gates before consumer
readiness can be claimed.
