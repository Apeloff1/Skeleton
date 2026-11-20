# Local Jeeves Docker — real Mongo writer-epoch journal admission

**Production-path source hardening, opt-in only; no state migration or live
deployment authorized.** This work builds on the disposable three-voter
Mongo failover and synthetic writer-epoch qualification, but changes the
existing *real* backend/engine enrollment safety boundary.

## Material source gaps resolved

The canonical `MongoCanonicalSourceEpoch` previously used an explicit
`WriteConcern(w="majority", wtimeout=10000)`, without explicitly
requesting journal durability for its own transition records. A primary
`hello` plus a linearizable sentinel read also did not demonstrate that
the actual replica-set configuration had majority journaling enabled.

The new source:

1. Requires `WriteConcern(w="majority", j=True, wtimeout=10000)` on the
   canonical epoch transition collection.
2. Bounds acquisition and completion calls with a 12-second caller deadline.
   Timeout or uncertain response is a **denial**, never evidence of a
   successfully acknowledged writer-epoch transition.
3. Before the real backend or engine attaches the epoch, independently reads
   five Mongo admin replies from its own existing authenticated client:
   `hello`, `replSetGetStatus`, `replSetGetConfig`,
   `getDefaultRWConcern`, and a second `hello`.
4. Requires both hello responses to attest the same local primary identity,
   matching configured host identity, exactly one elected primary, exactly
   one local `self` member, distinct voter IDs/names, three or more configured
   data-bearing voters and a healthy current majority.
5. Requires the explicit `defaultWriteConcern.w="majority"` and actual
   replica-set `writeConcernMajorityJournalDefault=true`. A separate
   default `j=true` property is NOT mandatory (MongoDB supports an
   ordinary global majority default), but any explicit `j=false` or
   malformed journal policy is rejected.
6. Leaves the startup source unchanged when its opt-in environment setting
   is `0`. The actual shared actor migration is still a separate,
   operator-owned process.

## Source and code locations

- `skeleton/persistence/docker_epoch_writer_policy.py`: bounded, redacted
  five-command read-only policy and primary-identity verification.
- `skeleton/persistence/mongo_source_epoch.py`: explicit journaled-majority
  source epoch CAS, bounded independent commit admission and completion.
- `backend/core/local_guarded_epoch_startup.py`: backend conversation
  authority cannot attach epoch until authenticated live policy is admitted.
- `skeleton/persistence/docker_engine_epoch_startup.py`: Jeeves engine
  memory writer requires the same independently observed live policy.
- `skeleton/testing/test_docker_epoch_writer_policy.py`: false primary,
  swapped IDs, weak defaults, staleness, wrong server success, timeout/error
  redaction, and disabled configuration tests with no network or DB effects.
- `skeleton/testing/test_mongo_source_epoch_journal.py`: real canonical
  epoch class under in-memory atomic Mongo-method fixtures; verifies
  odd/even transitions, competing actors, cancelled mutations, missing
  migration records and uncertain majority acknowledgement.
- Existing backend/engine startup tests now exercise real policy probes
  before binding and deny weaker policy without publishing an epoch.

## Important acknowledgement uncertainty

A majority+journal write is considered admitted only if its database call
returns successfully. If the reply is lost **after** Mongo committed it,
the caller cannot infer either success or failure from the timeout alone.
An acquisition acknowledgement loss may leave an odd WRITING epoch requiring
reconciliation. A completion acknowledgement loss may leave an even STABLE
epoch on the server while the caller reports failure. Neither condition
is proof of a safely replayable application operation. Durable operation
idempotency and full end-to-end retry custody must be qualified separately.

The runtime never automatically provisions, repairs or resets unknown actor
epochs. External writer enrollment and actor migration are still unverified;
a successful policy probe is only point-in-time capability evidence, not
proof of ongoing quiescence or unique writer custody.

## Local source validation

```sh
python -m compileall -q \
  skeleton/persistence/docker_epoch_writer_policy.py \
  skeleton/persistence/mongo_source_epoch.py \
  backend/core/local_guarded_epoch_startup.py \
  skeleton/persistence/docker_engine_epoch_startup.py \
  skeleton/testing/test_docker_epoch_writer_policy.py \
  skeleton/testing/test_mongo_source_epoch_journal.py \
  backend/tests/test_local_guarded_epoch_startup.py \
  skeleton/testing/test_docker_engine_epoch_startup.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_docker_epoch_writer_policy.py \
  skeleton/testing/test_mongo_source_epoch_journal.py \
  backend/tests/test_local_guarded_epoch_startup.py \
  skeleton/testing/test_docker_engine_epoch_startup.py
```

## Still explicitly blocked

The actual production deployment remains standalone Mongo by default.
This source change does not deploy a replica set, create credentials,
migrate existing epochs, establish complete external writer exclusion,
assert full conversation/memory side-effect acknowledgement, produce an
atomic Mongo/SQLite/Chroma backup, validate on-device GGUF inference, provide
a trusted Jeeves tokenizer/reviewer, qualify Windows/WSL2 or approve a
signed release. Dedicated physical exact-head evidence is needed before
any production writer opt-in or protected chat qualification.

**Draft / review only. No merge, release, live Docker mutation, user volume
copy, Mongo data write, live epoch migration or credential access.**

## Actual source collection override census

Before attaching the real backend conversation writer, the startup now
inspects **both** actual conversation collection handles. The engine
inspects its four canonical memory collection handles after constructing
the real repository and **before** index initialization or publishing the
writer. Any explicit `w:1`, `w:0`, `j:false`, forged collection, untyped
or incomplete handle set is denied. A plain PyMongo/Motor `WriteConcern()`
with an empty document is admitted **only** because the independent live
Mongo policy probe already established the stronger global server default.
This cannot discover arbitrary external writers or an unregistered database.

The memento transaction and retire/purge paths have also been hardened to
request `WriteConcern(w="majority", j=True)` directly. Rejection of the
newly opened engine Mongo client clears its runtime reference and closes
the client before any canonical memory writer is published. The long-lived
conversations/engine must still undergo independent end-to-end physical
write acknowledgement and release qualification.

Unit tests validate inherited/explicit journaled majority collections,
weak/unacknowledged overrides, incomplete or substituted handles,
backend refusal before epoch installation, and source-level engine
admission ordering. No production database, volume or Docker container is
changed by running these source tests.

## Read-only cross-service Docker command

A separate operator command inspects the already-running backend and Jeeves
engine from within their own existing Docker containers. No epoch overlay,
migration flag, stop, container creation or Mongo write is needed:

```sh
python scripts/local_ai_docker.py --mode cpu writer-policy-preflight
```

The command first performs the existing read-only running-container boundary
attestation and independent dual-service primary/linearizable epoch
preflight. It then runs `python -m
skeleton.persistence.docker_epoch_writer_policy --role engine` inside
`skeleton` and the equivalent `--role backend` inside `backend`.
Each process uses only its existing authenticated internal Mongo URI,
queries the same five bounded Mongo admin endpoints and returns an exact
JSON allowlist with a SHA-256 fingerprint of the authenticated Mongo
primary process. The operator requires those fingerprints to agree with
each other **and** the separate epoch preflight and requires matching
configured member/voter counts.

The operator returns only counts, booleans and a cryptographic primary
fingerprint; no raw Mongo hostname, URI, password, actor identity, memory
record, conversation content or driver exception. The presence of a real
server-side journal policy does not mean the write-path registry, migration
or protected chat is qualified. All such authority remains false in the
output. The current default standalone Mongo deployment is expected to
refuse the check until safely migrated with independently audited evidence.

The underlying module also supports synchronous read-only PyMongo
inspection for existing service containers, while backend and engine
startup continue to use the asynchronous client that actually owns
their production writers. The same strict five-read policy validator
is shared by both paths.

### Focused exact-head source test extension

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_local_ai_dual_writer_policy.py \
  skeleton/testing/test_docker_epoch_writer_policy.py \
  skeleton/testing/test_mongo_source_epoch_journal.py \
  backend/tests/test_local_guarded_epoch_startup.py \
  skeleton/testing/test_docker_engine_epoch_startup.py
```

Passing these source tests does **not** constitute physical Docker
validation; the latter requires an owner-controlled running deployment
with a real three-voter authenticated Mongo replica set. No test-only
synthetic Mongo can be substituted as proof of full application readiness.
