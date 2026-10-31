# KV tier migration write-ahead custody

A physical KV page migration can partially complete before a crash or an
adapter error. Replaying the same plan may duplicate or corrupt an opaque
backend handle. The migration journal writes a signed, bounded intent before
the first adapter call and commits a signed per-page receipt afterward.

`KVJournaledTierController` wraps the canonical
`KVLiveTierController`. Its `plan_live()` still requires a source-labelled
fresh OS pressure sample. Its `apply_once()` commits a RUNNING intent before
the second live probe and any page movement. A failed probe, crash, lost
response or failed journal commit leaves the plan unresolved and **never**
automatically retries the physical adapter.

A successful call returns the canonical `TierApplyReceipt`, including
explicit rejected moves. A committed receipt can be read after restart
using `KVMigrationJournal.recover_committed(plan)`, without executing a
backend. A RUNNING intent requires an authorized operator to inspect actual
resident pages and storage adapter custody; this module does not guess.

The journal contains only page keys, inventory and plan digests, source/target
tier labels and bounded receipts. It never persists KV tensor bytes,
prompts, weights or backend handles. The application must provision an
exclusive securely opened SQLite connection, an independent key, bounded
disk reserve and storage adapter with its own quotas and integrity checks.
This is not an independently monotonic anti-rollback anchor, a GPU driver,
or device qualification. Tests use simulated CPU-to-disk page moves.

Focused simulated regression:
`python -m pytest -q skeleton/testing/test_kv_migration_journal.py`.

**Critical partial-failure fence:** If the canonical adapter reports any
rejected move, the journal deliberately remains RUNNING. An adapter may have
moved a page before raising, so a rejection is not proof of no side effects.
No further plan is admitted until an authorized storage reconciliation.
