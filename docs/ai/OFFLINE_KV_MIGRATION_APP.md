# Offline application KV tier migration integration

`OfflineKVPageTierService` is the app-callable boundary for the canonical
CPU-to-disk KV pressure controller and its write-ahead migration journal.
The application provisions a securely opened exclusive SQLite connection,
a separate journal key, a trusted KV storage adapter and the selected
storage volume. Production bootstrap uses the canonical OS sampler only.

`plan_live()` returns a bounded typed `TierPlan` and payload-free
`OfflineKVMigrationStatus`. `apply_once()` rechecks live headroom and
commits a signed per-move receipt. Any adapter rejection or uncertain
outcome fences the journal, so the app must not retry that plan.

Test-injected sensors are permitted only with an explicit simulated flag.
All statuses leave `gpu_device_qualified=False`. CPU pressure is not a
proxy for free GPU/Metal/unified memory; no real hardware certification is
implied. The app must separately enforce physical disk quotas, permissions,
trusted adapter provenance and operator recovery for RUNNING journal rows.
