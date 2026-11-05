# Jeeves live native pressure supervision — local laptop protection

The native GGUF child now has an optional **parent-owned, real Linux/WSL2
resource pressure monitor**. It complements (and does not replace) the
existing capacity reservation, isolated inference deadline, source/rights
lease and SQLite transaction-custody planes.

The monitor is configurable in the Jeeves desktop under **Protect active
native GGUF child against observed host/cgroup/disk pressure**, enabled
by default in the interactive GUI. The library `DesktopConfig` defaults
this flag off for backwards-compatible source-only clients; a caller must
explicitly enable it in that API.

## What is measured

Once independently approved native GGUF startup has completed and the
first source-bound ready frame is verified, the desktop parent arms a
separate daemon observer of **the same isolated child process**.

- Host `/proc/meminfo`: actual available physical RAM, not synthetic
  VRAM or swap capacity.
- Process cgroup v1/v2: actual memory headroom under the process's
  effective memory controller; a container/WSL2 limit may be much smaller
  than host RAM.
- Private SQLite state filesystem: `statvfs` free allocatable storage
  for the actual state directory.
- Native child `/proc/<pid>/statm`: resident CPU memory in bytes, with
  `/proc/<pid>/stat` process start-time identity checked before and after
  each sample. A recycled PID is not trusted as the original native child.

The monitor never interprets source-code text, spawns helper processes,
loads another model, calls cloud APIs or imports GPU drivers. A real
GPU/VRAM monitor and hardware-specific offload governor remain separate
unqualified capabilities.

Default operator thresholds are 512 MiB free effective RAM, 256 MiB
private state storage, and a native RSS ceiling of 95% of the active
capacity budget. The sampling interval is 500 ms. The typed finite policy
can be configured by the operator within defined safety bounds.

## Runtime actions

The first observation must be healthy; otherwise native startup is
held. Subsequent pressure is evaluated with two consecutive critical
samples by default (a short transient may recover). If a lower RAM or
disk headroom threshold persists or process RSS exceeds its budget, the
monitor asks the **parent** to revoke that exact isolated child. A changed
PID epoch or repeated missing/unparseable telemetry is also terminal.
There is no unattended native retry or model fallback.

A revocation after a private task was submitted has an **uncertain
native/SQLite outcome**. The UI preserves the request/run ID and the
operator must inspect authoritative SQLite history or a sealed durable
checkpoint. The monitor cannot assume that a killed child did not
commit a model effect. Cancellation here is process termination; it is
not yet evidence that every native GPU/CPU cancellation behavior is
qualified.

The **Host pressure status** action reports recent measured RAM, cgroup,
disk and native resident bytes, plus a finite pressure reason when
applicable. It never includes prompt text, model file locations,
signing keys or path names. It explicitly sets
`device_qualified=false` and `release_certified=false`.

## Operating notes

The pressure monitor is designed for Linux/WSL2; native Windows
`/proc` and PID starttime semantics are not provided here. Do not treat
a Windows 11 source-only test as physical qualification. Missing
Linux/proc/cgroup capabilities while the guard is enabled are **holds**
rather than silent health passes.

This supervisor is not a native paging/offload optimizer. It cannot
alter GGUF tensor placement, GPU allocator limits, hardware thermal
governors or kernel swap reservations. Those are future, separate
capabilities requiring per-device evidence.

The application continues using the existing native `ExecutionSpine`
and signed local model. The monitor writes no additional persistent
history or resource-control database and grants the model no tools.
