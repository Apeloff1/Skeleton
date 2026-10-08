# Redundant native AI admission checkpoints

**Owner:** `skeleton/ai/model_runtime`; complements
[ADMISSION_CHECKPOINT_RECOVERY.md](ADMISSION_CHECKPOINT_RECOVERY.md).
This is redundant **control-plane checkpoint persistence**, not hot replication
of model weights, KV tensors, live GPU memory, token outputs or generation
side effects. Restoring a scheduler state does not by itself rehydrate model
compute. Decode must not resume until separately verified model/KV rehydration
or controlled restart/replay has completed.

## Safety and availability model

- The operator provisions three, five or seven **distinct physical failure
  domains** with pre-existing member directories. Three replicas require
  two matching authenticated votes; five require three; seven require four.
  Multiple paths on one disk or in one host do not survive that host failure.
- A secret `bytes` HMAC key of 32–4096 bytes is supplied securely at runtime.
  Never commit it, persist it beside replicas, print it or treat SHA-256 alone
  as authenticating the publisher. Compromise of that key breaks authenticity.
- Each member contains the same scheduler snapshot, leadership term, sequence
  number, parent revision and digest, but has its own member-bound MAC.
  Duplicate JSON fields, noncanonical encodings, tampering, wrong identity
  and replay below trusted floors are rejected. Recovery votes on exact
  (term, sequence, parent, digest), never on a claim supplied by a replica.
- A quorum can tolerate one failed/invalid/stale member out of three, or two
  out of five. Split votes without a majority **fail closed**.
- **Fencing prerequisite:** a trusted leader-election/lease authority outside
  these modules must supply the monotonically persisted minimum leadership
  term and scheduler sequence high-watermark. Without those independent floors,
  a stale majority could win after rollback. The HMAC does not implement
  distributed consensus or prevent concurrent writers.
- The last successfully acknowledged majority publication is the latest
  recoverable durable scheduler checkpoint. Operations after that checkpoint
  may need to be replayed with higher-level idempotency fencing.

## Example operator call

```python
from pathlib import Path
from skeleton.ai.model_runtime import (
    AdmissionReplicaFileStore,
    recover_admission_quorum,
)

# Pre-provisioned separate disks/hosts, with trusted leader lease and key.
store = AdmissionReplicaFileStore({
    "zone-a": Path("/mnt/disk-a/checkpoints"),
    "zone-b": Path("/mnt/disk-b/checkpoints"),
    "zone-c": Path("/mnt/disk-c/checkpoints"),
})
# The actual key must come from secure runtime secret storage.
# key = secrets_provider.read_hmac_key()
# publication = store.publish(
#     live_scheduler, leader_term=trusted_term, secret_key=key,
#     minimum_term=trusted_term, minimum_sequence=durable_sequence_floor,
#     parent_digest=last_committed_checkpoint_digest,
# )
# Restore after a failure:
# scanned = store.scan()
# recovered = recover_admission_quorum(
#     scanned.copies, members=store.members, secret_key=key,
#     minimum_term=trusted_term, minimum_sequence=durable_sequence_floor,
#     expected_policy=deployment_policy, expected_limits=deployment_limits,
# )
# Explicit repair requires the same trusted fencing authority:
# store.repair(
#     recovered.repair_targets[0], recovered, secret_key=key,
#     minimum_term=trusted_term, minimum_sequence=durable_sequence_floor,
# )
```

A `publish()` call persists a single immutable snapshot to independent slots
using temporary-file fsync, atomic replace and directory fsync (where
available), then independently rereads the replicas to verify a matching
quorum. No successful publication receipt is issued if a majority cannot be
verified. A failed write can still have touched one disk; failed publication
must not be treated as proof of total rollback. Recovery reconstructs the
last majority-committed version.

`scan()` returns member-specific I/O failures. `repair()` is explicit and
will not replace an authenticated newer revision. It does not silently promote
a lone newer member or resolve genuine split brain. Cross-process writers
must be fenced by a trusted leader/lease service. Copies on one process or
one disk do not constitute host availability.

## Test and qualification gates

```bash
python -m unittest tests.flgb.test_admission_replicas -v
python -m unittest tests.flgb.test_admission_replica_store -v
python -m unittest tests.flgb.test_admission_checkpoint_strict -v
python -m unittest tests.flgb.test_admission_checkpoint_state_machine -v
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Production qualification still requires two independent hosts/storage failure
domains, a durable external monotonic lease/fence authority, tested key
rotation and escrow, actual model-state rehydration/replay tests, injected
power-loss tests, capacity/latency benchmarks, restore drills and alerting on
degraded quorum. No such qualification or masterplan volume signing is
claimed here.
