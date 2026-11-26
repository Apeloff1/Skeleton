# Dragon graph deployment custody and device qualification

This controller operates on one corpus root and its ten graph databases. It is not a complete application backup: external payload/media volumes, manifest databases, other owner roots, Mongo/external services and settings require separate coherent deployment custody. Stop all application, scheduled and older writers. Use private absolute local paths; no network filesystem support. Never invoke on a running production app.

## Operator sequence

From backend, with project environment initialized:

1. python -m core.dragon_graph_deployment prepare --root ROOT --workspace NEW_PRIVATE_WORKSPACE --offline-writers-stopped LANE0 ... LANE9
2. python -m core.dragon_graph_deployment apply --workspace NEW_PRIVATE_WORKSPACE --offline-writers-stopped
3. python -m core.dragon_graph_deployment backup --root ROOT --backup NEW_PRIVATE_BACKUP --offline-writers-stopped
4. python -m core.dragon_graph_deployment verify-backup --backup NEW_PRIVATE_BACKUP
5. python -m core.dragon_graph_deployment drill --backup NEW_PRIVATE_BACKUP --scratch NEW_PRIVATE_SCRATCH --offline-writers-stopped
6. python -m core.dragon_graph_deployment benchmark --root ROOT --bytes-per-lane 16777216 --acknowledge-device-writes
7. python -m core.dragon_graph_deployment transaction-probe --root ROOT --rounds 3 --bytes-per-lane 65536 --acknowledge-device-writes

Use actual absolute paths. Prepare performs conservative aggregate free-space checks per filesystem and captures a verified preimage before migration. Legacy WAL is checkpointed and converted to DELETE before raw backup. The controller uses exclusive SQLite transactions and refuses sidecars, pending graph plans/probes and inconsistent data. All bytes are SHA-256 readback verified, including exact physical markers. Apply only migrates the backed-up legacy root, verifies the active topology and installs the direct, structural, multi-batch and same-owner protocols in order. Stages that already committed replay; failed unpublished shard files are never auto-deleted. If the source altered or a partial file differs, stop and inspect custody. A full application deployment still needs a separately qualified coherent backup of all related stores, process stop/start controls, and post-launch application checks.

Restore drill rebinds only a disposable clone's graph paths and audits it. Do not run the application against the clone, which may retain original unrelated routing metadata. Restore-new uses original absolute paths only, never overwrites, verifies every target, stages complete bytes and performs a no-overwrite hard-link publication; root publishes last. Local filesystem hard links must be supported. Keep writers stopped. A crash that leaves two links or a differing partial stage requires manual custody inspection. Existing root must match the entire restored set exactly. Directory fsync is reported only on POSIX. Verification is integrity evidence, not a signed backup or anti-tamper guarantee against an attacker able to rewrite both data and manifest.

Benchmark writes actual random non-sparse scratch bytes on every configured physical lane, measures fsync and verified readback, aggregates allocations by filesystem, uses four workers and cleans only its own scratch files. Read timings may include cache effects and RNG/hash overhead; no raw device speed guarantee. Graph transaction probe cycles the existing cross-shard durable canary and verifies reopen/cleanup. It measures that bounded transaction workload, not maximum storage capacity, production ingest TPS or power-cut durability. Physical host evidence, independent restore of all other stores, workload-specific stress and OS/hardware recovery tests remain mandatory. Fixture CI cannot establish production readiness.
