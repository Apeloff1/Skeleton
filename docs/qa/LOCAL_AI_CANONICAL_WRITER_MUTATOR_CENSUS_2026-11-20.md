# Local Jeeves Docker — canonical Mongo mutator source census

**Read-only, no Mongo connection, no actor migration, no Docker container
mutation, and no claim of a complete external writer registry.**

The immediate goal is to detect source changes which could silently bypass
the newly journaled-majority Mongo actor epochs. A running replica set and
successful synthetic compare-and-swap experiment are insufficient if a new
conversation or memory mutation method can be added outside writer custody.

## What is checked

The static census parses three known production Python classes using
Python's AST, rather than string matching or runtime service imports:

1. `MongoConversationAuthority` in `backend/core/conversations.py`.
2. `MongoMemoryRepository` in `skeleton/persistence/memory_repository.py`.
3. `MongoMementoAuthority` in
   `skeleton/persistence/mongo_memento_repository.py`.

It enumerates direct PyMongo/Motor mutations including `insert_one`,
`update_one`, `find_one_and_update`, deletes, bulk writes, replacement
operations and database/collection drops. All known direct write methods
must fall into exactly one explicit category.

| Surface | Required protection |
|---|---|
| Conversation thread and message mutation methods | Exact `@fence_conversation_write` decorator |
| Memory `commit` / `tombstone` | Exact `@fence_memory_commit` or `@fence_memory_tombstone` decorator |
| Memento publication / retirement | Exact `@fence_memento_write` decorator |
| Private conversation recovery and memory CAS helpers | Bound actor/canonical writer guard appearing before first direct Mongo mutation |
| Legacy governed conversation deletion | Mandatory first-statement denial when a protected epoch is installed, before deletion planning |
| Memory projection outbox publication acknowledgement | Strict exemption limited to a single `self.projection_outbox.update_one`; cannot mutate canonical memory records |

For every class, the **exact set** of methods with direct Mongo writes is
compared to a reviewed hardcoded inventory. A method added, removed,
renamed, newly undecorated or newly given a different mutation causes a
source qualification denial. A missing early internal actor guard, altered
protected deletion denial or scope-widened outbox acknowledgement also
fails.

The source reader only admits the three listed paths under the canonical
repository root, rejects symlinks, missing files, malformed UTF-8 and any
single source file over 2 MB. No private runtime record is read.

## Operator command

```sh
python scripts/local_ai_docker.py --mode cpu source-writer-census
```

It executes a *local static source check only*. It does not contact a
Docker daemon, Mongo or an AI provider; it requires no image, model,
credential or running service. It reports method/call counts and explicit
non-authority flags. The same check can run as an installed module:

```sh
python -m skeleton.persistence.docker_writer_surface_census
```

## Explicit limits and future acceptance

This census covers direct writes in the **three named classes only**. It
does not inspect dynamic reflection, third-party packages, services
outside these classes, direct Mongo admin maintenance scripts, external
deployment writers, physical replication durability, actor migration,
cross-process writer coordination, complete quiescence, logical database
restore or authenticated Jeeves inference. The projection outbox flag
is metadata-only and does not imply exactly-once publication; it remains
subject to separate projection-replay and idempotency qualification.

A passing source census must **never** set
`external_writer_registry_exhaustive`, `migration_quiescence_verified`,
`protected_jeeves_chat_qualified` or `release_authorized` to true.

Source qualification:

```sh
python -m compileall -q \
  skeleton/persistence/docker_writer_surface_census.py \
  skeleton/testing/test_docker_writer_surface_census.py \
  scripts/local_ai_docker.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_docker_writer_surface_census.py
```

The unit suite mutates only temporary fixture copies of the three source
files. It verifies that removing a decorator or an internal guard,
introducing a new direct write, weakening deletion denial, corrupting
projection scope or substituting a symlink cannot pass.

**Review-only. No production database writes, Docker volume changes,
GGUF inference, merge, release or epoch migration.**

## MongoDB aggregate write-stage denial

Mongo `aggregate()` is often a read, but a pipeline containing
`$out` or `$merge` can modify a collection. Counting only methods
with `insert_one` or `update_one` would leave this bypass open.

The census therefore separately inventories the three known
conversation read-aggregation sites. They must preserve the exact
static ordered stages:

- `chat_history_dependencies`: match → project → group
- `active_transcript`: match → project → group
- `_regeneration_recovery_refs`: match → sort → limit → project

For the one pipeline defined in a local variable, the source must
retain exactly one earlier literal list assignment. Reassignment,
mutating `append/extend/insert` calls, dynamic foreign pipelines,
new aggregation call sites, unexpected stages or write-capable
`$out/$merge` stages fail closed. This protects the *known* aggregate
sites only; no claim is made about external services or dynamic raw
Mongo commands beyond the enumerated production classes.
