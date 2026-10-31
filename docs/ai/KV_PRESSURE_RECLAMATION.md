# Pressure-aware deterministic KV reclamation

`RuntimeAdmissionScheduler.trim_retained_kv(target_bytes=...)` reclaims
oldest unpinned **retained** KV entries atomically to an explicit byte target.
Active decode state and pinned entries are protected. If they prevent reaching
the target, the scheduler raises without partial eviction. The receipt binds
evicted IDs, reclaimed bytes and the canonical post-operation snapshot digest.

`reclaim_for_headroom(available_memory_bytes=..., reserve_bytes=...)`
projects a measured OS memory allowance into that same safe reclamation
operation. Unknown measurements are rejected; no fabricated zero and no
new device reservation or persistent authority is introduced. This is
metadata-backed KV admission/reclamation, not physical tensor offload.

Tests: `python -m pytest skeleton/testing/test_kv_pressure_reclamation.py -q`.
