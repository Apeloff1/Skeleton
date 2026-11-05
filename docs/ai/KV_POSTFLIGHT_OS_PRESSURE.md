# KV post-migration OS pressure fence

The CPU-to-NVMe live tier controller now samples the real OS **after the
last physical page move**, not only before each move. A storage adapter may
block while RAM, swap, thermal or disk conditions deteriorate. A successful
adapter return cannot certify safe final headroom.

The postflight check preserves source identity, monotonic clock ordering,
maximum observation age, CPU pressure non-regression, RAM non-regression,
disk reserve and the exact bytes accounted for by this migration. Unrelated
concurrent disk loss is a hard HOLD. If the final sample fails, is stale or
is worse, the controller raises KVPressureDeferred. The journaled app leaves
the intent RUNNING for explicit operator reconciliation; it does not issue
a completed receipt or replay the already executed physical migration.

This does not provide a cross-process disk reservation, GPU/Metal/ROCm
qualification or consumer-device certification. The canonical storage
adapter must still enforce its own physical quotas and page identity.

Focused regression command (not yet executed):
`python -m pytest -q skeleton/testing/test_kv_live_tier_controller.py skeleton/testing/test_kv_migration_journal.py skeleton/testing/test_offline_kv_migration.py`
