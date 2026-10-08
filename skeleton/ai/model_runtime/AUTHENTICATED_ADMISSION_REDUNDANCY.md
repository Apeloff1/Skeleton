# Authenticated, term-fenced admission checkpoint replicas

This supplements the canonical
[three-replica admission recovery](ADMISSION_REDUNDANCY.md) and its
[checkpoint contract](ADMISSION_CHECKPOINT_RECOVERY.md).

`AuthenticatedFileCheckpointReplica` is a **CheckpointReplica adapter**; it
uses the same `publish_redundant_checkpoint`,
`recover_redundant_checkpoint`, `repair_redundant_checkpoint` and
`FileCheckpointReplica` as the standard 2-of-3 recovery path. It is not a
separate quorum algorithm, serving plane or leader-election authority.

### Failure isolation and authenticity

- Preprovision three genuinely independent storage/power failure domains.
  Three folders on the same disk are not sufficient for host redundancy.
- Supply a strong, **external, non-repository** HMAC-SHA256 secret key of at
  least 32 bytes. Replica records bind checkpoint digest, member name,
  leadership term, and expected predecessor digest into an authenticated
  envelope. A tampered or cross-member copied record is rejected before it
  contributes to recovery quorum.
- The trusted caller supplies a **current, independently fenced**
  `leader_term` to each member adapter. An older adapter cannot overwrite
  an authentic newer-term record. Two same-term histories with different
  authenticated predecessor digests are also blocked rather than silently
  replaced.
- Recovery still requires the external `minimum_sequence` and, when
  available, `expected_digest` pin from a durable independent witness. A
  correct HMAC is **not** a consensus certificate, a freshness proof, or a
  substitute for a leader lease; compromise of the HMAC key defeats record
  authenticity.
- The default file adapter uses atomic same-directory replacement plus fsync.
  Partial publication and physical disk failure remain possible. Only a
  successfully reread two-member majority authorizes recovery.

### Operator wiring

```python
from pathlib import Path
from skeleton.ai.model_runtime import (
    AuthenticatedFileCheckpointReplica,
    publish_redundant_checkpoint,
    recover_redundant_checkpoint,
)

# key = secure_secret_manager.get_bytes("admission-replica-hmac")
# term = durable_leader_lease.current_term()
# parent_digest = durable_commit_witness.previous_digest()
replicas = (
    AuthenticatedFileCheckpointReplica(
        "node-a", "rack-a", Path("/vol-a/checkpoint.json"),
        leader_term=term, secret_key=key,
        expected_parent_digest=parent_digest,
    ),
    AuthenticatedFileCheckpointReplica(
        "node-b", "rack-b", Path("/vol-b/checkpoint.json"),
        leader_term=term, secret_key=key,
        expected_parent_digest=parent_digest,
    ),
    AuthenticatedFileCheckpointReplica(
        "node-c", "rack-c", Path("/vol-c/checkpoint.json"),
        leader_term=term, secret_key=key,
        expected_parent_digest=parent_digest,
    ),
)
receipt = publish_redundant_checkpoint(
    live_scheduler, replicas, expected_policy=policy,
    expected_limits=limits, minimum_sequence=durable_sequence_floor,
)
# Independently persist receipt.digest + receipt.sequence before acknowledging
# them to any supervisor; then use those witness pins during recovery.
result = recover_redundant_checkpoint(
    replicas, expected_policy=policy, expected_limits=limits,
    minimum_sequence=durable_sequence_floor,
    expected_digest=durable_checkpoint_digest,
)
```

The snippet assumes the trusted `term`, `key` and parent revision have been
provided by the operator; it is not copy-and-run without that infrastructure.

**Key rotation:** Coordinate an external term increment, distribute the new
key securely, then publish a new quorum and update the trusted witness. Do
not rotate one member independently and mistake loss of quorum for success.

**Model-state boundary:** these are scheduler/KV-accounting snapshots, not
replicated KV tensor payload, model weights, or a fully recoverable token
stream. A host failover must separately rehydrate verified model/KV state or
restart and replay inference under higher-level idempotency fencing. No active
GPU decode can be resumed solely by reading these files.

### Required regression and operator gates

```bash
python -m unittest tests.flgb.test_admission_authenticated_redundancy -v
python -m unittest tests.flgb.test_admission_redundancy -v
python -m unittest tests.flgb.test_admission_checkpoint_strict -v
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Production readiness still requires two-node outage drills, fencing and
consensus/lease integration, verified key rotation, independent commit
witness durability, power-loss injection, alarms, metrics, and end-to-end
rehydration/regeneration validation. No masterplan volume sign-off is implied.
