# Local-only Docker: synthetic three-voter Mongo failover acceptance

**Review-only, explicitly opt-in, synthetic physical probe.** This work
extends the standalone Jeeves local-AI Docker stack after the read-only
production Mongo majority gate. It does NOT enable Mongo replication in the
actual application, write to user data, migrate epochs, validate protected
chat or grant merge/release approval.

## Verified prerequisite

The canonical offline four-image archive has been independently checked,
its receipt SHA-256 is trusted outside the archive, an exact-ID Compose
overlay has been rendered and all four image IDs are already installed.
The script takes the **immutable Mongo image ID from that verified bundle**.
It will not accept tags, use hosted services, download an image or pull a
registry. A Linux Docker daemon using a local Unix socket is mandatory;
Docker remote context environment overrides are rejected.

## Explicit synthetic-only execution

```sh
python scripts/qualify_local_ai_mongo_quorum_docker.py \
  --mode cpu \
  --directory /path/to/verified-four-image-archive \
  --overlay-directory /path/to/verified-offline-compose-overlay \
  --expected-receipt-sha256 YOUR_INDEPENDENT_ARCHIVE_RECEIPT_SHA256 \
  --allow-synthetic-database-writes
```

Without the final explicit flag the action is inert. The actual source
archive, immutable images, app Docker project and data volumes are only
read; their names are never used as synthetic container names.

## Physical proof sequence

1. Re-admit the offline immutable image and exact canonical Compose binding.
2. Reject remote Docker endpoints and non-Linux daemons.
3. Create an independently named **non-attachable internal-only bridge**,
   with a random scope and a unique Docker label.
4. Launch three **new** containers from the approved Mongo image. Each
   instance runs with UID/GID 999, dropped capabilities, no-new-privileges,
   read-only root, bounded CPU, RAM and process count. Database files,
   config and temporary files exist **only on private container tmpfs**.
   No published port, host path, application volume, or persistent mount.
5. Inspect all containers and their bridge, including immutable image
   IDs, labels, network membership, privilege restrictions and mounts.
6. Initialize a **test-only** replica set from the synthetic nodes.
   Observe one elected primary, set a majority+journal write default,
   then submit a unique synthetic record with `w=majority,j=true`.
7. Read the exact record with majority read concern from all three voters.
8. Stop ONLY the identified disposable primary, observe a different
   primary election among the remaining voters, then submit a second
   majority+journal write. Verify both records on both survivors.
9. Check physical isolation again and remove ONLY created IDs that still
   bear their originally attested random synthetic identity label.
   Clean up the labelled internal network. Any cleanup ambiguity leaves
   a clear failure requiring operator examination, not an unsafe prune.

The tool emits only allowlisted booleans and the source receipt hash. It
never prints the random challenge, container names or raw Mongo/Docker
diagnostics. A failed stage is a denial; there is no data migration,
replica-set conversion, or production rollback operation.

## Security boundary and proof limits

This is an intentionally **unauthenticated disposable test-only Mongo
replica set** with no host-published ports, internal Docker-only network
and no persistent disks. It is not an acceptable production Mongo
configuration. Running it on a real Docker host is an opt-in local operation,
not an automatic first-install step.

The test proves that a pinned image can exercise a real three-member Mongo
election, acknowledgement, majority replay and primary failover in an
isolated synthetic environment. Because tmpfs is volatile, it **does not
prove physical journal persistence or crash recovery**. A single Docker
host does not demonstrate independently isolated failure domains.

The actual standalone Mongo Compose service remains single-node and the
production `audit-mongo-majority` gate is expected to DENY. Its independent
read-only checks, shared writer-epoch fencing, authenticated application
writers, coherent Mongo/SQLite/Chroma snapshot and restore, native GGUF
hardware inference, protected Jeeves chat, Windows/WSL2 device acceptance
and signed release provenance remain separate outstanding gates.

## Exact-head source qualification

```sh
python -m compileall -q \
  scripts/qualify_local_ai_mongo_quorum_docker.py \
  skeleton/testing/test_local_ai_mongo_quorum_docker.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_local_ai_mongo_quorum_docker.py
```

The actual three-node Docker qualification requires an operator-approved
local machine with the already verified immutable image bundle; CI source
tests do NOT substitute for a real physical run. No merge or release.
