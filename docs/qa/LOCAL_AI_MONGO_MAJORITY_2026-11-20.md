# Jeeves Docker: physical read-only Mongo majority-journal admission

**Status:** review-only source. It does not enable replicas, perform schema
migration, change Mongo settings, rotate credentials, write documents,
establish durable actor epochs, or authorize production recovery.

## Current structural limitation

The canonical standalone local-AI Compose has one pinned MongoDB 7 service
with authentication and persistent /data/db and /data/configdb volumes.
A healthy single mongod and a successful ping do not demonstrate a
majority-durable replicated writer. A fault-tolerant quorum must be
deliberately configured and independently qualified; silently converting
existing volumes or auto-initializing a replica set is unsafe.

This is a strict READ-ONLY capability check. It fails on an ordinary
standalone Mongo instance, exposing the architecture gap rather than
incorrectly reporting completion.

## Command

Requires the verified four-image archive, exact-ID Compose binding and
running application containers:

    python scripts/local_ai_docker.py --mode cpu audit-mongo-majority \
      --directory /home/operator/private/transfer-001 \
      --overlay-directory /home/operator/private/bindings/local-cpu-001 \
      --expected-receipt-sha256 INDEPENDENT_IMAGE_RECEIPT_SHA256

The auditor rechecks Docker identities before and after the query and
runs a bounded read-only Python snippet inside the already authenticated
backend container through the exact Compose overlay.

It reuses the application's existing shared PyMongo connection pool.
The host command and the sanitized result NEVER include the Mongo URI
or credentials, hostnames, addresses, data documents or error messages.

Read-only database commands:
- hello: actual writable primary and a consistent replica set identity.
- replSetGetStatus: primary state, member health and replicated voters.
- replSetGetConfig: data-bearing voters and majority journal policy.
- getDefaultRWConcern: explicit journaled-majority default write concern.

Each command has bounded server-side maxTimeMS and strict output fields.

## Fail-closed thresholds

Admission requires:

1. Exact verified Docker image IDs and unchanged running-container
   isolation under canonical internal-only networking.
2. One writable primary and a consistent replica set identity and state.
   A ping or process health flag is insufficient.
3. At least THREE **distinct** data-bearing configured voting members,
   excluding arbiters; at least floor(voters/2) + 1 healthy data-bearing
   voters. Every configured numeric voter ID must have a unique exact host,
   and every observed status member must match that ID-host pair. Duplicate,
   missing or unrecognized identities, boolean-as-integer votes/health and
   inconsistent status membership fail closed.
4. Majority journal default explicitly true.
5. Default write concern explicitly w=majority and j=true.
6. No duplicate/unknown fields, malformed members, nonfinite values,
   unbounded output or host Docker identity changes.

A pass has status
live_mongo_majority_readonly_capability_not_writer_epoch.

It does NOT prove different physical failure domains, real write
acknowledgements, external writer exclusion, committed actor epochs,
cross-plane migrations, crash recovery or coherent Mongo/SQLite/Chroma
snapshots. All those claims remain FALSE, including protected chat and
release qualification.

## Readiness integration

The on-host readiness matrix adds the observed gate
read_only_mongo_majority_capability. It runs only after the canonical
four-image archive and actual container isolation have passed.

The separate shared_mongo_writer_epoch_and_migration gate remains
unverified, EVEN if majority capability passes.

Actual replica-set bootstrap, trust keys, multiple failure domains,
migration, backup consistency and writer fencing require a separate
explicitly authorized rollout. This source candidate does not attempt
those risky mutations or auto-modify preexisting data.


## Source qualification of embedded backend probe

The source suite executes the actual backend-only read-only snippet against
a fake admin command interface. Eight adversarial topology variations test
duplicate voter IDs or hosts, boolean voting policy, spoofed runtime
hostnames/health and missing or duplicate status entries. Invalid evidence
emits only a fixed redacted rejection record, not raw Mongo metadata. This
is a deterministic source regression, not evidence of physical majority
availability. Rerun the exact-head CI and independently qualify a genuine
Docker/Mongo deployment before any production decision.
