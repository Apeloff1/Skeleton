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


### Independently retained predecessor and signing-key continuity

The v3 cutover signature requires predecessor_generation and
predecessor_latch_sha256. Only an independently verified first deployment
may use 0 and null. A restart must bind the exact last retired generation and
digest retained outside the Mongo restore domain. The v2 latch stores the
authority public-key SHA-256 and the prior row digest on every transition;
retirement and startup both reject an alternate key even under the same
authority name. A signature from an older domain or a v1 latch row is denied.
Existing v1 state needs a reviewed offline migration, never an automatic
reset. Record every successful retirement receipt independently before issuing
another activation. This is detection relative to an independently retained
checkpoint, not physical anti-rollback if the independent evidence and
database are restored together or the signer deliberately approves genesis.


The launcher maintains an append-only local witness chain in its existing
protected state directory. Every successful shared reservation must be
published with exclusive creation and fsync before writer binding. Each
record binds the actual active generation, latch digest, exact source,
authority key and signed predecessor, plus the previous local record digest.
A host which observed an active generation rejects a new genesis approval
or any predecessor at or below that generation, even before contacting Mongo.
Missing intermediate records, malformed records, key substitution and
untrusted descriptor identities fail closed. The ledger accepts skipped
generations only because other hosts may have made independently approved
transitions. It does not recover missing documents, trim history, authorize
startup independently, or detect deletion of all/suffix records without an
external checkpoint. Keep the custody directory independently backed up and
retain signed receipts outside both restore domains. Bounded to 4,096 witness
records per deployment and 65,536 directory entries; larger histories require
a separately reviewed archival/checkpoint protocol.


The actual /api/health/ready aggregate now includes a redacted
canonical_writer_custody result. Legacy mode stays available but is explicitly
unqualified. A protected process checks exact installed owner identities,
sticky handles, writer inventory and active database reservation. Failed
observations quarantine the readiness state; an in-flight shared observation
times out to not-ready rather than using an old passing result. Concurrent
health callers coalesce onto one check; cancelling a caller does not cancel
the authority observation. Shutdown drains that task before Mongo closes.
This does not attest inference or external writer coverage. The three
duplicated mandatory route probes have been consolidated to one.


### Explicit co-hosted protected engine and backend

scripts/start_protected_stack.py is the operator-only single-host launcher.
It consumes the same signed writer cutover and persistent local witness plus
a separately signed ProtectedStackLaunchPlan bound to the writer-plan digest.
It pins the exact source, both loopback ports, policy, memory namespace,
all local model/runtime/tokenizer digests, selected active model, independent
reviewer identity/signing key, CA and client certificate digest, and a
reviewer challenge scope with an already provisioned stable actor epoch.
The launch authority cannot be the reviewer key. It does not provision an
actor or generate an approval.

Configure existing AI_PROVIDER=local, exactly one local model source,
SKELETON_INTERNAL_URL=http://127.0.0.1:ENGINE_PORT and the existing engine
service credential before launch. No fallback model provider is allowed.
Do not run the ordinary Compose backend or engine concurrently.

    PYTHONPATH=.:backend python scripts/start_protected_stack.py \
      --source-head REVIEWED_SHA --plan /private/writer.json \
      --signature /private/writer.sig --authority AUTHORITY --deployment DEPLOYMENT \
      --operator-public-key-hex PUBLIC_KEY --launch-plan /private/launch.json \
      --launch-signature /private/launch.sig --state-dir /private/writer-custody \
      --reviewer-ca /private/ca.pem --reviewer-client-cert /private/client.pem \
      --reviewer-client-key /private/client.key

The real backend writer binding runs first. Its trusted startup callback
starts the real engine on the same event loop with exactly those owner
objects. The engine verifies a scoped independent reviewer challenge against
the signed pins and its actual registry must expose only the pinned guarded
local models before backend startup continues. Each ASGI application keeps
its own loopback listener and lifecycle. During orderly shutdown backend
HTTP/background work drains, then engine finalization completes before shared
Mongo closes. The process never retires the database latch automatically.
A failed or uncertain launch requires offline reconciliation.

This is a source implementation for an explicit deployment topology, not
a substitute for real Mongo, signed reviewer, actual loaded model, process
lifecycle, browser, Windows/WSL2, Docker or device qualification. In particular
it does not automatically make the default Compose install guarded or
establish semantic review quality or a successful inference.
