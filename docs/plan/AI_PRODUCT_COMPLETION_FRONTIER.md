# AI Product Completion Frontier — reverse build

This lane builds from the user-visible end of the standalone AI back toward the
already-established provider-independent execution spine.

## Why this frontier exists

The canonical Functional AI path already proves a local-model execution can pass
through governed tools, durable execution, independent verification, and
provider-independent evidence. That is necessary but not sufficient for a
usable AI product. A caller still needs a stable boundary that turns repeated
user requests into one restart-safe conversation without bypassing the lower
runtime.

This frontier therefore adds a **composition plane**, not a second authority or
agent runtime.

## Delivered contracts

1. **Durable session identity**
   - a session ID is permanently bound to objective, instructions, tenant, and
     data-class semantics;
   - reopening the SQLite store preserves that binding;
   - the same session ID cannot be silently rebound to different semantics.

2. **Idempotent turn identity**
   - `(session_id, request_key)` has one canonical payload digest;
   - a completed retry replays the persisted response instead of executing the
     model/tools again;
   - reuse of a request key with different input fails closed;
   - in-flight or failed request keys cannot be silently double-executed;
   - caller timestamps are not part of idempotency identity.

3. **Deterministic context compilation**
   - conversation history and supplied context are rendered deterministically;
   - external context is explicitly labeled data, not authority;
   - context text is escaped so it cannot forge framework delimiters;
   - bounded compilation drops external data before recent conversation;
   - current user input is never silently truncated;
   - a canonical SHA-256 binds the exact context supplied to the lower runtime.

4. **Serialized conversation turns**
   - at most one turn may be in-flight for a session;
   - concurrent requests cannot fork conversation history into conflicting
     branches;
   - completed history is replayed in ordinal order across process restarts.

5. **Lower-runtime correlation**
   - product requests derive deterministic Functional AI request IDs;
   - execution ID and operation ID must match the lower runtime's evidence;
   - inference, tool policy, effect proof, verification, and execution durability
     remain owned by `FunctionalAIRuntime` / `CognitiveExecutionRuntime`.

6. **Stable response envelope**
   - every response carries session/turn/request correlation;
   - response text is bound to execution result and evidence digests;
   - local model identity and tool-receipt count are surfaced;
   - replay is represented as a delivery property and is never persisted as new
     execution truth.

7. **Restart acceptance**
   - a real local Functional AI runtime is exercised through the product layer;
   - multi-turn history is recovered from durable storage;
   - a post-restart idempotent replay returns the same execution identity without
     rerunning the lower runtime.

## Non-authority boundary

This layer does **not**:
- grant tools or approvals;
- mark effectful actions successful;
- verify model answers;
- promote models;
- turn retrieved/memory text into trusted control;
- claim GI/SI or advanced-model quality;
- replace existing execution, evidence, security, or learning planes.

Those responsibilities remain in the canonical lower subsystems.

## Acceptance

The `AI Product Completion Acceptance` workflow compiles the product runtime and
runs:
- deterministic context/adversarial-boundary tests;
- durable multi-turn/idempotency tests through the real local
  `FunctionalAIRuntime`;
- the existing VS-001 regression to ensure the composition plane does not break
  the lower canonical acceptance.

This is deliberately a broad, end-to-end completion build from the product edge
inward.
