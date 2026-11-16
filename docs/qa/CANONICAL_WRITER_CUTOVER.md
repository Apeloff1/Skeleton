# Canonical backend writer cutover (operator-only candidate)

The existing default Compose services use distinct databases and start in
legacy/unactivated mode. A healthy default install is not guarded-AI evidence.
The protected backend launcher is a new explicit source-checkout entrypoint;
it does not alter existing Compose services or provision/migrate any data.

Before considering it, independently quiesce all writers, establish encrypted
backup/restore custody, prove physical deployment identity and retire direct
or unregistered mutation principals. Reconcile all canonical collections and
existing actor epochs using independently reviewed migration procedures.
The source gate scans canonical thread and memory root actor coverage and
stable epoch records; it does not scan every message, revision, archive,
outbox, orphan or external writer. Missing, writing, revoked or inconsistent
epochs deny the entire initial cutover. No automatic repair or reset occurs.

With the existing backend Mongo configuration, observe the inventory only:

    PYTHONPATH=.:backend python scripts/start_protected_backend.py \
      --inspect-only --source-head REVIEWED_GIT_SHA

The command prints only counts, inventory SHA and non-authorizing readiness
flags. It requires authenticated stable replica-set primary, majority actor
inventory and per-actor linearizable epoch equality. No credentials or actor
IDs are printed. Current implementation caps the inventory at 65,536 actor
epochs and has a 120-second bounded scan. Larger deployments require a
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
      --operator-public-key-hex REVIEWED_PUBLIC_KEY_HEX --port 8001

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
