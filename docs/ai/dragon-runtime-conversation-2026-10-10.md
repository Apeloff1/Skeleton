# Dragon runtime and conversation integration — 2026-10-10

Scope: retained resource accounting, authenticated foreground interaction,
hardware-bounded chat context, canonical ten-step projection hooks, indexed
conversation context and governed deletion. This does not qualify the full game
builder, install model weights or certify consumer hardware or legal clearance.

## Runtime ownership and installation

DragonExecutionPool requires the application's existing GlobalResourceScheduler
and an explicit ResourceEnvelope. It never discovers or creates physical
capacity. It retains at most 128 owner executors by default (operator configurable
1–1024), without eviction or request-level budget reset. Each owner has one
serialized executor and cumulative governor. Capacity exhaustion defers practice;
a full pet owner pool does not block a new foreground user. Foreground leases
are separately bounded (64 by default), globally pause all pool workers, include
workers created during the request, and unwind on HTTP errors/cancellation.

install_dragon_runtime(app, shared_scheduler, envelope) mounts that pool and the
Academy's executor factory. Reinstalling is rejected because it would erase
retained accounting. backend/server.py lifespan calls mount_configured_dragon_runtime:
operators may supply app.state.global_resource_scheduler and
app.state.dragon_resource_envelope before startup. Lifespan restarts reuse the
same pool, and reject replacement with a different ledger/envelope. Missing
configuration creates no scheduler and leaves guarded practice unavailable.
A distributed/multiprocess deployment must supply its truly shared resource
integration; this process-local pool cannot manufacture cross-process capacity.

The primary authenticated AI /chat HTTP route holds foreground priority while
processing its request. It samples the configured execution host's verified
hardware before provider initialization. Thermal/memory/telemetry deferral
returns 503 and performs no chat work. The canonical context compiler caps the
request's context capacity from the resource plan; output/policy/safety/tool
reserves and segment bounds scale consistently. This is a conservative token
budget, not an exact allocator or GPU-memory measurement. An unavailable or
oversized current turn is rejected rather than silently truncated. The software
waiting toy remains independent of model execution.

This hook covers the HTTP request lifetime, not an entire delegated engine turn
after its HTTP response. Other assist/generation endpoints remain compatibility
paths. Backend-host telemetry is not proof of a phone client's rendering or
local-model capability. All-app/device and delegated-turn acceptance remain open.

## Canonical conversation projection

The Mongo conversation authority owns all messages and commit/recovery semantics.
An optional DragonConversationBinding is called after a tenth committed sequence
and on idempotent replay. It fetches at most ten active-branch, committed message
metadata records. Raw content is omitted from the Mongo projection and replaced
with canonical message references before constructing the checkpoint window.
A branch fork that does not supply ten contiguous active-branch sequences is
skipped. Projection failure cannot roll back or duplicate a canonical message.
Counters report written/skipped/degraded outcomes without transcript logging.

Install the typed binding with install_dragon_conversation_binding(authority,
binding), or provide app.state.dragon_conversation_binding for the lifespan hook.
Its connection_factory must use the existing durable Dragon SQLite store, close
connections, and enforce a short native busy timeout (the acceptance fixture
uses 50ms). Its asynchronous policy_reader must resolve CURRENT consent from
canonical authorized retention policy. No HTTP JSON flag, model answer, cached
permission, or prior checkpoint can replace that policy authority. No default
reader, blanket consent, consent-management API or automatic training is added.

Policy records bind tenant, owner and thread, expiry no later than seven days,
explicit game-topic factors, retention_consent and a separate boolean
training_consent. None means no available consent; explicit false retention
means revocation and physically clears the projection. Re-consenting the same
thread may wait for its short deletion fence; a new conversation is independent.
Invalid or expired policy denies creation/context access. The stored bullets are
interest signals, not factual knowledge or hidden reasoning. A stored training
flag does not itself authorize a training job.

At inference, the authority revalidates current thread/branch/version and returns
at most three matching checkpoints. They become canonical ContextSegments with
DERIVED_UNTRUSTED trust, conversation-summary kind, actual canonical token
estimates and original message-reference provenance. The context compiler admits
them through its existing budgets. The authority rejects foreign-tenant,
control-trust, mandatory or oversized injected segments. Training eligibility is
always false in inference projections. The API never adds these as instructions.

repair_dragon_checkpoint reauthorizes and rebuilds one specified ten-step window
from retained canonical metadata. It is a bounded operator/worker method, not
an autonomous catch-up loop. Automatic replay does not guarantee repair of every
older checkpoint after process loss; callers must schedule bounded rebuilds.

## Deletion, races and retention

Before governed physical deletion/acknowledgement, the authority clears the
thread's derived checkpoint/postings. Failure blocks that physical deletion
step and acknowledgement. A SQLite write-serialized 300-second negative-only
fence prevents already authorized, bounded in-flight callbacks from resurrecting
the deleted projection. Fresh canonical policy/thread authorization must still
reject deleted conversations after the fence expires. Fences confer no consent.
When 1000 live fences for one owner are reached, cleanup coarsens to one temporary
owner-wide write fence rather than denying deletion or growing metadata without
bound. This can temporarily defer other checkpoints for that owner.

Projection callbacks and context reads have a 250ms asynchronous deadline.
Native synchronous SQLite work must retain its own busy/size bounds; asyncio
cannot interrupt an unbounded synchronous callback. No detached threads are
introduced. Deleted/expired content is not a context fallback. Retrieval checks
payload/digest size in SQL before materialization and verifies its local digest.
Digests are integrity identities, not authentication or legal review receipts.

Expiry cleanup is available through the canonical adapter and runs on admitted
checkpoint writes. The deployment still must wire storage housekeeping for cold
expired rows and its canonical retention/consent UI. These gates remain open.
The Mongo retention/governance owner remains authoritative for physical storage
quotas, consent revocation, source deletion, export and training eligibility.

## Construction, acceptance and rollback

L00–L03 preserve resource, conversation and retrieval owners; no provider SDK,
credential route, service root or physical store is introduced. L04–L07 implement
retained admission, foreground cancellation, immutable commits, scoped context,
revocation/deletion fencing and bounded recovery. L08 exposes non-content counters
and pool occupancy/accounting. L09 bounds owner/foreground capacities, quotas,
context, callback deadlines, payload materialization and parser-cache retention.
L10 covers actual callback/HTTP/context-compiler and SQLite reopen integration.
L11 adds rebuildable fence tables without changing message schemas. L12 rollback
removes consumers; canonical transcript data remains intact and derived tables
can be discarded under retention policy. L13 remains open for deployment policy
configuration, distributed-ledger integration, cold expiry and consumer devices.

The mandatory provider validator originally exited 137 with its large AST cache;
an identical-check bounded-cache invocation then passed. Its AST and source caches
now retain 128 recent files instead of 16384. Compact import summaries preserve
their larger cache. Eviction never skips a source or relaxes isolation checks;
evicted source is reparsed. Focused tests verify eviction and changed-file
provider-import detection. This bounds cache entries, not per-file AST size or
whole-process RAM. The unmodified validator command is rerun after the repair.

Six old backend chat tests fail identically on untouched baseline 79fe3870:
three in test_ai_chat_conversation_authority and three in
test_ai_chat_conversation_finalization. Their durable lifecycle fixtures reach
unconfigured Mongo or a closed loop before the changed projection boundary.
These failures are not masked; full chat end-to-end acceptance is not declared.
The required implementation-notes gate also retains the independently reproduced
VOL-000.existing_evidence staleness. No unrelated volume dossier is bulk-rewritten.

Sign-off: Codex, 2026-10-10, limited to implementation and stated acceptance.
No enterprise grade, completed volume, release permission or legal certainty.

## Local validation checkpoint

The full Dragon/reviewed-knowledge/pyramid run passes 1064 tests and 11 subtests,
with 12 skips. The focused backend runtime, projection, Academy and canonical
storage/governance/regeneration run passes 59 tests. Architecture, construction,
capability interfaces, superiority schema, state topology and global resource
contract checks pass. This supersedes neither the six reproduced baseline chat
failures nor the stale implementation-notes gate. Provider bootstrap and hosted
exact-head workflow results are recorded separately after completion.
