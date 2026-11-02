# Linux RAM / cgroup-v2 memory envelope (Studio C)

`python -m skeleton.ai.model_runtime.long_context_cli --root /unused --tokenizer-digest <64-hex> head-observe-memory --request-bytes 1048576`

This command never opens a spool, allocates memory, or starts inference. The
result is a **non-authorizing, read-only diagnostic**. Linux-only POSIX
descriptor-relative reads reject symlinks, oversized pseudo-files, changed
inodes, and replaced root directory names. Two bounded observations compare
host total, cgroup limits and high watermark. Host available memory is
minimized and cgroup usage maximized across both samples. A configurable
reserve is subtracted once from the tighter of those observations.

Missing, unbounded, malformed, non-monotonic, or inconsistent telemetry
produces `state=hold` and zero headroom. In particular, `memory.max=max`
is not treated as a device qualification. The checksum is a correlation
digest, not an authentication signature. Backend authorization, live
memory reservation, per-principal quota, pressure/thermal/energy checks,
KV coherence, and durable spill bounds remain mandatory separately.
No GPU/M-chip, Windows, multi-process, or crash-restart qualification
is asserted by this observation.

Focused contract tests: `python -m unittest tests.flgb.test_long_context_memory_envelope`.
Exact-head CI is required before release; this document does not claim it passed.
