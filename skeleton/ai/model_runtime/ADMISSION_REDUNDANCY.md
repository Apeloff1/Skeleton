# Three-replica native model-serving admission recovery

This document complements
[ADMISSION_CHECKPOINT_RECOVERY.md](ADMISSION_CHECKPOINT_RECOVERY.md).

## Deployment layout

Provision three *independent* storage failure domains with a bounded,
atomic file-store directory for each checkpoint:

```python
from pathlib import Path
from skeleton.ai.model_runtime.admission_redundancy import (
    FileCheckpointReplica, publish_redundant_checkpoint,
    recover_redundant_checkpoint,
)

# Preprovision these directories on separate durable volumes/hosts.
replicas = (
    FileCheckpointReplica("primary", "node-a", Path("/volume-a/checkpoint.json")),
    FileCheckpointReplica("secondary", "node-b", Path("/volume-b/checkpoint.json")),
    FileCheckpointReplica("tertiary", "node-c", Path("/volume-c/checkpoint.json")),
)

# With an existing RuntimeAdmissionScheduler `scheduler`, and independently
# trusted deployment policy/limits (not taken from the checkpoint itself):
receipt = publish_redundant_checkpoint(
    scheduler, replicas, expected_policy=policy, expected_limits=limits,
    minimum_sequence=trusted_sequence_floor,
)

# Persist receipt.digest + receipt.sequence in a separately trusted witness
# before acknowledging the checkpoint to higher-level control logic.
result = recover_redundant_checkpoint(
    replicas, expected_policy=policy, expected_limits=limits,
    minimum_sequence=trusted_sequence_floor,
    expected_digest=trusted_committed_digest,
)
scheduler = result.scheduler
```

Do not paste these example identifiers unchanged into production. The example
describes *logical* independent failure domains: the application cannot prove
that three directory paths correspond to three independent disks, volumes,
power supplies, or hosts. The operator must provision and verify the hardware,
backups, monitoring and storage permissions.

## Reliability contract

- Exactly 3 distinct named replica adapters and declared failure domains.
- Require at least 2 **independently validated identical canonical** snapshots
  for successful recovery; a single valid copy cannot authorize recovery.
- A missing, unreadable, corrupted, oversized or outdated single replica
  permits **degraded** recovery only if the other two match.
- Two missing/bad replicas, three distinct revisions or absence of a
  two-member quorum **fail closed**.
- Publication validates the source scheduler, checks existing valid revisions
  for rollback/equivocation, writes isolated copies, reads each copy back and
  requires two matching acknowledgements.
- A successful two-replica acknowledgement may leave a stale third replica.
  The returned `ReplicationReceipt` records that degraded state. An operator
  can republish after repairing failed media.
- A partial new write can leave one *newer* uncommitted copy and two *older*
  copies: without a **trusted independent witness**, the old two-copy quorum
  may be selected. An expected digest/sequence from a trusted ledger is the
  rollback fence, not the SHA-256 checksum by itself.
- Never count a write attempt, storage path, or checksum as proof of distinct
  failure domains or durable consensus.
- `FileCheckpointReplica` uses bounded canonical JSON, refuses symlink reads
  on systems with O_NOFOLLOW, atomically replaces same-directory temporary
  files and fsyncs file data and POSIX parent directories.
- The file adapter requires an already provisioned parent directory; it does
  not create storage, dispatch work or manage secrets.

## Boundaries and exclusions

This is **crash recovery**, not duplicate live model-execution redundancy.
It does not implement distributed consensus, split-brain leases, a durable
independent witness, cloud replication, cross-process synchronization,
hot-standby model weights or a second copy of in-flight GPU KV tensor pages.
A snapshot records KV **accounting and scheduler ownership**, not the raw
tensor payload. Recovering a GPU generation also requires a verified
compatible tensor/weight snapshot or a fail-closed restart of generation.

The storage protocol assumes a single writer for the three slots, and that
file permissions and failure-domain names are controlled by a trusted service.
External writer leases/fencing and an authenticated high-water mark are
required if processes may overlap or if a malicious store is in scope.
A two-of-three protocol without those controls must not be represented as
linearizable consensus.

## Focused regression commands

```bash
python -m unittest tests.flgb.test_admission_redundancy -v
python -m unittest tests.flgb.test_admission_checkpoint -v
python -m unittest tests.flgb.test_admission_checkpoint_strict -v
python -m unittest tests.flgb.test_admission_checkpoint_state_machine -v
python -m unittest tests.flgb.test_runtime_admission_scheduler -v
```

The tests use independent test adapters, fault injection and temporary
directories; temporary directories on one disk do not demonstrate physical
fault tolerance or production-scale durability.
