# Guard-dominance and outbox-custody hardening — Docker local AI

**Purpose:** Close source-level bypasses in the existing canonical Mongo
writer-surface census before enabling a real multi-process writer migration.
This is a static, read-only qualification; no Docker, Mongo, accounts, model
files, or private application state is required.

## Failures addressed

A previously checked `require_actor_writer()` call that occurs **before**
a Mongo write in source order is not sufficient proof of source custody.
A developer could put the call inside `if False:`, a nested function, a
`try/except` that swallows its denial, or pass an unrelated actor ID.
The code would have passed a naive line-number check while the real write
path could execute without a durable actor epoch.

The updated AST checker uses a deliberately restrictive source contract:

* The five direct Mongo-writing private memory helpers must call
  `self._require_canonical_writer(tenant_id=<actual record/proposal tenant>,
  actor_id=<actual record/proposal subject>)` as their **first executable
  statement** (ignoring the docstring). The AST must show an actual
  self-method call, no positional or omitted identity arguments, and the
  exact producer identity.
* Conversation WAL `_recover_prepared` is special because legacy
  non-protected callers still exist. Its first statement must bind
  `epoch = getattr(self, "canonical_source_epoch", None)`; its second
  must be the exact `if epoch is not None` branch with no `else`,
  which immediately invokes
  `epoch.require_actor_writer(tenant_id=tenant_id, actor_id=owner_id)`.
  The guard must dominate all direct writes, never be concealed in a
  nested block, and never be checked for the wrong actor.
* Public write methods continue to require their exact
  `@fence_conversation_write`, `@fence_memory_commit`,
  `@fence_memory_tombstone`, or `@fence_memento_write` decorators.

The only currently allowed unfenced memory mutation is a **derivative
projection-outbox publication acknowledgement**, not a canonical memory
source write. Its previously broad exemption is tightened to exactly one
`self.projection_outbox.update_one` with no kwargs and the precise filter
`repository_namespace=self.repository_namespace`,
`event_id=event_key`, `published_at=None`. Its update must be exactly
`{"$set": {"published_at": _iso(instant)}}`. No upsert, changed tenant,
arbitrary event, missing pending predicate, source revision increment,
record write, or additional update operator retains the exemption.

## Hostile source regression cases

Test fixtures modify temporary copies of the three known production Mongo
classes only. The tests deny unreachable guard, nested guard, later guard,
try/except-swallowed guard, wrong subject, wrong tenant, mutated source
record, wrong conversation recovery actor, false legacy-mode test, foreign
projection namespace/event, missing pending-state predicate, outbox upsert,
extra `$inc` source mutation, and altered write method ownership.

This complements the prior suite's static `$merge/$out` aggregate denial,
raw Mongo command bypass denial and exact covered mutator list. It is
**not** a proof that independent external writers, maintenance scripts or
other deployment processes have adopted this actor epoch. Both production
writer settings remain OFF by default.

## Qualification on exact source head

```sh
python -m compileall -q \
  skeleton/persistence/docker_writer_surface_census.py \
  skeleton/testing/test_docker_writer_surface_census.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_docker_writer_surface_census.py
python scripts/local_ai_docker.py --mode cpu source-writer-census
```

No test success is claimed without an exact-head receipt. Even a fully
passing static source suite must not authorize protected Jeeves chat,
migration, external writer registry, coherent restore, or a release.
