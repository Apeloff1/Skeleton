# Full effect pass: governed AI side effects

This lane turns a completed local-AI transaction into real-world effects without allowing model text to become execution authority.

## Causal boundary

`FunctionalAIRuntime -> CoreExecution -> proposal decoder -> host authorization -> handler -> independent verifier -> durable commit -> memory/learning`

The model can only emit **proposals**. The JSON proposal grammar rejects authorization, approval, principal, policy, capability-set, or decision fields. Every host authorization is bound to the proposal SHA-256, subject, required capability, policy identity, issue/expiry window, and optional approval references.

## Runtime properties

- Default-deny authorization with an explicit capability authorizer for embedding.
- Strict proposal schema, byte/effect limits, unknown-field rejection, finite JSON values, and operation/tenant binding.
- Per-effect idempotency keys plus deterministic batch identity prevent accidental replay.
- Durable SQLite WAL ledger with transaction leases and a SHA-256 parent-linked event chain.
- Independent executor/verifier identities; required postconditions must be reported `true` before commit.
- Effect count, risk, kind, timeout, reversibility, and irreversible-batch policy gates run before authorization.
- Atomic failure path compensates reversible applied effects in reverse order. Any un-compensated or unacknowledged apply is fail-closed as `partial_failure` / in-doubt evidence; it is never mislabeled as rolled back.
- Global deadlines bound handler and verifier I/O; compensation remains separately bounded so safety cleanup still runs after an execution deadline.\n- Authorization backend outages terminate durably before mutation.\n- `dry_run` produces evidence but never requests authorization and never calls a handler.
- Memory and learning sinks run only after the entire batch reaches `committed`; observations cannot feed back into authority.
- Existing VS-001 is integrated through `FunctionalAIAdapter`; no provider or model authority is added.

## Qualification

Run:

```bash
python scripts/run_ai_effect_qualification.py
```

The deterministic qualification proves two independently verified state mutations, proposal-digest authorization binding, executor/verifier separation, tamper-evident event chaining, commit-only memory/learning, state effectiveness, and idempotent replay.
