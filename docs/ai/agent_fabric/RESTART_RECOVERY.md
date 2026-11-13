# Restart Recovery — operational AI agent fabric

## Scope

Running or held execution requires operator review; no blind inference or tool retries.

The operating boundary is an offline, owner-bound AI runtime using the existing
model and persistence systems in Skeleton. It never executes a hosted model,
introduces game-system code, or upgrades model-generated text into permission.

## Executable workflow

1. Operator provisions private state and separately approves model rights.
2. Caller's principal and model/tokenizer identity are fixed before work.
3. Caller submits a bounded DAG with exact dependencies, stable IDs and a
   canonical content digest. Model-generated plans are proposals only.
4. The scheduler checks dependencies and claims one durable operation with
   a fenced attempt. Conflicting calls fail closed.
5. A model step calls the existing native `ExecutionSpine`; read steps require
   an independent knowledge provider and privileged tools require a signed,
   one-time, explicitly scoped operator grant.
6. A verified receipt and its audit-chain event are committed in the same
   SQLite transaction; no hidden regeneration is accepted.
7. If the worker fails, a held state remains for operator review. Uncertain
   side effects are not retried by an autonomous worker.
8. Diagnostics expose hash-bound metadata only, avoiding prompt and result
   content in operational exports.

## Local implementation map

- `core/`: typed identity, finite limits, canonical JSON and digest contracts.
- `planning/`: deterministic DAG compilation, dependency closure, risk analysis.
- `custody/`: SQLite atomic state, idempotent plan admission, audit event chain.
- `execution/`: explicit external ports, step receipts and bounded work loop.
- `authorization/`: independently signed and single-use grants.
- `context/`: role-safe source selection and cryptographic provenance.
- `evaluation/` and `assurance/`: independent tests and observational metrics.
- `transport/` and `operations/`: typed local commands and read-only diagnostics.

## Release holds

This source package remains an unqualified draft. Fixture-backed unit tests
only exercise code contracts. A release claim requires actual approved GGUF
weights, complete first-install and native generation, independent permissions
review, target-device capacity and durability qualification, and successful
mandatory final-head GitHub checks. Absent evidence is not a pass.

## Threats deliberately held

- Prompt injection embedded in retrieved source text
- Reused IDs with conflicting instructions or principal identity
- Unbounded context, results, plans or source payloads
- Database or audit-chain corruption and unexpected cross-process writes
- Repeated side effects after ambiguous worker termination
- Forged approvals, mismatched argument digests, unauthorized tool scope
- Real-model hallucinations, poor quality, or hardware/OOM behavior

The engineer operating the system must review the exported evidence and
never substitute workflow metrics for verified checkpoint behavior.
