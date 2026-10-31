# Measured KV tier pressure planner (Studio C)

The canonical `KVCacheManager` exposes payload-free, immutable resident-page
inventory and a single-page compare-and-migrate operation. The
`KVPressureTierPlanner` uses fresh, source-labelled GPU/CPU pressure and
available CPU/disk bytes to plan conservative demotion of unpinned pages.
It never reads tensor data, changes operating-system swap settings, or
pretends that a missing device probe is a measured zero.

When GPU pressure exceeds the configured threshold, pages may move to CPU
only with measured CPU headroom and acceptable CPU pressure; otherwise to
NVMe only if measured free disk remains above reserve. CPU pressure can
also trigger CPU-to-NVMe demotion. Unknown/stale measurements, pinned
pages, cooldown, unavailable adapters, or changed page identity fail
closed. Every plan binds the exact page inventory, policy, telemetry
and proposed moves with a SHA-256 digest. Apply rechecks the plan, uses
the canonical manager lock and returns moved/rejected receipts. An
adapter failure cannot be reported as a successful migration.

This is **source-level local KV resource control**, not a claim of
Apple Silicon/Metal, CUDA, ROCm, or Windows device qualification. Actual
GPU tensor transfer remains the responsibility of the installed
`KVStorageAdapter`. The regression adapter is explicitly simulated.

Focused canonical tests:

```bash
python -m pytest -q --noconftest skeleton/testing/test_kv_pressure_tiering.py
```

Before runtime activation, wire trusted OS telemetry into this planner
through the canonical local inference owner, qualify the physical storage
adapter on each supported device, and run full exact-head CI/security.
