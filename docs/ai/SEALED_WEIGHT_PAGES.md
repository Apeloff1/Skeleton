# Sealed shared pages for offline model weights

`WeightShardStore.open_sealed_pages(plan_digest, model_identity=...,
max_bytes=...)` exposes verified local weight shards through Linux memfd
objects with F_SEAL_WRITE, F_SEAL_GROW, F_SEAL_SHRINK and F_SEAL_SEAL.
All shards are copied under an explicit aggregate RAM budget, hashed again
after source streams open, sealed and mapped read-only before any page is
published. The context manager closes mappings and descriptors on exit.

This is ephemeral, immutable host memory; it is not GPU VRAM, an M-chip
physical-memory modification, a model decoder or a new persistence owner.
Unsupported kernels and non-Linux systems fail closed rather than silently
claiming immutable shared-page guarantees. Device qualification remains
separate. No network or provider credentials are involved.

Run `python -m pytest skeleton/testing/test_sealed_weight_pages.py -q`.
Linux memfd tests require actual kernel support; skipped platform tests are
not evidence of successful device qualification.
