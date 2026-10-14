# Adaptive Memory Context Plane

Skeleton now treats OS-addressable system RAM as the default hot context reservoir for large AI projects.

The capability is vendor-neutral. It discovers total and available system memory on supported platforms and, when firmware exposes physical topology, classifies DDR, LPDDR, HBM, soldered board memory, package memory, DIMM-style memory, and CXL-attached memory. Textual DDR, LPDDR, GDDR, and HBM names are parsed without a generation allowlist, so later names such as DDR6, LPDDR7X, and HBM4E do not require a new allocator.

## Allocation model

The operating system remains the owner of physical memory placement. Skeleton never attempts raw DRAM-controller access or direct access to memory packages that firmware and the OS have not mapped into the process address space.

The adaptive context plane selects a retention profile from detected capabilities:

- HBM exposed as system memory: highest hot-context retention profile.
- Soldered, board, or package memory: board-memory profile.
- CXL system memory: CXL profile.
- Recognized DIMM/system-memory silicon: system-silicon profile.
- Unknown topology: conservative host-RAM profile.

All profiles reserve memory for the operating system and shrink automatically under memory pressure.

## Context behavior

The reservoir is content-addressed, bounded, integrity checked, and optionally compressed. It does not preallocate its advertised capacity. Low-priority and least-recently-used entries are evicted first. Pinned entries survive ordinary pressure, but critical pressure may evict them because pinning is never permission to cause an out-of-memory failure.

The assistant context compiler uses this RAM plane by default for stable tenant-bound project scopes. It recognizes project_id, workspace_id, repository_id, and conversation_id scopes.

Trusted control text is never persisted into project RAM. Recalled material must pass the same expiry, restricted-data, trust, deduplication, candidate-count, and context-budget checks as live material before it can reach model inference.

This expands effective project context. It does not change a model's architectural token or attention limit; instead, a much larger project working set can remain resident in RAM while the compiler selects the best bounded subset for each inference call.
