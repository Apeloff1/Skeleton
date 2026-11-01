# Bounded cgroup-v2 diagnostics (Studio C)

`python -m skeleton.ai.model_runtime.long_context_cli --root <spool> --tokenizer-digest <64-hex> head-observe-cgroup` reports a payload-free, read-only diagnostic. It does not create or open the spool.

The observer descriptor-opens each cgroup ancestor without symlink traversal, reads bounded pinned CPU/memory PSI and memory.current/memory.max, verifies inode and mutation metadata against the named files, then reopens the directory to fence replacement. Malformed, missing, linked, oversized, unbounded or changing counters hold closed. A memory limit of `max` produces unknown memory safety; a finite limit at 85% or 95% produces elevated or critical pressure. PSI severity is combined conservatively with memory utilization.

The observed cgroup root is **not attested to be the process's active cgroup**. Counters are not an atomic multi-file snapshot. A normal result does **not** grant admission, qualify CPU/GPU/M-chip hardware, certify thermal or energy safety, or establish an execution lease. All consumers must independently verify authorization, current process membership, device eligibility and live telemetry before allowing work. Unknown thermal and energy states remain holds. No disk, network or model inference operation occurs in this command.

Regression fixtures: `tests/flgb/test_long_context_cgroup.py`.
