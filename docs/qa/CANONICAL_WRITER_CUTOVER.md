# Canonical backend writer cutover (operator-only candidate)

The existing default Compose services use distinct databases and start in
legacy/unactivated mode. A healthy default install is not guarded-AI evidence.
The protected backend launcher is a new explicit source-checkout entrypoint;
it does not alter existing Compose services or provision/migrate any data.

Before considering it, independently quiesce all writers, establish encrypted
backup/restore custody, prove physical deployment identity and retire direct
or unregistered mutation principals. Reconcile all canonical collections and
existing actor epochs using independently reviewed migration procedures.
The v2 source gate scans stable epoch records plus all six known local canonical
owner collections: threads, committed messages, memory roots, revisions,
projection outbox, and committed idempotency receipts. It checks exact scope
relationships, logical identity uniqueness and bounded version relationships.
Unresolved prepared messages or pending memory reservations deny admission;
a separate reviewed recovery is required. The gate does not verify payloads,
complete historical continuity, archive or external writer surfaces. Missing, writing, revoked or inconsistent
epochs deny the entire initial cutover. No automatic repair or reset occurs.

With the existing backend Mongo configuration, observe the inventory only:

    PYTHONPATH=.:backend python scripts/start_protected_backend.py \
      --inspect-only --source-head REVIEWED_GIT_SHA

The command prints only counts, the v2 inventory SHA, local-owner graph SHA,
collection counts and non-authorizing readiness flags. It requires authenticated stable replica-set primary, majority actor
inventory and per-actor linearizable epoch equality. No credentials or actor
IDs are printed. Current implementation caps the inventory at 65,536 actor
epochs, 250,000 metadata rows per owner collection and a 120-second bounded
scan. The v2 signature domain and inventory digest invalidate v1 approvals;
issue a new independently reviewed approval. Never reuse a v1 signature. Larger deployments require a
separately reviewed sharded inventory/qualification path, not a bypass.

An independent authority may sign a CanonicalWriterCutover plan's
domain-separated canonical_bytes() after reviewing the exact source SHA,
deployment ID, database, voting hosts, authenticated user/role inventory,
counts, inventory digest, and external backup, quiescence, writer-retirement
and storage-provenance receipt hashes. Maximum signed validity is ten minutes.
The launcher verifies the raw 64-byte signature with a separately pinned raw
32-byte Ed25519 public key in hex. No signing key should be installed on the app.
The plan parser requires exact fields and rejects duplicates. The application
does not generate the approval nor establish external evidence truth.

    PYTHONPATH=.:backend python scripts/start_protected_backend.py \
      --start-protected-backend --source-head REVIEWED_GIT_SHA \
      --plan /private/cutover.json --signature /private/cutover.sig \
      --authority REVIEWED_AUTHORITY --deployment REVIEWED_DEPLOYMENT \
      --operator-public-key-hex REVIEWED_PUBLIC_KEY_HEX \
      --state-dir /private/writer-custody --port 8001

This starts only the existing backend on loopback, one worker, no reload.
Before fail-soft lifespan or scheduler, it validates the signed live inventory,
then binds the actual canonical global conversation and memory owners to one
epoch. The governed memory writer must refer to that same repository.
Loss or replacement of the installed epoch is denied by known writer fences.
Startup failure cannot continue through the ordinary fail-soft boot envelope.
Protected owners cannot be rebound in the same process. This is not an
authorization to start a concurrent legacy writer or change Mongo volumes.
The engine remains independently unqualified: no cross-process canonical
reader binding, replica migration, semantic review, production activation or
installer-to-inference success follows from this entrypoint. An actor without
an already provisioned stable epoch is denied by the protected writer.

No deployment is performed by source qualification.

Protected startup now also rebinds the actual canonical conversation database,
thread/message and four memory collection handles with primary majority reads
and journaled majority writes, with a bounded write concern timeout. Protected
write entrypoints check installed handle identity and concern, and recheck
before the epoch can become stable after mutation. This does not make direct
Mongo clients or unregistered collection writers safe; memento transactions
and cross-owner deletion remain separate reviewed surfaces.

The disposable authenticated Mongo qualification now exercises the v2 local
owner graph using actual BSON projections, majority reads, a real stable epoch,
same-principal independent clients, alternate-principal denial, orphan and
prepared-message denial, divergent revision scope, pending idempotency denial,
and changed-outbox approval invalidation. Its ephemeral fixture is not a
production migration, multi-member failover, or installer-to-inference receipt.

Protected startup additionally requires a pre-provisioned, mode-0700 POSIX
state directory owned by the service account. Use one durable, independently
controlled directory for the deployment. The launcher holds an exclusive
local deployment lock and creates a new mode-0600 approval reservation with
exclusive creation and file/directory fsync before importing and launching the
backend. Failed or interrupted startup burns the approval. A reservation is
not a successful admission receipt. Do not delete reservation records to
recover; reconcile and obtain a fresh signed plan. This is single-host trusted
filesystem custody, not a distributed lock or a physical anti-rollback witness.
Default unprotected setup and read-only inspection do not make reservations.


### Shared database startup custody

The protected launcher additionally reserves a non-expiring, majority-journaled
singleton row in canonical_writer_deployment_latch. It validates the signed
six-collection graph before the reservation, validates the graph again after
reservation, and checks the exact linearizable ACTIVE row before binding local
owners. An uncertain write or failed launch leaves the reservation held.
A second cooperative backend cannot start on the same canonical database,
including from a different host or under a deployment alias. The fixed row
identity is database-wide; the generation is monotonic and retirement preserves
the approval timestamp high-water mark. No TTL or automatic takeover exists.

Use --inspect-deployment --source-head SHA for a read-only state, generation,
and active latch digest receipt. After independently proving every protected
process is stopped, an authorized operator signs WriterDeploymentRetirement
with the active latch digest, exact source/deployment/database/authority pins,
short validity, and SHA-256 of external shutdown evidence. Use
--retire-deployment --source-head SHA --plan /private/retirement.json
--signature /private/retirement.sig --authority ID --deployment ID
--operator-public-key-hex PIN. This operation is offline administration only:
never retire an active process, never delete the latch row, and never use
elapsed time as shutdown evidence. A new startup plan must have an issuance
timestamp strictly newer than the retirement high-water mark. A different
deployment or authority requires a separately reviewed migration.

The latch excludes cooperating startup attempts; it does not fence arbitrary
direct clients, continuously attest an already-running backend, prove external
shutdown evidence, prevent database snapshot rollback, or authorize inference.
Those remain independent holds. The default legacy install is unchanged.


The reservation is also pinned into the actual backend epoch object. Known
actor-epoch reads and nested/outer writer boundaries revalidate the exact
active generation. Loss, cancellation or ambiguous observation quarantines
that process rather than allowing a rebind. If the latch changes after actor
admission but before the final CAS, the actor remains WRITING. This is a
boundary check, not an atomic cross-collection transaction; retirement still
requires independently verified shutdown, not a live release. Both canonical
and compatibility epoch source paths are modified identically.

The isolated authenticated Mongo v3 harness races separate clients against the
singleton latch, verifies signed retirement and replay denial, then verifies
a process pinned to the retired generation remains quarantined when a newer
generation starts. No production latch is written by that isolated harness.

The process also retains a separate required-pin identity. Loss or replacement
of the installed pin quarantines the process even if the original tuple is
later restored. This protects known application-owned paths, not arbitrary
code execution inside the backend process.
