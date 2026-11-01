# Hierarchical Linux cgroup-v2 memory admission

The canonical live CPU sampler now checks the **current process** unified
cgroup membership rather than treating the mount root as the process budget.
Every ancestor from the cgroup mount root to the leaf is sampled using
descriptor-relative no-follow directory traversal. The tightest finite
headroom wins, and a hard hold at any ancestor prevents dispatch. A changing
membership, missing ancestor capacity, malformed proc membership, symlinked
directory, partial memory controller or counter read failure aborts admission.

This is an observational, non-atomic kernel sample: concurrent allocations
can race the read. The native backend still enforces per-token re-probing,
execution deadlines, bounded RAM/KV, tenant custody and no automatic retry
after uncertain outcomes. It does not reserve RAM, certify GPU/M-chip hardware,
or modify cgroup limits. Noncanonical fixture paths are probed as one
explicitly selected directory; no test path can impersonate proc membership.

Sampling retains a single descriptor-pinned ancestor chain and checks the
leaf inode against a freshly resolved canonical path before admitting work.
A detached or replaced cgroup leaf is not treated as current process capacity.
