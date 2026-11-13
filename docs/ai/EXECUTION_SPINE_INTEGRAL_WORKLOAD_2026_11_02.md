# Integral operational AI execution spine — MBW-04 / MBW-07

This change builds an executable, owner-scoped **offline inference custody path**, rather than another game-system scaffold. The system requires a verified local native model with the exact model/tokenizer identities and explicitly refuses provider fallback, fake inference, or model-initiated tool execution.

## Critical-path behavior

1. **MBW-00 (identity/contracts):** strict principal, model, tokenizer, session, request, finite budgets, canonical serialization and digest checks. Identity is never inferred from generated text.
2. **MBW-01 (durability):** SQLite-WAL/full-sync single-store authority for sessions, pending intents, turns, append-only hash chain, and transactional outbox. Atomic journal/outbox writing in the *same* commit prevents the formerly observed post-turn audit gap. Exclusive private state/sidecar inspection and foreign-key checks hold unsafe files.
3. **MBW-02 (inference/evidence):** direct bridge to `operational_ai.model.native.Generated` receipts from the existing native/GGUF backend. Deterministic bounded context windows retain all older turns durably while explicitly counting omissions. Exact tokenizer preflight is used where exposed; the native backend must still enforce true context capacity. Evidence is lower-trust quoted data, not instructions, and source identity is pinned to the owner. Encrypted memory bridge uses the existing sealed-memory store.
4. **MBW-03 (tool authority):** separate HMAC effect grants, exact argument digests, expiration, bounded allowlisted tool functions and durable at-most-once attempts. A crash around an external effect stays *ambiguous* and is never invisibly retried.
5. **MBW-04 (orchestration):** cross-process session flock, idempotent request reservation, finite inference leases, fenced CAS commits, cancellation checks and explicit recovery holds. No concurrent session mutation and no implicit inference replay on failure. Native result digests are checked independently.
6. **MBW-05 (product):** typed content-free receipt projection and owner-filtered committed-event cursor; no uncommitted token emission is claimed.
7. **MBW-06 (qualification):** canary executes the real backend when available, producing only hash/usage/timing evidence. It does not prove factual answer quality or full hardware readiness.
8. **MBW-07 (first install):** a Linux/operator CLI invokes the existing hash-verified GGUF activation, principal-bound private state, transactional execution spine, and read-only doctor. Required CI/security/model/installation checks remain release holds.

## Operator entrypoints

```sh
# Requires a REAL approved GGUF model manifest/shards and llama-cpp-python.
python -m skeleton.ai.runtime.operational_ai.deployment.production.cli \
  --model-root /operator/approved-model --state-dir /operator/private-ai-state \
  --tenant local --subject operator --prompt 'Explain this repository plan.'

# Read-only receipt/state doctor (requires a preexisting identity binding):
python -m skeleton.ai.runtime.operational_ai.deployment.production.doctor \
  --state-dir /operator/private-ai-state --tenant local --subject operator \
  --model-sha256 <actual-64-hex> --tokenizer-sha256 <actual-64-hex>

# Real native inference canary, not a unit-test mock:
python -m skeleton.ai.runtime.operational_ai.deployment.production.canary \
  --model-root /operator/approved-model --state-dir /operator/private-ai-state \
  --tenant local --subject operator
```

The private state directory must preexist with mode `0700`, and all generated database files, SQLite sidecars, and lock files must be private owner-only regular files. No model archives or weights are checked into ordinary Git.

## Recovery, reversibility and known holds

- The `requests` table is the only authority for request execution. A failed backend leaves a pending intent; after expiry an authenticated, independently approved recovery CLI can **hold** it. It never re-runs the model, guesses a response, fabricates a completion, or resends an external effect.
- A completed turn and its audit hash-chain and outbox are committed together. An outbox event can be delivered and acknowledged idempotently. Consumed effects never silently repeat.
- Context is budgeted and *loss-accounted* rather than falsely represented as full-context retention. Exact in-memory history is reconstructed from all stored turns; long context over native capacity is trimmed at whole-turn boundaries.
- SQLite contents are plaintext at rest under OS private-file controls. This is **not** full-disk encryption; the separately connected long-term memory store uses its own sealed encryption. Backup, user deletion, key rotation and multi-host replication must be separately qualified.
- The GGUF backend reports a model-bound tokenizer digest; it is not independently cryptographically attested. A third-party exact tokenizer proof, licensing review, device/hardware qualification, real-first-install test, native-model end-to-end check, full CI and security gates remain mandatory.
- No skip, pending, cancelled, superseded or failed check counts as passed.
- Package builder 1.9 GB size contract is unaffected; no synthetic package bytes are created.

## Focused tests

`PYTHONPATH=. python -m unittest skeleton.testing.test_ai_execution_spine -v`

All deterministic fixture tests exercise code paths but do **not** substitute for a real operator-approved checkpoint, live model, GPU/device test, or exact-HEAD CI.
