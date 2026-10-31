# Offline reclaim-pressure admission

The canonical local resource fabric observes Linux cgroup v2 `memory.stat`
(`pgscan`, `pgsteal`, `pgmajfault`) and falls back to explicitly labeled
host `/proc/vmstat` when cgroup counters are unavailable. On macOS and
Windows the signal remains **unavailable**, never a fabricated zero.

Kernel page-scan and major-fault deltas are normalized by measured physical
RAM pages and monotonic elapsed time. Sustained inefficient reclaim or high
major-fault rates imposes a hysteretic pressure hold: only one concurrent
read-only staging stream is admitted, and advisory shared-memory GPU
eligibility is withheld. Three independent quiet intervals are required for
recovery. Missing telemetry, counter resets and cgroup/host scope switches
never clear an existing hold. Other existing RAM, disk, thermal, cgroup OOM,
CPU and I/O guards remain authoritative.

This signal is **observational**. It does not reserve physical RAM, transfer
GPU pages, prove Metal/ROCm/CUDA coherence, or replace backend-owned inference
admission. Resource plan and authenticated loopback resource-monitor responses
include a payload-free `reclaim_pressure` receipt with source and normalized
rates; source paths, model bytes and private prompts are not included.

Focused tests use labeled synthetic counters. Device qualification must
exercise actual cgroup memory pressure and measure p95/p99 throughput,
cancellation and recovery on each target platform.

The pressure hold constrains the **aggregate** in-process stream-slot budget,
not only each request's stream count. Already running streams are allowed to
finish or cancel; new work cannot overbook the held capacity.
