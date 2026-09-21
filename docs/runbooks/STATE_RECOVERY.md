# Authoritative-First State Recovery Runbook

Architecture contract: `machine/state_topology.json`  
Construction task: `AIQ-S0-STATE-03`

## Recovery law

Skeleton restores state in authority order. A durable or searchable store is not
automatically authoritative.

The non-negotiable ordering is:

```text
restore authoritative physical service
 -> restore canonical application/product records
 -> verify canonical counts + document digests + index digests
 -> restore canonical operation/execution authority
 -> reconcile unpublished durable intents
 -> rebuild derived Chroma/vector/cache/index state
 -> verify derived determinism/lag
 -> enable readiness/traffic
```

A derived rebuild attempted before authoritative verification is a recovery
failure, not a shortcut.

## Automated rehearsal

The repository contains a destructive **scratch-only** recovery harness:

```bash
python scripts/state_recovery_drill.py live-mongo \
  --uri "mongodb://127.0.0.1:27017" \
  --source-database skeleton_recovery_drill_source \
  --restored-database skeleton_recovery_drill_restored \
  --output /tmp/state-recovery.json
```

The script refuses database names that do not begin with
`skeleton_recovery_drill_`.

The dedicated `State Recovery Drill` GitHub Actions workflow boots an isolated
Mongo 7 service and proves:

- canonical scratch data can be backed up logically;
- user-defined index metadata is captured;
- a separate restore database can be reconstructed from the backup;
- collection sets and document counts match;
- canonical document digests match;
- user index digests match;
- derived rebuild is impossible before `verify_authority`;
- derived rebuild is deterministic after verification;
- the recovery journal reaches `ready` only after both layers pass.

The existing RAG authority tests additionally delete all user-owned Chroma
projections and rebuild them from canonical Mongo state.

## Production incident sequence

The live CI drill is evidence for ordering and logical recoverability. It does
not authorize running the scratch script against a production database.

For a production recovery:

1. fence or quiesce writers;
2. authenticate and recover the Mongo physical service;
3. restore the canonical application database from the approved production
   backup mechanism;
4. run schema/index compatibility checks;
5. verify record counts and integrity evidence before opening dependent writes;
6. restore/reopen canonical OperationEnvelope state and reconcile unpublished
   transactional outbox rows;
7. restore any other declared authoritative ledgers;
8. only then discard/rebuild Chroma, vector indexes and process-local caches;
9. verify derived-state lag/determinism;
10. run readiness and cross-store reconciliation;
11. reopen traffic.

If authoritative verification fails, stop. Do not rebuild projections on top of
an unverified restore.

## Evidence

Current executable evidence is anchored by:

- `scripts/state_recovery_drill.py`
- `skeleton/testing/test_state_recovery_drill.py`
- `.github/workflows/state-recovery-drill.yml`
- `backend/tests/test_rag_state_authority.py`
- `machine/state_topology.json`
- `docker-compose.yml`

The build-accountability ledger remains authoritative for task completion.
