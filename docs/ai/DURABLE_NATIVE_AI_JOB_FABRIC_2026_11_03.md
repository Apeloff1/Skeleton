# Durable Native AI Job Fabric — operational delivery and exact constraints

## What this tranche changes

The source adds a real SQLite workload subsystem inside the existing offline
AI runtime. Jobs bind tenant/user/session/model/tokenizer and immutable input
hashes. The system uses bounded, durable submission, native-work fair claiming,
lease heartbeats, operator-only hold recovery, terminal result digests,
cancel requests and dependency-aware admission.

NativeChatEngine, native tokenizer and authoritative OfflineChatStore are
untouched. A worker invokes the existing OfflineAIService exactly once on its
stable request identity. If a generation or acknowledgement is ambiguous,
the queue does not auto-regenerate it: the held request must be independently
reconciled against the chat store by an operator.

## Source files and execution boundaries

The new package includes typed contracts, SQLite schema/transaction/audit,
bounded queue and fair scheduling, exact receipt limits, real native bridge,
owner-private state access, append-only integrity checks, consent-safe
observability, HMAC cursor, operator risk gates, telemetry freshness, explicit
recovery and a CLI that activates only a verified real local model.

672 machine-readable adversarial scenarios exercise real policy code under
private SQLite for 21 domains, alongside lifecycle, restart, bridge, target
dispatch and focused per-domain unittest modules. Scenario fixtures do not
produce real neural inference or magically supply approved model weights.

## Local commands

    python -m skeleton.ai.runtime.operational_ai.durable_jobs.cli
    python -m unittest discover -s skeleton/testing -p 'test_durable_jobs*.py' -v
    python -m compileall -q skeleton/ai/runtime/operational_ai/durable_jobs

Real local-model use requires a separately supplied and pinned compatible
checkpoint and the existing operational_ai durable chat bootstrap; use
python -m skeleton.ai.runtime.operational_ai.durable_jobs.worker_cli --help
for arguments. An absence of a verified model is an explicit release hold.

## Source and release assurances not established

No approved 1.9 GB bundle, real native model performance, actual device,
Windows native install, private same-UID attacker robustness, external tool
side-effects, independent security audit or release certification is claimed.
All mandatory exact-head workflows must pass on this branch after all changes,
and the dependent AI-only #4649 draft must qualify first.
