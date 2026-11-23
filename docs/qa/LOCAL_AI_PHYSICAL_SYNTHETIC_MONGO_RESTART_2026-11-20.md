# Standalone Docker local AI — physical synthetic Mongo restart

**Review-only physical synthetic acceptance**, explicitly OFF by default.
This is not a production restore procedure and has no application-data access.

## New physical failure mode

Earlier disposable three-voter tests in the Docker workstream use
`tmpfs` mounts to prove live elections, journaled-majority acknowledgements,
writer-epoch compare-and-swap and quorum-loss refusal. Those tests do not
prove a byte can survive destruction of the memory-backed Mongo data root.

The new acceptance probe uses the **already installed immutable Mongo
image ID**, a **new randomly generated private scratch directory** under
`/tmp`, and one process-local MongoDB instance. It requests a
`w:1,j:true` write to a synthetic record, then:

1. Runs Mongo inside Docker with `--pull never`, `--network none`,
   read-only container root, no published ports, all capabilities
   dropped, no-new-privileges and exact CPU, RAM, swap and PID limits.
   No externally supplied mount path or credential is admitted.
2. Mounts only the generated private scratch `data` child at
   `/data/db`. Both other writable paths are small UID/GID-scoped
   tmpfs mounts; the image is pinned by the independent offline
   four-service source bundle.
3. Runs the actual `mongod` listener on the container's loopback
   interface and sends actual `mongosh` commands exclusively through
   Docker's authenticated container-exec channel.
4. Requires a successful synthetic single-node
   `writeConcern:{w:1,j:true}` acknowledgement and a matching
   read of exactly one synthetic marker record.
5. Sends an actual `SIGKILL` to that exact attested container ID.
   It requires the same marker to be readable after a real
   `docker start` and Mongo WiredTiger journal recovery.
6. Removes only the exact scope/name/label/image/mount verified test
   container. Recreates a **new container identity** from the same
   immutable image using the **same** private synthetic scratch
   mount, and requires the record to survive that replacement.
7. Enumerates and removes only exact label/name/image/mount-verified
   test objects, confirms no unexpected scratch-root member exists,
   and deletes only its private generated scratch directory using
   symlink-safe traversal. A cleanup failure blocks any acceptance.

### Operator command

```sh
python scripts/local_ai_docker.py --mode cpu qualify-synthetic-mongo-restart \
  --directory /private/preverified-offline-image-bundle \
  --overlay-directory /private/validated-no-pull-overlay \
  --expected-receipt-sha256 IMMUTABLE_IMAGE_BUNDLE_RECEIPT_SHA256 \
  --allow-synthetic-database-writes \
  --allow-private-synthetic-bind
```

Both affirmative flags are required. The generated scratch directory is
never user-supplied. No main application Compose service is started,
stopped or modified. There is no host port, external bridge, Docker
volume, registry pull, provider connection or native model download.

**Filesystem caveat:** `/tmp` might be memory-backed depending on the
host; even a completed SIGKILL/restart/recreate experiment is
**same-host synthetic container persistence evidence only**. It does
NOT establish durable physical storage, a separate failure domain,
three-voter majority, real application WiredTiger recovery, a consistent
Mongo/SQLite/Chroma checkpoint or complete Jeeves chat readiness.
That distinction is built into the receipt. The separate synthetic
three-voter suite remains necessary for quorum evidence.

### Test scope and remaining gates

```sh
python -m compileall -q \
  scripts/qualify_local_ai_mongo_restart_docker.py \
  skeleton/testing/test_local_ai_mongo_restart_docker.py \
  scripts/local_ai_docker.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_local_ai_mongo_restart_docker.py \
  skeleton/testing/test_local_ai_mongo_quorum_docker.py \
  skeleton/testing/test_local_ai_synthetic_epoch_fence.py
```

The focused source suite is **host-portable and mocked at the Docker
transport**. It cannot claim that actual Docker execution has happened.
It exercises forbidden pulls, host networking, foreign volume mounts,
poisoned container metadata, wrong credentials/UID/tmpfs, resource
limits, forged journal replies, failure to replay a record, exact
SIGKILL/restart/recreate order, private scratch cleanup and explicit
dual approvals. Physical acceptance requires separately running the
operator on a local Docker host with the immutable bundle installed.

The receipt always denies: production Mongo writes, production volumes,
real replica-majority qualification, independent physical failure-domain
proof, real application Mongo recovery, cross-store atomicity,
protected Jeeves inference and release authorization.

**Draft/review only. No merge, release or production data changes.**
