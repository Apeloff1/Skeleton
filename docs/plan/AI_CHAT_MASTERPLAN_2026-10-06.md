# AI Chat Masterplan — October 2026

Date: **2026-10-06**

Status: **active implementation plan**

Canonical assistant root: `skeleton/ai/assistant/`

Initial runtime contract: `machine/ai_chat_runtime_contract.json`

Initial implementation: `skeleton/ai/assistant/turn_runtime.py`

## Mission

Build one canonical AI chat runtime that composes Skeleton's existing
conversation authority, assistant control plane, model routing, memory, tool,
artifact, provenance, and durable execution systems.

The chat product must remain simple to use while the runtime is explicit,
replayable, fail-closed, evidence-bearing, and safe under interruption.

The project must not create a second provider stack, tool executor, memory
authority, or conversation store.

## Current foundation

Skeleton already contains the major planes needed for a strong chat runtime:

- server-authoritative conversation state in `backend/core/conversations.py`;
- canonical conversation contracts and reconstruction APIs;
- product assistant routing/context/tool/memory policy in
  `skeleton/ai/assistant/`;
- provider-neutral model routing;
- canonical privileged tool execution and durable tool receipts;
- context and memory closure gates;
- Jeeves chat UI and conversation cache reconstruction;
- exact-head CI patterns and independent receipt verification.

The implementation strategy is therefore convergence, not replacement.

## Non-negotiable architecture

The authoritative path is:

1. authenticated client request;
2. conversation authority admission;
3. durable turn operation;
4. trust-aware context compilation;
5. model/task routing;
6. bounded model execution;
7. structured tool proposal;
8. deterministic capability admission;
9. canonical tool execution;
10. receipt reconciliation;
11. verification;
12. authoritative assistant-message commit;
13. optional governed memory proposal;
14. terminal operation state.

The browser, mobile client, provider history, and streamed text are projections.
They are never the authoritative conversation record.

## CHAT-P0 — durable turn runtime

The first implemented slice introduces an append-only turn journal.

Required states:

- `RECEIVED`
- `ADMITTED`
- `USER_MESSAGE_COMMITTED`
- `CONTEXT_COMPILING`
- `ROUTING`
- `MODEL_RUNNING`
- `TOOL_REQUIRED`
- `AWAITING_USER`
- `TOOL_EXECUTING`
- `VERIFYING`
- `FINALIZING`
- `ASSISTANT_MESSAGE_COMMITTED`
- `MEMORY_PROPOSAL`
- `COMPLETE`
- `DEGRADED`
- `FAILED_RETRYABLE`
- `FAILED_TERMINAL`
- `CANCELLED`
- `QUARANTINED`

Every transition is immutable, sequence-numbered, request-bound, and
digest-chained.

### P0 guarantees

A restart must not:

- lose an already committed user message;
- fabricate assistant completion;
- skip verification;
- duplicate an ambiguous external write;
- cross a privacy boundary;
- silently reset resource consumption;
- break conversation ordering;
- lose provenance required for recovery.

### Consequential tool ambiguity

If a consequential tool may have started an external effect and no durable
receipt is available, the turn enters an ambiguity condition.

Recovery must choose receipt reconciliation before retry or model
continuation.

Blind replay is forbidden.

Read-only tool work with no external effect may be retried under the original
request-bound authority and budget.

## Resource governor

Every turn has hard ceilings for:

- wall time;
- input tokens;
- output tokens;
- model calls;
- tool calls;
- agent depth;
- parallel workers;
- retrieval queries;
- external writes;
- cost.

Child workers receive sub-budgets. A child budget cannot exceed the parent's
remaining authority.

This prevents recursive agent amplification and turns latency/cost limits into
runtime invariants rather than advisory telemetry.

## Context architecture

Context is compiled by trust class, not concatenated as an undifferentiated
prompt.

Target trust order:

1. immutable platform control;
2. product/system policy;
3. authenticated user configuration;
4. current user instruction;
5. approved durable memory;
6. conversation history;
7. retrieved private evidence;
8. retrieved public evidence;
9. tool output;
10. model-derived material.

Lower-trust evidence cannot promote itself into policy.

Context pressure must remove or compress lower-value history before trusted
control or the current request is lost.

## Conversation authority

The canonical conversation repository remains the only authoritative thread
and message store.

Future turn persistence integration must bind each operation to:

- thread id;
- expected thread version;
- causal user message id;
- branch id;
- operation id;
- AI result id;
- context id and digest;
- provider receipt refs;
- tool receipt refs;
- memory refs;
- citation refs;
- artifact refs.

The durable turn journal coordinates work around those authoritative records;
it does not replace them.

## Model routing

Models are capability endpoints.

Routing policy considers:

- task class;
- required modalities;
- privacy ceiling;
- quality floor;
- reliability;
- context capacity;
- latency;
- cost;
- provider health;
- jurisdiction;
- local-only requirements.

Fallback can never weaken privacy, safety, minimum quality, or required
capability.

A local-only request fails closed if no permitted local endpoint is available.

## Tool authority

Models propose actions; they never directly own privileged execution.

The required chain is:

`model proposal -> capability policy -> request-bound grant -> canonical
ToolExecutionRequest -> canonical tool runtime -> durable receipt`.

External or security-sensitive writes require explicit authority.

Idempotency identity is bound to operation and arguments. Reusing an
idempotency key with different arguments fails closed.

## MCP boundary

MCP is an adapter surface, not Skeleton's internal authority model.

Canonical Skeleton tool requests may be translated to MCP, native adapters,
HTTP APIs, files, operating-system runtimes, or other connectors.

Protocol evolution must not change the internal tool receipt, permission, or
conversation authority contracts.

## Memory

Memory retrieval and memory persistence are separate decisions.

Memory may store useful information but never capability authority.

Durable memory candidates must carry:

- origin;
- scope;
- timestamp;
- sensitivity;
- provenance;
- confidence;
- freshness;
- supersession status.

Sensitive memory persistence requires explicit policy admission.

## Evidence and factuality

Current or externally verifiable claims must route through evidence acquisition
before synthesis when freshness is required.

The target evidence path is:

`claim requirement -> source selection -> retrieval -> integrity/freshness
check -> dedupe -> rerank -> claim/evidence mapping -> synthesis -> citation
verification`.

## Verification

Generation and acceptance are distinct stages.

Verification may include:

- schema validation;
- tool-result consistency;
- citation existence;
- citation entailment;
- source freshness;
- policy conformance;
- sensitive-data leak checks;
- unsupported-claim detection;
- artifact integrity;
- structured-output validation.

High-assurance tasks may use an independent verifier in addition to
deterministic checks.

## Streaming

The durable operation stream should eventually expose events such as:

- `turn.accepted`
- `context.started`
- `context.ready`
- `model.selected`
- `generation.started`
- `generation.delta`
- `tool.proposed`
- `tool.approval_required`
- `tool.started`
- `tool.completed`
- `verification.started`
- `verification.completed`
- `message.committed`
- `turn.completed`
- `turn.failed`

Each event requires operation identity, monotonic sequence, event identity,
timestamp, schema version, and payload digest.

Client reconnect uses operation id plus last observed sequence.

## Attachments

Raw chat-inline attachment payloads are transitional.

Target ingestion:

`upload staging -> byte/size validation -> type verification -> malware
inspection -> content-addressed object -> sandbox parsing -> governance
registration -> attachment reference`.

File extension alone never establishes trusted file type.

Document text remains evidence, not system instruction.

## Multi-agent execution

Supervisor/Secretary/Worker authority remains bounded:

- Supervisor schedules and delegates;
- Secretary decomposes and coordinates;
- Worker performs bounded reasoning/proposals;
- privileged tool runtime performs admitted side effects.

Workers receive only the context, budget, and capabilities required for their
task.

Agent recursion is bounded by depth, worker count, wall time, tokens, tool
calls, writes, and cost.

## Failure policy

Provider timeout:
use circuit breaker and permitted fallback.

All providers unavailable:
preserve committed user state and terminate retryably.

Context overflow:
compact deterministically; never discard trusted control silently.

Tool timeout:
inspect durable receipt/status before retry.

Ambiguous write:
reconcile; never blindly replay.

Duplicate client send:
return/reconstruct the same idempotent operation.

Stream disconnect:
reconnect and replay from durable sequence.

Database interruption:
never fabricate completion.

Memory unavailable:
continue chat without durable memory if policy permits.

Retrieval unavailable:
do not claim freshness that was not obtained.

Safety/policy dependency unavailable:
high-risk actions fail closed.

## Observability

One chat turn should trace:

- admission;
- message commit;
- context compilation;
- memory retrieval;
- retrieval;
- model routing;
- model execution;
- tool authorization;
- tool execution;
- verification;
- conversation finalization;
- memory proposal.

Default telemetry must avoid raw prompt, file, memory, or secret capture unless
a governed diagnostic mode explicitly permits it.

## Closure gates

The completed chat system will require evidence for:

- conversation authority;
- turn replay;
- context integrity;
- model routing;
- provider isolation;
- tool authority;
- tool replay/reconciliation;
- memory authority;
- attachment security;
- streaming recovery;
- citation integrity;
- prompt-injection resistance;
- sensitive-data handling;
- budget enforcement;
- cost admission;
- agent-depth enforcement;
- crash recovery;
- provider failover;
- accessibility;
- frontend reconstruction;
- performance/load;
- chaos testing;
- adversarial testing;
- exact-head verification.

A checkbox is not completion evidence.

Completion requires implementation, regression tests, adversarial tests,
exact-head CI, and independently rehashed machine-readable evidence.

## Ordered implementation volumes

### Volume 1 — CHAT-P0 durable turn runtime

Status: implementation started in this branch.

Deliver:

- canonical turn states;
- legal transition graph;
- digest-chained event journal;
- hard execution budget;
- child-budget non-amplification;
- deterministic recovery planner;
- consequential tool ambiguity reconciliation;
- structural contract and exact-head closure gate.

### Volume 2 — durable persistence adapter

Persist turn events beside authoritative conversation operations with
optimistic version checks and restart reconstruction.

### Volume 3 — durable streaming projection

Publish operation events to clients with sequence replay, duplicate tolerance,
reconnect, cancellation, and terminal reconstruction.

### Volume 4 — context compiler v2

Add budget allocation, protected control reserve, provenance-aware compaction,
and adversarial trust tests.

### Volume 5 — routing v2

Bind turn budgets, privacy, endpoint health, provider receipts, and fail-closed
fallback into model placement.

### Volume 6 — tool recovery integration

Bind the turn runtime directly to canonical tool receipt reconciliation and
approval state.

### Volume 7 — governed attachment plane

Move PDFs/images/files from inline payload handling to governed
content-addressed references.

### Volume 8 — evidence and citation plane

Add freshness classification, source quality, claim mapping, and citation
verification.

### Volume 9 — verification plane

Add acceptance profiles, deterministic validators, optional independent model
critics, and quarantine semantics.

### Volume 10 — bounded multi-agent runtime

Add budget-splitting worker orchestration without granting subagents direct
privileged authority.

### Volume 11 — frontend chat v2

Consume durable event streaming and surface tool approvals, sources, recovery,
artifacts, and operation status without exposing internal control complexity.

### Volume 12 — qualification

Run failure injection, provider outage, database interruption, stream
reconnect, ambiguous write, prompt injection, memory poisoning, budget
exhaustion, and adversarial tool tests.

## Promotion rule

This masterplan describes the target system.

Individual volumes remain `implemented_candidate` until exact-head tests and
independent verification pass.

No runtime, manifest, document, or agent may fabricate completion, signatures,
evidence, or verification status.
