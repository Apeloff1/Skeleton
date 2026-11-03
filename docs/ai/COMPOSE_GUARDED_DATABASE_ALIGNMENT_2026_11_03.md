# Studio C — default Compose canonical Mongo alignment (2026-11-03)

The default Compose backend uses `DB_NAME=tutolage` and the engine uses
`SKL_MONGO_DATABASE=skeleton`. A majority-durable canonical epoch in one
logical database cannot fence source mutations in the other. This is an
**existing fail-closed activation blocker**, not a reason to migrate or
rewrite an existing Mongo volume automatically.

The backend now receives only the non-secret engine database NAME
(`SKL_CANONICAL_MONGO_DATABASE=skeleton`) for read-only operator preflight.
`python -m skeleton.app.compose_guarded_preflight` checks the backend
database name against this declared engine name **before creating any
Mongo client**. It reports fixed reason codes
`canonical_database_identity_mismatch` or
`canonical_engine_database_identity_required` with no credentials or actor
scope in output. Matching names do not prove matching Mongo clusters,
authenticated writer roles, deployment ownership, or an active model. The
result therefore never claims `guarded_local_ai_ready`.

Operators must explicitly reconcile canonical owner database and cluster
identities, review backups/restores, audit all writers, establish an
authenticated replica-set primary and independently operated signed reviewer,
then validate exact model/tokenizer binding and restart/revocation before
activating. The default Compose Mongo remains standalone and unchanged.
Studio D may show these reason codes while leaving first-run setup available.

Focused regression:
`python -m unittest skeleton.testing.test_compose_guarded_preflight`

This change is source-only until tests and exact-head CI actually succeed.
