# Deep operational AI reliability fabric — substantive SOTA expansion

The earlier operational AI native GGUF and SQLite stack is the canonical
execution owner. This new source package adds forty distinct, executable
fail-closed assurance controls, 880 source-controlled adversarial inputs,
forty per-domain evidence-ledger/adapter/test sets, and a second
operational flow plane for actual service integration.

The forty domains span source/model identity, installed bytes, tokenizer,
capacity, RAM and disk telemetry, queue admission, request replay, context
assembly, prompt role provenance, verified native output, streaming,
backpressure, cancellation, retries, session scope, memory consent/deletion,
retrieval/citation integrity, read-only tool grants/intents, journal,
outbox, snapshots, backups, ordered recovery, key/lease epochs, transport,
HTTP framing, installer custody, isolated process exit, health circuit,
telemetry, evaluation, canary execution, rollout, release evidence and
privacy. Each has two acceptance and twenty rejection fixtures.

## Operational coupling

`reliability_fabric/flows/preflight.py` requires nine named runtime
controls and binds all claimed identities to the *actual* supervised
service model and subject. `native_turn.py` then delegates to the real
`SupervisedAI.turn` and validates the committed native output receipt;
a replay is read-only through the existing SQLite spine. The flow package
also provides finite quotas/rate windows, monotonic time budgets,
native-health circuits, postcommit delivery credits, HMAC grants, read-only
tool intent plans, ordered restart evidence, source-bound model custody,
measured-device admission, private metrics, and release holds.

## Executable validation

```bash
python -m compileall -q skeleton/ai/runtime/operational_ai/reliability_fabric
python -m skeleton.ai.runtime.operational_ai.reliability_fabric.cli
python -m unittest discover -s skeleton/testing -p 'test_ai_reliability_*.py' -q
```

These commands must run on the completed exact-head checkout, never on
a partial source tree. No full model weights, generated model stand-in,
secret material or game features are included. The 880 cases are actual
JSON/Python contract inputs but they do not constitute an authorized
GGUF run, live laptop performance benchmark, rights review or release.

### Unresolved independent holds

All mandated final-SHA CI/security workflows, independent code and
legal review, real approved GGUF model/tokenizer source, clean Windows/WSL2
device installation, isolated native child cancellation proof, SQLite
cold-restart/durable replay, real memory pressure and frontend reachability
require separate qualification. No skipped, cancelled or queued gate
is accepted as a pass.
