# Durable offline AI work control — executable native bridge

This package adds an operational, owner-bound job execution queue to the
existing Skeleton native local AI. It does not build a second transformer,
replace OfflineChatStore, train a model, execute game systems, silently fetch
weights, call a hosted provider or grant tools on model-generated text.

## Dependency-safe build order

1. canonical.py, spec.py: precise canonical identity, work shape and limits
2. schema.py, transaction.py, audit.py: fail-closed SQLite durable custody
3. store.py: stable requests, collision checks, quota, fair claiming,
   expiring leases, terminal results, cancellation, dependency and held recovery
4. admission.py, result_caps.py, state_rules.py: independent policies
5. bridge.py: actual existing OfflineAIService turn and authoritative receipt
6. observer.py, read_model.py, invariants.py: integrity-backed observation
7. privacy.py, pagination.py, risk.py: source-bound read boundaries
8. db_file.py: owner-private POSIX SQLite opening and file identity checks
9. worker_cli.py: real checkpoint -> verified service -> durable work -> reply
10. scenario_runner.py and test_durable_jobs*.py: threat acceptance

The work-store database is not a replacement for chat history. Existing
native core owns same-session generation, checkpoint binding and native chat
commit/replay. Expired or failed workers may be ambiguous after a chat commit,
so this queue holds such work and never automatically regenerates the answer.

## Real local-model invocation

Independently approve the compatible native checkpoint and SHA-256, and
install a private state directory. Then run worker_cli.py as a Python module,
with --checkpoint, --sha256, --license, --database, --memory-db, --journal-db,
--message and --request-id arguments. All real output comes from the actual
native runtime. There is no test backend exposed by this production CLI.

## Review acceptance and qualification holds

    python -m skeleton.ai.runtime.operational_ai.durable_jobs.cli
    python -m unittest discover -s skeleton/testing -p 'test_durable_jobs*.py' -v

There are 672 versioned executable job scenarios across 21 domains, plus
independent Python integration and SQLite tests. Fixture tests are not
model-quality proof, an actual device run, or release certification.

Do not claim a tested 1.9 GB model archive, licensed checkpoint, deployment
qualification, secure same-UID filesystem resistance, multi-process recovery,
safe training results, native throughput or consumer installation readiness.
Exact-head merge, security, hygiene, device and consumer gates are mandatory.
