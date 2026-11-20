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
9. Stop the synthetic successor as well, leaving exactly **one** voter.
   Require that it reports loss of primary authority and proves that an
   additional majority+journal write is **not acknowledged**. A locally
   attempted or timed-out uncommitted write is never treated as committed.
10. Restart only the **original** leader by its previously inspected immutable
    container ID; observe a new two-member primary election and require
    majority reads of both previously committed records on both members.
    Perform a third majority-acknowledged write, verify its exact replay,
    and leave the other disposable voter stopped.
11. Check physical isolation again and remove ONLY created IDs that still
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
election, journal-requested acknowledgement, majority replay, primary
failover, loss-of-quorum demotion, refused minority majority-acknowledgement,
restored quorum and replay of previously committed records in an isolated
synthetic environment. Because tmpfs is volatile, it **does not
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

## Minority loss-of-quorum acceptance notes

The second destructive operation is **ONLY** a `docker stop` of the already
attested disposable successor. It never touches the application Mongo
container. The single remaining disposable voter must lose primary status;
the probe then executes a bounded synthetic `w=majority,j=true` insert and
requires a structured server error or explicit write-concern timeout. A
network failure, missing server receipt, malformed JSON or an acknowledged
write fails the entire acceptance run. The minority challenge is randomly
scoped and is never treated as a committed application operation.

After quorum is lost, the probe restarts a *previously stopped exact container
ID*, never pulls, creates a replacement volume or changes the replica set
membership. An elected two-voter primary must provide majority-read replay
of the two earlier writes and a third freshly acknowledged write. Source
tests exercise server-refusal codes, timeout receipts, an unexpectedly green
minority acknowledgement, stale primary state, enforced restart inspection
and cleanup on failures. These checks do not prove actual application
actor-lease fencing, persistent-media fsync, or cross-host partitions.

## Three-phase independent Mongo primary and policy probes

Each acknowledged-write phase has a fresh, separate physical read of
`hello`, `replSetGetStatus`, `replSetGetConfig` and
`getDefaultRWConcern` **inside the elected synthetic primary**. This
reconciles exact replica-set name, current primary state, three configured
data-bearing voting members (not arbiters), at least three healthy voters
before fault injection and at least two healthy voters following each
intentional failover, plus a global `w=majority` write default and explicitly configured
`writeConcernMajorityJournalDefault=true`. Every synthetic data write
**separately** requests `w=majority,j=true`; the journal flag is not
smuggled into the global default write-concern command.
Every read is bounded and its receipt contains only fixed booleans/counts.
No production credentials, command dumps, connection strings or document
contents appear in the report. A missing/partial response does not pass.

This improves the evidence for a Docker-level election and journal-requested
write, but remains **synthetic and volatile**: a green probe does not grant
production Mongo majority primary authority, application actor epoch
exclusivity, physical power-loss durability or a deploy/release decision.

The test connects to each individual Mongo member by a direct-local mongosh
connection. Majority replay uses an explicit `find().readPref(
"secondaryPreferred").readConcern("majority")` cursor, rather than
`db.runCommand({find: ...})`, because modern mongosh command helpers do not
inherit the global read preference for secondary reads. All three independent
replay phases require actual evidence from each available voter.

## Inherited isolated-runtime custody requirements

The minority/recovery extension also inherits the strict Docker controls
from #5703. Synthetic Mongo creation is admitted only as an exact argv
sequence binding the pinned immutable image, randomized scoped network/name,
non-root 999:999 identity, read-only root, dropped capabilities, no added
capabilities and three private tmpfs mounts. The memory admission limit is
768 MiB with **no additional swap**, at most one CPU and 192 PIDs; the
read-only Docker inspector independently verifies actual host configuration
and exact uid/gid, mode, nosuid, nodev and byte ceilings for each tmpfs.
HostConfig intent and live NetworkSettings port publication must agree that
no synthetic Mongo listener is exposed to the host.

A recovered or orphaned container is eligible for synthetic cleanup only
after its ID, scoped name, unique label, and **original image ID** all
match. Foreign-image objects are not deleted even if a label is spoofed.
The command guard permits only scoped inspection, synthetic create, exact-ID
stop/start/exec and verified teardown; hostile host networking, extra
mounts, capabilities, Docker prune/pull and unbounded resources are rejected
before any subprocess is spawned. The source suite retains the minority
fencing/replay regressions alongside the upstream isolation and negative
command fixtures. These are source-level qualification targets, not proof
of physical execution or production data-plane durability.
