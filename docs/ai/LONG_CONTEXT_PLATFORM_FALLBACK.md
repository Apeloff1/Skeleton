# CPU-only offline platform fallback diagnostic

The platform fallback observer is a bounded, process-local state machine:
hold, warming, cpu_candidate. It consumes repeated conservative host PSI,
cgroup-v2, and event-counter observations; unknown thermal, energy, memory,
CPU, event or clock evidence forces a hold. A pressure change revokes the
candidate and imposes a cooldown. A fork, restart, closed observer or
changed stream/principal/resource request cannot inherit safe observations.

GPU and Apple Silicon remain unqualified even if the host OS matches.
A cpu_candidate is a read-only suggestion, not a CPU lease or permission
to move KV tensors, allocate unified RAM/VRAM, run inference, or spill to
disk. Live backend authorization, tokenizer and model identity, checkpoint
generation, CPU/memory quota, disk safety and policy checks remain required.

The CLI head-platform-fallback command is deliberately one-shot and
never opens the token spool. It cannot independently establish multiple
normal samples or device readiness. Output contains only stream digest,
pressure state, requested device, candidate label and non-grant flags.
