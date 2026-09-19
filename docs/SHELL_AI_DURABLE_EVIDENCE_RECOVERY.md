# Shell AI Durable Evidence and Recovery

## Purpose

The AI shell now has two classes of evidence.

Process-local evidence is optimized for fast runtime checks.

Durable evidence is designed to survive service restarts and multi-worker operation.

This document explains how those layers fit together.

The durable layer is not an alternate execution path.

It observes and commits evidence produced by the existing reviewed execution path.

## Core objective

A restarted worker should be able to answer five questions without asking a model.

What plan was reviewed?

What authority allowed it to run?

What actually executed?

What evidence belongs to this AI session?

Can the evidence still be trusted?

Recovery must never depend on reconstructing hidden reasoning.

Recovery must never depend on re-running a command merely to discover whether it ran.

## Evidence layers

The durable evidence stack contains:

ContentAddressedEvidenceChain.

DistributedReceiptChain.

DistributedAIDecisionJournal.

SessionExecutionEvidence.

SessionJournalEvidence.

AISessionCheckpoint.

AIRecoveryCheckpoint.

AIDecisionProvenance.

AIAuditAnchorStore.

AIExecutionEvidenceFinalizer.

Each layer has a separate job.

## Content-addressed evidence chain

ContentAddressedEvidenceChain is the generic durable append primitive.

Every node contains:

sequence.

previous hash.

node hash.

kind.

bounded payload.

The node hash is SHA-256 over canonical serialized content.

The storage key is derived from the node hash.

Nodes are immutable by convention and verified on read.

## Head record

Only one tiny record is mutable.

That record is the evidence head.

The head contains:

latest committed sequence.

latest committed node hash.

The head advances with compare-and-swap.

## Why nodes are written before the head

A writer builds an immutable node first.

It stores that node by content hash.

It then attempts to move the head.

If another writer wins first, the losing node can remain unreachable.

An unreachable immutable node does not corrupt the committed chain.

This is safer than mutating a large append list in place.

## CAS conflict behavior

A CAS exception is not automatically treated as contention.

The chain reloads the head.

If the head changed, the writer treats the event as a race and retries.

If the head did not change, the original backend error is re-raised.

This distinction matters.

A database outage must not be disguised as ordinary concurrency.

## Retry bound

CAS retries are bounded.

The default chain does not spin forever.

If contention exceeds the retry budget, EvidenceConflict is raised.

Operational response should reduce contention or use a backend with stronger append primitives.

Do not bypass the chain because retries were exhausted.

## Integrity verification

Verification starts at the current head.

It walks backwards through previous hashes.

It rejects:

missing nodes.

invalid node types.

digest mismatch.

cycles.

non-contiguous sequences.

premature genesis.

head length mismatch.

Verification then reconstructs forward order.

## Genesis

The empty chain root is sixty-four zero characters.

Sequence zero must use genesis.

A non-empty head may not use genesis.

This gives the empty state an explicit identity.

## Backend expectations

EvidenceStateBackend needs:

get.

put_if_absent.

compare_and_swap.

The in-memory fenced store satisfies this contract for tests and single-process reference semantics.

Production should use strongly consistent durable storage.

## Database implementation

A relational implementation can use two tables.

One table stores immutable evidence nodes.

One table stores the namespace head.

Node insert should use a unique node-hash key.

Head update should use:

WHERE revision = expected_revision.

Exactly one row should update.

Zero rows means a race or conflict.

## Transaction boundaries

Node insertion and head CAS do not have to be one transaction for correctness.

A node can safely exist without being reachable.

However a transaction can reduce garbage.

Do not make correctness depend on garbage cleanup.

## Evidence garbage

CAS losers may create unreachable nodes.

They are safe.

They can be removed by a conservative garbage collector.

A collector must never delete a node reachable from any retained head.

For high-assurance retention, garbage collection can simply be disabled.

## Receipt durability

DistributedReceiptChain preserves the semantics of ReceiptChain.

The outer durable node has its own content hash.

The inner shell receipt chain retains the original ReceiptChain SHA-256 algorithm.

This gives compatibility with existing receipt roots.

## Receipt reconstruction

A durable receipt is reconstructed from stored metadata.

It includes:

receipt ID.

logical command.

correlation ID.

command fingerprint.

start and finish timestamps.

duration.

return code.

success.

timeout.

output-limit status.

stdout byte count.

stderr byte count.

attempt.

bounded metadata.

Raw stdout and stderr are not stored in the receipt chain.

## Receipt root

DistributedReceiptChain.root_hash returns the same logical receipt hash that the in-process ReceiptChain would produce for the same ordered receipts.

That property is tested.

It allows old provenance consumers to keep using receipt roots.

## Receipt outer-chain integrity

The generic outer evidence chain adds durable storage integrity.

The reconstructed inner receipt chain adds execution evidence integrity.

Both must verify.

A valid outer chain with malformed receipt payload is not accepted.

## Journal durability

DistributedAIDecisionJournal persists AI decision events.

It stores wall-clock timestamps because another host may read the events later.

The original AIDecisionJournal hash algorithm is preserved.

The outer evidence chain separately protects durable storage linkage.

## Journal event contents

Decision events contain summaries and bounded metadata.

They do not store hidden chain of thought.

They should not store raw child output.

They should not store resolved secrets.

They should not store full unrestricted prompts.

## Global journal

The decision journal can contain events from many sessions.

Its global root proves the ordered aggregate history.

That global root may legitimately change because another session is active.

Therefore global-root equality is not enough for per-session recovery.

## Session journal evidence

SessionJournalEvidence filters the shared decision journal by session ID.

It commits:

global sequence of each relevant event.

event hash.

event kind.

proposal ID.

The resulting digest is session scoped.

## Why global sequence remains

A session commitment retains each event's global sequence.

This proves where the session events appeared in the shared chain.

It also preserves order.

The session digest does not pretend that events formed an independent journal.

## Unrelated journal traffic

Another session can append events.

The global journal root changes.

The interrupted session's SessionJournalEvidence digest remains unchanged.

Strict recovery can therefore tolerate unrelated journal traffic.

## Same-session journal drift

If a new event appears for the interrupted session, its session-journal digest changes.

Strict recovery treats that as material evidence drift.

This can require manual review.

## Session execution evidence

SessionExecutionEvidence commits only the execution report for one AI session.

It contains one SessionReceiptEvidence per plan step.

Each step can record:

step ID.

correlation ID.

receipt IDs.

receipt fingerprints.

return codes.

attempt count.

step success.

## Skipped or non-dispatched steps

A step with no dispatch is represented explicitly.

It has zero attempts.

Its receipt vectors are empty.

Its state still contributes to the parent execution report.

This avoids conflating "no child ran" with missing evidence.

## Receipt vector consistency

Receipt ID count.

Fingerprint count.

Return-code count.

Attempt count.

All must agree.

Mismatched vectors are invalid evidence.

## Session evidence digest

The complete session evidence object is canonically serialized.

Its digest binds:

session ID.

plan ID.

plan fingerprint.

report success.

all step evidence.

## Session evidence store

SessionEvidenceStore keeps the latest commitment for each AI session.

It is CAS based.

First write is revision one.

An identical write is idempotent.

Changed evidence advances revision.

A stale expected revision fails.

## Backend outage behavior

If the backend throws during CAS and its revision did not change, the original backend exception propagates.

A storage outage is not relabeled as a session evidence conflict.

If another writer actually advanced the record, SessionEvidenceConflict is raised.

## Global receipt chain

Shell receipts can be global across many sessions.

Another task may append receipts while an AI session is interrupted.

Therefore a changed global receipt root does not automatically mean the AI session executed additional work.

## Receipt-chain integrity versus equality

Strict recovery checks global receipt-chain integrity.

It does not require the global root to remain frozen when session-scoped evidence is available.

This distinction prevents false recovery alarms under concurrent workloads.

## Version-one checkpoint

AISessionCheckpoint remains the compact session state checkpoint.

It binds:

session identity.

phase.

intent identity and fingerprint.

proposal identity and fingerprint.

transition count.

global journal root.

global receipt root.

policy fingerprint.

tool catalog digest.

effect digest.

## Version-two recovery checkpoint

AIRecoveryCheckpoint wraps the version-one checkpoint.

It adds:

session execution evidence digest.

session journal evidence digest.

release evidence digest.

sandbox binding digest.

This is the preferred restart artifact for high-assurance deployments.

## Release binding

The recovery checkpoint can bind the signed release evidence active during execution.

If the worker restarts under a different release, strict recovery can require replanning.

This prevents a session from quietly continuing under a new model/tool/policy release.

## Sandbox binding

A recovery checkpoint can bind the sandbox contract and backend capability digest through SandboxBinding.digest.

If that binding changes after restart, strict recovery requires replanning.

A weaker sandbox may not inherit the authority of a previously reviewed plan.

## Strict recovery

StrictAIRecoveryManager evaluates:

global journal integrity.

session journal commitment.

global receipt-chain integrity.

session execution commitment.

policy fingerprint.

tool catalog digest.

effect digest.

release evidence digest.

sandbox binding digest.

It then chooses an explicit recovery action.

## Recovery actions

NONE means no recovery action is required.

RESUME_REVIEW means deterministic review can continue.

REQUIRE_REPLAN means the plan authority surface changed.

REQUIRE_VERIFICATION means execution may have occurred and evidence must be checked.

MARK_FAILED means the checkpoint was already in a failed or denied terminal path.

MANUAL_REVIEW means evidence integrity or session history is ambiguous.

## Journal corruption

If journal verification fails, automatic recovery stops.

The action becomes MANUAL_REVIEW.

Do not rewrite hashes.

Do not discard the corrupted chain.

Preserve it for incident analysis.

## Global journal advancement

If the global root changes because another session appended events, strict recovery can still resume when the session-journal commitment matches.

The report exposes both facts:

journal_root_matches can be false.

session_journal_matches can be true.

This is intentional.

## Session journal mismatch

A mismatch in the interrupted session's own journal commitment is stronger evidence.

Manual review is required.

The system should determine which new event appeared and why.

## Receipt corruption

If the durable receipt chain fails verification, strict recovery requires manual review.

The child process history is no longer trustworthy enough for automatic continuation.

## Session evidence missing during execution

If an executing or verifying checkpoint expects a session evidence digest but the store has no matching value, recovery requires verification.

Do not simply rerun the plan.

The child may have executed before the evidence write failed.

## Policy drift

A changed AI policy requires replanning.

This remains true even if the old plan was signed.

A signature proves what was reviewed.

It does not force current policy to accept old authority.

## Tool-catalog drift

A changed model-visible catalog requires replanning.

Tool meaning may have changed.

## Effect drift

A changed effect registry requires replanning.

Risk classification may have changed.

## Release drift

A changed signed release evidence digest requires replanning.

This captures more than policy.

It can bind code, tool, effect, model, eval, and workspace evidence.

## Sandbox drift

A changed sandbox binding requires replanning.

The original review may have depended on a stronger isolation backend.

## Final evidence commit

AIExecutionEvidenceFinalizer closes the execution evidence loop.

It runs after an execution attempt reaches COMPLETE or FAILED.

It does not execute another command.

It does not call a model.

## Finalizer inputs

The finalizer receives:

AIShellSession.

AIExecutionBundle.

policy fingerprint.

tool catalog digest.

effect digest.

optional release evidence digest.

optional sandbox binding digest.

It also owns references to:

decision journal.

receipt chain.

session evidence store.

audit-anchor store.

## Stable proposal identity

The finalizer does not require Python object identity.

It matches proposal ID and proposal fingerprint.

This makes finalization compatible with reconstructed objects after serialization.

## Provenance checks

Before committing evidence, the finalizer checks that execution provenance matches:

session intent fingerprint.

session proposal fingerprint.

policy fingerprint.

tool catalog digest.

effect digest.

optional release evidence digest.

optional sandbox binding digest.

A mismatch is an error.

## Pre-finalization integrity

The finalizer verifies:

decision journal.

receipt chain.

No final anchor is written when those chains are already corrupt.

## Session commitment

The finalizer rebuilds SessionExecutionEvidence from the actual PlanExecutionReport.

It writes or confirms that commitment in SessionEvidenceStore.

## Session journal commitment

The finalizer computes SessionJournalEvidence from the current durable or in-process journal.

That digest becomes part of the recovery checkpoint.

## Recovery artifact

The finalizer captures a fresh AISessionCheckpoint.

It wraps it in AIRecoveryCheckpoint schema version two.

The recovery checkpoint binds session execution and journal commitments.

## Signed audit anchor

The finalizer appends an AIAuditAnchor.

The anchor binds:

recovery checkpoint digest.

execution provenance digest.

global journal root.

global receipt root.

session execution digest.

release evidence digest.

sandbox binding digest.

The anchor is signed.

The signed anchor is then appended to a durable content-addressed chain.

## Audit-anchor integrity

AIAuditAnchorStore verifies:

outer evidence chain.

anchor reconstruction.

artifact type.

signed artifact digest.

HMAC signature.

A modified anchor or signature fails verification.

## Audit key

ArtifactSigner uses an HMAC key.

The key should live in a secret manager or trusted service process.

Never provide the key to:

the model.

the child process.

the MCP client.

the review UI.

the workspace.

## Independent verification

HMAC assumes shared-key trust.

If evidence must be independently verifiable outside the service boundary, sign exported anchor digests using a public-key or hardware-backed signing service.

The current HMAC layer remains useful for internal tamper evidence.

## Restart flow

On clean shutdown:

finalize completed sessions.

write recovery checkpoints for active sessions.

verify durable journal.

verify durable receipts.

record active release evidence.

record sandbox binding when relevant.

On startup:

load signed release channel.

verify release.

load checkpoint.

verify journal.

verify receipt chain.

load session execution evidence.

compute session journal evidence.

run StrictAIRecoveryManager.

follow its action.

## Interrupted planning

NEW or PLANNING checkpoints require replanning.

No execution evidence should exist.

If execution evidence unexpectedly exists, manual review is appropriate.

## Interrupted review

A REVIEW checkpoint can resume review when:

journal integrity is valid.

session journal matches.

control-plane digests match.

release matches.

sandbox binding matches if present.

No conflicting session execution evidence exists.

## Interrupted execution

EXECUTING and VERIFYING require caution.

Never assume failure means nothing happened.

Inspect session execution evidence.

Inspect receipt IDs and correlations.

Inspect workspace/external state.

Use verification before deciding whether another execution is safe.

## Completed session

A COMPLETE session should normally need no resumed execution.

The final evidence anchor should be present.

If the anchor is missing, the execution can be finalized from trustworthy evidence without re-running the plan.

## Failed session

A FAILED session remains failed.

Evidence finalization can still occur.

Failure evidence is valuable.

Do not hide it by creating a new session under the same ID.

## Exactly-once claim

The system does not promise exactly-once external side effects.

It provides:

single-use authority.

global replay barriers.

fenced coordination.

durable receipts.

session-scoped evidence.

explicit verification.

signed final anchors.

Those mechanisms make duplicate execution less likely and ambiguity more detectable.

## Evidence retention

Retention policy should distinguish:

durable chain nodes.

session checkpoints.

session evidence.

audit anchors.

raw outputs.

Raw child output should generally have shorter retention than integrity metadata.

## Evidence deletion

Deleting a reachable content-addressed node breaks chain verification.

If legal retention requires deletion, use a designed redaction/tombstone protocol rather than silently deleting a reachable node.

The current chain assumes retained reachable nodes remain available.

## Backup

Back up:

evidence nodes.

head records.

release registry.

release channels.

signing-key metadata.

session evidence.

checkpoints.

Backups should preserve transactional consistency enough to reconstruct heads.

## Restore

After restoring:

verify every retained chain.

verify signed release records.

verify active release channels.

verify audit anchors.

Do not begin autonomous execution until restoration integrity checks pass.

## Multi-region caution

A globally distributed eventually consistent store is not enough for CAS authority.

The evidence head and replay barriers require strong ordering.

Use a single strong coordinator or a database offering the necessary consistency semantics.

## Monitoring

Track:

evidence append failures.

CAS retry exhaustion.

unreachable node growth.

chain verification failures.

session evidence conflicts.

journal session mismatch.

recovery action counts.

audit-anchor signing failures.

audit-anchor verification failures.

finalizer failures.

## Alerts

Critical alert examples:

global receipt chain invalid.

decision journal invalid.

audit anchor signature invalid.

active release signature invalid.

execution evidence missing for a supposedly completed high-risk plan.

seal consumed with no corresponding execution or recovery record.

## Operational principle

Durable evidence is not a performance optimization.

It is part of the authority story.

If evidence required by policy cannot be durably committed, high-assurance automation should become less available rather than less accountable.
