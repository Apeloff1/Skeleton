# AI Product Completion Frontier — reverse build

This lane builds from the user-visible end of the standalone local AI inward to
the already-established provider-independent execution spine.

The implementation is intentionally **non-atomic** and end-to-end, but it does
not create a second authority model.

## Canonical path

```text
user turn
  -> ConversationThread / ConversationMessage
  -> SQLiteConversationRepository reference authority
  -> canonical ContextSegment sources
  -> ContextCompiler trust/budget selection
  -> provider-context projection
  -> FunctionalAIRuntime
  -> CognitiveExecutionRuntime
  -> local model + governed tools + verification
  -> durable AIExecutionResult
  -> canonical assistant message
  -> stable product response envelope
```

The assembled backend can use its production conversation authority while this
portable lane proves the same canonical contracts against the SQLite reference
implementation.

## Delivered contracts

### 1. Canonical conversation authority

The product edge reuses `ConversationThread`, `ConversationMessage`, exact-next
sequencing, optimistic thread versions, branch lineage, causal user/assistant
links, and the existing conversation repository. The provisional duplicate
session store from the first reverse pass was removed.

### 2. Canonical trust-aware context

Conversation messages enter the existing context source adapters. External
product context is accepted only as evidence-class canonical `ContextSegment`
values. Product callers cannot inject trusted control, tool schemas, tool
results, or conversation-role segments through that evidence input.

The existing `ContextCompiler` remains authoritative for:
- trust inspection;
- tenant/purpose admission;
- deterministic ranking;
- token budgets and omission;
- source snapshots;
- context digest identity;
- provider projection that labels non-conversation evidence as untrusted data.

### 3. Full semantic idempotency fence

Each user turn persists a reserved SHA-256 identity covering:
- user message;
- idempotency key;
- external context segment identities/content digests;
- attachment refs;
- allowed tool IDs;
- model/tool/repeat budgets.

A retry with the same idempotency key but changed execution semantics fails
closed before model execution.

### 4. Runtime policy/compiler identity fence

A second digest binds the turn to:
- exact instruction-policy identity;
- canonical context budget;
- context compiler version.

A process restart cannot silently replay an old execution under a changed
product policy/compiler identity and then label the result with a new context.

### 5. Exact execution correlation

The canonical user-message identity deterministically derives the Functional AI
request, operation, and execution IDs. The committed assistant message binds:
- operation ID;
- content-addressed AI result identity;
- context ID/digest/compiler version/source snapshot;
- tool receipts;
- memory refs;
- evidence/citation refs;
- artifact refs.

The response envelope independently re-checks those bindings against the durable
`AIExecutionResult`.

### 6. Crash-safe execution/commit recovery

There is an explicit regression for the dangerous window:

1. local model execution completes and is durably finalized;
2. assistant-message commit crashes;
3. process retries the same canonical turn;
4. the durable execution result is recovered;
5. the assistant message is committed;
6. the model is **not invoked a second time**.

This prevents duplicate cost/effects from a product-state commit failure.

### 7. Durable cancellation

Cancellation first records the execution cancellation request, then interrupts
the active local inference task. `LocalInferenceEngine` propagates task
cancellation to the worker's cooperative cancellation event.

The cognitive runtime then materializes one terminal `cancelled` result.
Conversation authority receives a deterministic system-derived cancellation
marker so the thread no longer ends on an orphan user turn and later turns can
continue without fabricating an assistant success.

### 8. Shared in-process execution join

Concurrent retries of the same canonical execution join one active async task.
Ordinary client coroutine cancellation is shielded from the durable execution;
only the explicit cancellation path owns authority to stop the operation.

### 9. Full restart replay

Acceptance closes and reopens both conversation and execution repositories,
constructs a fresh runtime, and proves the same response/execution/context
identity is replayed without invoking local inference again.

### 10. Lower safety planes remain authoritative

This bridge does not:
- grant tool authority or approvals;
- verify model claims;
- declare side effects successful;
- bypass postcondition proof;
- promote models;
- turn retrieved/memory text into trusted control;
- replace execution, evidence, governance, security, or learning planes.

Effectful-tool postcondition enforcement remains below this layer in
`CognitiveExecutionRuntime`, so a permissive external verifier cannot turn an
unproven side effect into publishable success.

## Acceptance gate

`AI Product Completion Acceptance` now compiles the product bridge and executes:
- canonical context compiler regressions;
- canonical conversation repository regressions;
- canonical product multi-turn/trust/correlation acceptance;
- full semantic-idempotency fencing;
- runtime policy/compiler drift rejection;
- execution-success / assistant-commit crash recovery;
- in-flight local-model cancellation;
- full repository reopen/replay without reinference;
- existing VS-001 local Functional AI regression.

This frontier closes the product-edge seam by using existing authorities more
deeply, not by building a parallel chat stack.
