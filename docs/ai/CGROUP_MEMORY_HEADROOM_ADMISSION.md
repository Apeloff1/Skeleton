# Cgroup-v2 memory headroom in guarded offline inference

The fair-stream live sampler now independently reads `memory.current`,
`memory.max` and `memory.high` from the Linux cgroup-v2 memory controller.
It takes the higher of two usage samples and the lower of two ceiling samples.
Every counter is read through a descriptor-relative no-follow open, with a
128-byte bound and an inode-identity check. No cgroup settings are modified.

The smaller of host and effective cgroup headroom becomes the CPU stream
budget. A hard hold is issued when remaining headroom is at most the larger
of 64 MiB or 5% of the effective cgroup limit. Missing v2 controller files
remain *unknown* and therefore retain the existing single-stream,
128-token conservative admission path. Partial, malformed or unreadable
controller data fails closed; it is never interpreted as unlimited memory.

The two reads are deliberately not an atomic kernel snapshot. A racing
process can allocate memory immediately after sampling. The existing
native per-token pressure callback and the execution journal's uncertain
outcome quarantine remain mandatory. This module does not reserve RAM,
qualify GPU/Metal hardware, or prove safe cross-process scheduling.
