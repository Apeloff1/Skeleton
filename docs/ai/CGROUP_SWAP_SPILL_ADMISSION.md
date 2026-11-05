# Cgroup-v2 swap headroom: advisory spill gating

The Linux live-stream sampler now measures current process cgroup-v2 swap
usage and its swap ceiling through descriptor-pinned, bounded reads. It samples
both endpoints twice, walks each process ancestor and rejects membership
changes, symlinks, partial controller files and malformed counters.

A finite limit with more than the reserved margin is **advisory** evidence
that a separate, authorized spill manager may consider spill. It is not a
reservation or permission to write, migrate KV, allocate GPU memory or bypass
RAM/thermal/disk admission. Unknown or unlimited swap never grants measured
spill capacity. A swap-disabled cgroup does not halt CPU-only inference; it
limits stream fan-out and records a `cgroup_swap_spill` pressure hold.

Every actual spill must re-probe and independently enforce disk quota, tenant
authorization, encryption/key custody, publication and crash recovery. The
probe is not a hardware/device qualification. Synthetic tests cover limits,
concurrent counter changes, nested membership and malformed controllers.
