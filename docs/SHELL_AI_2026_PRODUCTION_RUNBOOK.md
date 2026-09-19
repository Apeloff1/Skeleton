# Shell AI 2026 Production Runbook

## Scope

This runbook describes how to operate the AI-facing shell control plane in production.

It assumes the ordinary shell boundary is already configured.

The ordinary shell boundary remains authoritative.

The model never receives direct operating-system authority.

The model proposes logical actions.

Deterministic control layers decide whether those actions can proceed.

This runbook focuses on the production path from model identity through final signed evidence.

## Production objective

A production execution should be explainable as one immutable chain.

The chain begins with a known model and release.

It continues through a known intent and reviewed proposal.

It binds policy, tools, effects, source state, approval, quorum, sandbox, and release identity.

It ends with receipts, session evidence, audit anchors, and signed execution evidence.

Any missing mandatory link should stop the execution.

## Control-plane ordering

Use the following ordering for production work.

Resolve active release channel.

Verify signed release evidence.

Verify model/provider admission.

Create the user or system intent.

Collect bounded model proposals.

Apply provider-diverse consensus where configured.

Run deterministic proposal critique.

Compile one immutable execution plan.

Capture source or external preconditions.

Obtain ordinary human approval when policy requires it.

Obtain dual-control quorum when production assurance requires it.

Compile isolation and resource contracts.

Verify sandbox backend capabilities.

Create the exact assurance binding.

Issue the short-lived execution seal.

Recheck live release identity.

Recheck plan staleness.

Recheck preconditions.

Recheck quorum evidence.

Consume the single-use seal.

Consume the single-use quorum.

Consume ordinary approval when required.

Execute the immutable plan.

Verify execution result.

Persist session-scoped evidence.

Finalize recovery checkpoint.

Append signed audit anchor.

Append signed top-level execution evidence.

## Why ordering matters

Authority should only narrow as execution approaches.

A later stage must not widen a decision made earlier.

A model result is not approval.

Consensus is not approval.

An approval is not a shell capability.

A seal is not a sandbox.

A sandbox is not permission to run an unreviewed plan.

A receipt is evidence, not authority.

## Release identity

Production workers should serve a declared release channel.

Typical channels are canary, staging, and production.

Each channel points to one active signed release record.

The record pins the release evidence digest and registry signature.

Workers must not infer a release from local files alone.

## Release verification at startup

Configure AIStartupReleaseGuard.

Configure RuntimeReleaseExpectation.

Pass both into AIShellService.

The expectation should include the exact code revision.

It should include the exact AI policy fingerprint.

It should include the exact tool catalog digest.

It should include the exact effect registry digest.

Where available, include provider attestation digest.

Where available, include workspace manifest digest.

The service should not become READY when the expectation differs from the signed channel.

## Live release verification

Startup validation is not enough.

A channel can move after a worker becomes READY.

AIShellService rechecks release identity before authority transitions.

The recheck protects against stale workers serving after rollout.

If a release mismatch appears, stop new work.

Do not rewrite the expectation to make the worker pass.

Replace or restart the worker on the intended release.

## Release signing key

Treat ArtifactSigner keys as production signing secrets.

Do not expose them to model requests.

Do not expose them to shell children.

Do not embed them in source code.

Do not place them in model-visible context.

Use a secret manager.

Assign explicit key IDs.

Rotate keys deliberately.

Retain verification capability for evidence that must remain verifiable.

## Release safety case

A deployable release should have a passing safety case.

The safety case should include diagnostics.

It should include evaluation results.

It should include red-team results.

It should include provider attestation.

It should include regression comparison where available.

A blocked safety case must not activate.

A review-state safety case should not silently become production.

## Model registry

Register every production model/provider identity.

Registry identity is provider ID plus model ID.

Model version should be explicit.

Adapter version should be explicit.

Capabilities should be explicit.

Supported protocol versions should be explicit.

The expected model-visible tool catalog digest should be explicit.

## Model admission

Use AIModelAdmission before production ensemble planning.

Admission confirms that the identity is registered.

Admission confirms that the record is active.

Admission can require an exact model version.

Admission can require an exact adapter version.

Admission can pin the provider attestation digest.

Admission verifies structured-output support.

Admission verifies tool-use support.

Admission can require critique support.

Admission can require parallel-candidate support.

Admission can require protocol compatibility.

Admission can require minimum input capacity.

Admission can require minimum output capacity.

Admission verifies the exact tool catalog digest.

## Model admission failure

An unknown model should not plan production shell work.

An inactive model should not plan production shell work.

A model version mismatch should stop the request.

An adapter version mismatch should stop the request.

A capability regression should stop the request.

A tool catalog mismatch should stop the request.

Do not downgrade admission requirements automatically.

## Admitted ensemble

AdmittedEnsembleAIPlanner requires admission for every configured member.

Admission occurs before ensemble calls.

This prevents an unregistered model from contributing to production consensus.

All ensemble members must have matching trusted requirements.

The configured requirements must exactly match the ensemble member set.

## Ensemble compatibility

Every production ensemble member should expose the same tool catalog.

Every production ensemble member should use the same AI policy fingerprint.

A mismatch should fail construction.

Fallback must never mean broader authority.

Provider diversity changes who proposes.

It does not change what may execute.

## Ensemble provider identity

Provider identity comes from trusted configuration.

Do not trust a provider name emitted in model text.

Do not infer independence from model names.

Two aliases served by one provider are not provider-diverse.

Use explicit provider IDs.

## Unique model voting

One model identity receives at most one vote for a proposal shape.

Multiple proposal IDs from the same model do not create extra votes.

This prevents self-generated consensus inflation.

## Provider diversity threshold

High-assurance planning should require multiple provider identities where practical.

A provider outage may reduce availability.

Do not lower the diversity threshold automatically during an incident.

Explicitly move to a degraded policy only through reviewed operations.

## Candidate selection

Consensus identifies an eligible shape.

CandidateSelector still runs deterministic critique.

Only deterministically executable candidates should be selected.

A high-confidence but policy-denied candidate remains denied.

A model critic cannot override deterministic rejection.

## Planning budget

Bound model calls.

Bound action counts.

Bound context bytes.

Bound tool cards.

Bound replanning rounds.

Bound candidate counts.

An outage or ambiguous request must not create unlimited model fan-out.

## Context provenance

Every model-visible context item should have a provenance label.

Record context kind.

Record trust level.

Record sensitivity.

Record source identity.

Record content digest.

Secrets should not enter model payloads.

Confidential context should require explicit policy.

Untrusted repository text should remain labeled untrusted.

## Prompt-injection treatment

Treat repository text as data.

Treat issue text as data.

Treat logs as data.

Treat downloaded documents as data.

Treat command output as data.

A statement inside data does not grant shell authority.

Do not turn an untrusted instruction into a system-level action.

## Source preconditions

For code-changing or high-risk work, bind reviewed source state.

Use SourceDigestProvider for bounded file hashing.

Use Preconditions for exact resource digests.

Use PreconditionChecker immediately before seal consumption.

A required mismatch stops execution.

## Source root

Pin a trusted absolute source root.

Resource IDs should be relative.

Reject absolute resource IDs.

Reject parent traversal.

Reject resolution outside the root.

Deny symlinks by default.

If symlinks are allowed, resolved targets must remain inside the root.

## Hashing limits

Set a per-file byte limit.

Set a manifest-entry limit.

Set a total manifest-byte limit.

Digest computation is part of the security boundary.

It must not become an unbounded I/O operation.

## Workspace manifest

Use WorkspaceManifest when the reviewed operation depends on multiple files.

The manifest should be deterministic.

Duplicate paths should fail.

Record file digest.

Record file size.

Record mode when useful.

Compare manifests before high-impact execution.

## Precondition race residual

A precondition is a point-in-time verification.

A file may change after hashing.

For stronger guarantees, execute from an immutable snapshot.

Use a pinned VCS worktree.

Use a copy-on-write sandbox.

Use a read-only source mount.

Use content-addressed inputs where possible.

## Ordinary approval

AIPlanApproval binds one principal.

It binds one intent fingerprint.

It binds one proposal fingerprint.

It has a TTL.

It is single-use.

It is not a generic permission token.

## Dual-control quorum

High-risk production assurance should use AIApprovalQuorumStore.

The default quorum requires two distinct approvals.

The principal is not allowed to approve its own execution by default.

Approver roles may be restricted.

Votes are stored in a strongly consistent versioned backend.

## Quorum binding

A quorum binds the principal.

It binds the intent fingerprint.

It binds the proposal fingerprint.

It binds every vote.

It binds vote role.

It binds vote decision.

It binds vote reason.

It binds metadata.

It binds creation and expiry.

Its digest changes whenever the authority evidence changes.

## Approval votes

Approval votes must come from authenticated reviewer identities.

Do not use user-supplied display names as reviewer identity.

Use the identity established by the review system.

Record a role when role policy is enabled.

## Reject votes

A reject vote vetoes the quorum.

A rejected quorum is terminal.

Do not allow later approval votes to erase the rejection.

Do not allow the same approver to change a vote decision.

A new review requires a new quorum object.

## Approval metadata

Use bounded metadata for change-management references.

Examples include change ticket IDs.

Examples include incident IDs.

Examples include deployment request IDs.

Do not store secrets in approval metadata.

Metadata is included in the quorum digest.

## Quorum TTL

Use a short TTL.

High-risk authority should expire quickly.

Long-lived approval increases review-to-execution drift.

If the quorum expires, review again.

Do not extend an expired quorum in place.

## Quorum stale evidence

The service requires the exact current quorum digest.

If another vote is added after sealing, the previous quorum evidence becomes stale.

The old seal cannot be used with the new quorum.

Issue a new seal after revalidation.

## Quorum consumption

Quorum is single-use.

Consumption uses compare-and-swap.

A concurrent change blocks consumption.

Once consumed, it must not be reused.

There is no automatic unconsume operation.

## Quorum backend

Use a strongly consistent backend.

CAS must be atomic.

Do not emulate CAS with separate read and write calls.

Do not use eventually consistent storage for approval authority.

A quorum backend outage should stop high-risk execution.

## Assurance policy

AIExecutionAssurancePolicy controls risk-adaptive requirements.

The compatibility-safe default keeps low risk STANDARD.

The default requires SEALED for medium risk.

The default requires SANDBOXED for high risk.

The default denies critical risk.

## Production assurance profile

AIExecutionAssurancePolicy.production adds stricter evidence requirements.

Medium risk requires verified release evidence.

High risk requires verified release evidence.

High risk requires verified preconditions.

High risk requires human approval.

High risk requires dual-control quorum.

High risk still requires sealed execution.

High risk still requires a verified sandbox.

Critical risk remains denied.

## Assurance policy digest

Treat the assurance policy as part of authority configuration.

Its deterministic digest should change when requirements change.

Record the digest with assurance binding.

Changing assurance policy invalidates previous binding identity.

## Assurance binding

AssuranceBinding should bind every authority surface used for the final decision.

Bind risk band.

Bind assurance policy digest.

Bind plan fingerprint.

Bind release evidence digest.

Bind preconditions digest.

Bind ordinary approval ID.

Bind quorum digest.

Bind execution backend ID.

Bind sandbox binding digest.

The binding digest becomes a concise identity for the final assurance surface.

## Execution seal

The execution seal is the final short-lived authority token.

It is HMAC signed.

It binds principal.

It binds session.

It binds PlanPin.

It binds preconditions digest.

It binds ordinary approval ID.

It binds release evidence digest.

It binds assurance or quorum digest.

It binds issue time.

It binds expiry.

It binds a nonce.

## Seal TTL

Keep seal TTL short.

Tens of seconds are preferable to long windows.

Seal TTL has an authority maximum.

The verifier rejects seals whose encoded lifetime exceeds the configured maximum.

## Seal clock behavior

Execution seals use wall-clock time for cross-host portability.

Configure acceptable clock skew.

Monitor time synchronization on execution workers.

A seal issued too far in the future should fail verification.

## Seal issuance

Before issuing a seal, recheck PlanPin.

Recheck ordinary approval when required.

Recheck quorum when supplied.

Bind current release evidence.

Bind current preconditions.

Do not execute during seal issuance.

## Seal consumption

Recheck live release before consumption.

Recheck plan staleness before consumption.

Recheck preconditions before consumption.

Recheck quorum before consumption.

Check assurance before consumption.

Then verify and consume the seal.

Only after that consume the quorum.

Only after those controls pass should the plan enter execution.

## Why stale-plan check precedes consumption

A stale plan has already lost authority.

Burning a valid seal on an already stale plan creates avoidable operational failure.

The service rechecks staleness before seal consumption.

The caller can then replan and reseal.

## Seal replay

Local ExecutionSealRegistry prevents reuse within one process.

DistributedExecutionSealRegistry prevents reuse across workers.

Production multi-worker execution should use the distributed replay barrier.

The first consumer wins.

Every later consumer fails.

## Seal backend outage

When global replay prevention is required, backend outage means execution should stop.

Do not fall back to local replay state silently.

Doing so would widen authority under failure.

## Seal and quorum failure ordering

A seal may be consumed and then a quorum consumption race may fail.

This is safe from a duplicate-side-effect perspective.

The child has not started.

The old seal remains consumed.

Resolve the quorum state.

Review again if necessary.

Issue a fresh seal.

## Sandbox requirement

High-risk production work should run through VerifiedSandboxExecutionBackend.

The backend is bound to one plan fingerprint.

It is bound to one sandbox contract digest.

It is bound to one capability digest.

A different plan cannot use the binding.

## Isolation compiler

AIIsolationCompiler derives minimum isolation from effect contracts and risk.

Read-only AI work remains at least workspace isolated.

Mutable work remains workspace isolated or stronger.

High-risk effects require SANDBOXED.

High-risk risk bands require SANDBOXED.

## Write-root policy

Configure explicit allowed write roots.

A requested write root must be inside a configured root.

No configured roots means no requested writes.

An empty allowlist is not wildcard access.

## Network policy

Network is disabled unless the effect contract declares network.

Network is disabled unless the intent allows network.

Both conditions must pass.

The model cannot grant itself network.

## Home visibility

Hide the ambient user home.

Provide explicit isolated configuration to tools that require home-like state.

Do not expose developer credentials through ambient home directories.

## Temporary directory

Use private temporary storage.

Do not share an uncontrolled global temp namespace across AI tasks.

Clean temporary data on sandbox teardown.

## Clean environment

Start from a minimal explicit environment.

Do not inherit arbitrary shell startup variables.

Do not inherit dynamic-loader variables unless explicitly required.

Do not inherit credential variables by default.

## Resource ceilings

Enforce wall time.

Enforce CPU time.

Enforce memory.

Enforce process count.

Enforce file bytes.

Enforce open files.

Enforce output bytes.

A declarative resource profile is not enforcement by itself.

The sandbox backend must attest that it enforces the profile.

## No-new-privileges

High-risk execution should require no-new-privileges or an equivalent backend control.

Do not claim this property based on application convention.

Verify backend capability.

## Syscall filtering

High-risk execution can require syscall filtering.

The backend must attest support.

A missing required syscall filter blocks sandbox compatibility.

## Network namespace

No-network work should receive network namespace isolation or a backend equivalent.

Environment flags are not a substitute.

## Process lifecycle

The backend must own child lifecycle.

Use process groups, containers, cgroups, or stronger isolation.

Ensure timeout termination covers descendants.

Do not leave detached child processes running after task failure.

## Sandbox capability drift

Capabilities are rechecked immediately before execution.

The capability digest must still match the binding.

The contract digest must still match.

The plan fingerprint must still match.

Any mismatch stops execution.

## Verification

Execution success alone is insufficient.

Run PlanVerifier.

Evaluate explicit verification criteria.

Record verification state.

Treat failed verification as failed AI execution even if every child returned zero.

## Output handling

Treat child output as untrusted data.

Do not feed raw output back into authority logic.

Apply output policies.

Classify secret-bearing output.

Limit retained bytes.

Prefer digest and metadata retention for sensitive content.

## Session evidence

SessionExecutionEvidence commits the receipts produced by one AI session.

It avoids using a global receipt root as the only recovery signal.

This matters in multi-session services.

Unrelated sessions may legitimately advance the global receipt chain.

## Session journal

SessionJournalEvidence commits decision-journal events for one AI session.

It separates same-session drift from unrelated global journal traffic.

Recovery can tolerate unrelated session events while detecting changes to the interrupted session.

## Recovery checkpoint

Use AIRecoveryCheckpoint version two.

Bind the base session checkpoint.

Bind session evidence digest.

Bind session journal digest.

Bind release evidence digest.

Bind sandbox binding digest.

This record describes the authority/evidence state expected at recovery.

## Strict recovery

Use StrictAIRecoveryManager for high-assurance recovery.

Verify journal integrity.

Verify session journal commitment.

Verify receipt chain integrity.

Verify session execution evidence.

Verify release evidence identity.

Verify sandbox binding identity.

Verify AI policy.

Verify tool catalog.

Verify effect registry.

Do not replay a child merely because the session was interrupted.

## Review-phase recovery

A review-phase session may resume only when the relevant evidence still matches.

If policy changed, replan.

If tools changed, replan.

If effects changed, replan.

If release changed, replan.

If same-session journal changed unexpectedly, require manual review.

## Execution-phase recovery

An interrupted executing or verifying session requires verification.

Do not assume the child did not run.

Inspect session-scoped receipts.

Inspect durable side-effect evidence.

Inspect external idempotency status.

Only then decide whether compensation, verification, or a fresh plan is appropriate.

## Global receipt advancement

Another session may append receipts while one session is interrupted.

That does not automatically mean the interrupted session changed.

Use session-scoped evidence.

The global chain remains important for integrity.

It is not the sole per-session recovery discriminator.

## Audit anchor

AIAuditAnchor binds recovery checkpoint identity.

It binds execution provenance.

It binds global journal root.

It binds global receipt root.

It binds session evidence.

It binds release evidence.

It binds sandbox binding.

It is signed and appended to a durable content-addressed chain.

## Audit anchor verification

Verify the outer evidence chain.

Verify the anchor digest.

Verify artifact type.

Verify signature digest.

Verify signing key identity.

A failure should be treated as evidence corruption.

## Final execution evidence

AIExecutionEvidence creates the top-level execution record.

It binds session identity.

It binds intent fingerprint.

It binds proposal fingerprint.

It binds provenance digest.

It binds recovery checkpoint digest.

It binds session execution evidence.

It binds session journal evidence.

It binds audit anchor digest.

It binds audit anchor chain node.

It can bind release evidence.

It can bind sandbox binding.

It can bind model attestation.

It can bind execution seal ID.

It can bind quorum digest.

## Final evidence signing

AIExecutionEvidenceStore signs the final evidence digest.

It appends the record to a durable content-addressed chain.

Signature metadata binds session ID.

Signature metadata binds execution seal ID.

Verification rechecks both metadata bindings.

## Evidence finalizer

AIExecutionEvidenceFinalizer is the normal completion path.

It does not execute commands.

It does not call a model.

It consumes evidence from an already completed or failed attempt.

It verifies journal integrity.

It verifies receipt integrity.

It persists session evidence.

It builds session journal evidence.

It captures checkpoint.

It builds recovery checkpoint.

It appends audit anchor.

When configured, it appends final signed execution evidence.

## Finalizer mismatch behavior

A foreign proposal fails.

A foreign intent fails.

A policy mismatch fails.

A tool catalog mismatch fails.

An effect registry mismatch fails.

A release evidence mismatch fails.

A sandbox binding mismatch fails.

A corrupt journal fails.

A corrupt receipt chain fails.

Do not generate a clean-looking final record from inconsistent inputs.

## Evidence storage

Use durable strongly consistent storage.

Immutable content-addressed nodes are preferred.

Use CAS for chain heads.

A writer that loses a CAS race may leave an unreachable immutable node.

It must not corrupt the committed chain.

## Evidence retention

Choose retention based on risk and compliance needs.

Retain digests longer than sensitive output bytes.

Preserve signing-key verification for retained signed evidence.

Do not delete a key required to verify evidence still inside retention.

## Evidence export

Exports should include stable digests.

Exports should omit signing secrets.

Exports should avoid raw sensitive stdout and stderr unless explicitly required.

Use evidence IDs to join records.

Do not expose hidden model reasoning.

## MCP exposure

Remote MCP tool calls must pass protocol parsing.

They must pass tool lookup.

They must pass authorization.

They must pass argument validation.

They must pass replay admission.

Only then may they become AIAction values.

## MCP principal

Principal identity comes from transport authentication.

MCPRequestEnvelope does not authenticate the principal by itself.

Do not accept a principal field in model text as identity.

Pass the authenticated principal into MCPAIShellGateway.

## MCP tool discovery

Use principal-filtered discovery.

A principal should see only authorized tool descriptors.

The discovery digest is principal-bound.

Do not treat a cached tool list from one principal as authority for another.

## MCP routing headers

Validate routing header count.

Validate header name size.

Validate header value size.

Require expected routing headers.

Require header/body method equality.

Require header/body tool-name equality.

Header validation does not replace authentication.

## MCP replay barrier

Use MCPReplayGuard for side-effecting production tool calls.

The guard binds authenticated principal.

It binds request ID.

It binds canonical request bytes.

Admission is atomic put-if-absent.

An identical second request is still a replay.

Reject it.

## MCP replay timing

Replay admission occurs after request validation and authorization.

Malformed requests do not consume a legitimate replay slot.

Unauthorized requests do not consume a legitimate replay slot.

Once the validated request is admitted, a retry requires a new request ID after the operator understands the prior outcome.

## MCP replay TTL

Use a TTL long enough to cover likely transport retries.

Do not use an unbounded replay record.

After expiry, the request ID may be reused under policy.

For high-impact operations, prefer unique request IDs that are never intentionally reused.

## MCP replay backend outage

If replay protection is part of the production authority path, backend outage should stop the call.

Do not silently bypass replay protection.

## Distributed state

Policy state uses CAS.

Session checkpoints use CAS.

Review claims use fencing.

Seal replay uses put-if-absent.

Quorum approval uses CAS.

Release channels use CAS.

Evidence chain heads use CAS.

These are security primitives, not performance optimizations.

## Consistency requirement

Use a strongly consistent backend for authority records.

Eventually consistent storage is unsafe for single-use controls.

Do not use asynchronous replication lag as the source of truth for quorum or seal consumption.

## Lease fencing

Lease expiry alone is insufficient.

Use monotonically increasing fencing tokens.

A stale worker must be unable to write after another worker acquires ownership.

This applies to review ownership and other leased coordination.

## Backend time

For distributed TTL and leases, prefer backend or server time when possible.

Do not rely on arbitrarily skewed worker clocks.

Execution seal verification still requires synchronized host clocks.

Monitor both.

## Model-provider outage

Health state may degrade.

Circuit breaker may open.

Rate limit may block calls.

The ensemble may continue only when configured success and diversity thresholds remain satisfied.

Do not lower execution assurance because planning availability is poor.

## Coordination backend outage

Classify the failed subsystem.

Policy backend outage can stop new high-risk work.

Release-channel outage can stop release verification.

Seal backend outage can stop sealed execution.

Quorum backend outage can stop high-risk execution.

Evidence backend outage should stop finalization and may require the service to drain.

Availability loss is preferable to ambiguous authority.

## Evidence backend outage after child completion

The child may already have produced side effects.

Do not retry the child just because final evidence persistence failed.

Preserve local receipts.

Open an incident.

Restore evidence backend.

Finalize or reconstruct evidence from trusted retained inputs.

If reconstruction cannot be proven, mark the attempt for manual review.

## Quorum backend outage after seal issue

Do not execute.

The quorum cannot be revalidated or consumed.

Let the seal expire or explicitly discard it.

Restore coordination.

Review current quorum state.

Issue a fresh seal.

## Seal backend outage after quorum completion

Do not execute if distributed replay is required.

A completed quorum is not enough.

Restore replay backend.

Issue a fresh seal if the original authority window is no longer trustworthy.

## Release channel move during review

The live release recheck will fail before later authority transitions.

Discard the stale review.

Start a new session on the current release.

Do not carry old approval across release identity.

## Policy change during review

PlanPin detects policy fingerprint change.

Stale guard fails.

Replan and review under new policy.

Do not override stale guard to preserve a model response.

## Tool catalog change during review

Stale guard detects the catalog digest change.

The model may have planned against a different surface.

Replan.

## Effect contract change during review

Risk semantics changed.

Stale guard detects effect digest change.

Replan.

Do not reinterpret the old proposal under new effect declarations.

## Source change during review

Precondition verification fails.

Re-read source.

Determine whether the change is expected.

Replan if the reviewed assumptions changed.

Do not simply update the expected digest without review.

## Quorum change after sealing

The quorum digest changes.

The seal binds the earlier digest.

Execution fails.

Revalidate the new quorum.

Issue a new seal.

## Sandbox deployment change after sealing

The sandbox capability digest changes.

VerifiedSandboxExecutionBackend detects drift.

Execution fails.

Re-attest the backend.

Issue a new binding and a fresh seal when appropriate.

## Approval expiry after sealing

Ordinary approval is revalidated.

An expired approval cannot be consumed.

Issue fresh approval and seal.

Do not extend the old approval object.

## Incident classification

Classify release mismatch as authority drift.

Classify stale plan as review drift.

Classify precondition mismatch as source drift.

Classify quorum failure as human-control failure.

Classify seal replay as authorization replay.

Classify sandbox drift as execution-boundary drift.

Classify evidence verification failure as audit-integrity failure.

## Incident evidence

Capture IDs and digests.

Capture release ID.

Capture release evidence digest.

Capture session ID.

Capture proposal fingerprint.

Capture PlanPin.

Capture approval ID.

Capture quorum digest.

Capture seal ID.

Capture sandbox binding digest.

Capture receipt root.

Capture session evidence digest.

Capture audit anchor digest.

Do not capture signing keys.

Do not capture secret context.

## Quarantine

Quarantine suspicious model identities.

Quarantine proposal fingerprints when appropriate.

Quarantine commands when a tool contract is suspect.

Quarantine sandbox backends operationally when attestation becomes unreliable.

Quarantine should reduce authority.

It should never create a fallback with more authority.

## Key rotation

Rotate release signing keys deliberately.

Rotate audit-anchor signing keys deliberately.

Rotate execution-evidence signing keys deliberately.

Rotate execution-seal HMAC keys deliberately.

Version keys with key IDs.

Plan overlap windows for verification.

Do not mix issuance keys invisibly.

## Seal key rotation

An execution seal is short lived.

A rotation can usually stop issuing with the old key and wait for its maximum TTL.

Then retire old seal verification.

If immediate revocation is required, reject all old-key seals and accept the availability impact.

## Evidence key rotation

Evidence lives much longer than seals.

Keep old verification keys for the evidence-retention period.

Consider external archival verification if evidence must outlive service key infrastructure.

## Review identity

Approver identity should be authenticated.

Reviewer roles should come from trusted identity configuration.

Do not accept role from an untrusted client without verification.

Log the authenticated identity used for each vote.

## Separation of duties

For high-risk production work, separate requester from approvers.

Separate model/operator from signing-key custodians.

Separate execution worker from release promotion where practical.

Separate audit verification from execution authority where practical.

## Self-approval

Production quorum defaults to forbid principal self-approval.

Keep that default unless governance explicitly permits otherwise.

If self-approval is allowed for a lower environment, do not carry that configuration into production accidentally.

## Two-person rule

A required vote count of two is the minimum dual-control pattern.

Some operations may require more.

Increase required_votes through reviewed policy.

Keep max_votes bounded.

Do not count duplicate identities.

## Rejection semantics

One explicit reject vote vetoes the quorum.

This prevents approval accumulation from overriding a security reviewer.

A rejected request should be investigated.

Open a new quorum only after the plan or context changes appropriately.

## Change management

Bind a change ticket ID in quorum metadata when required.

Bind deployment ID.

Bind incident ID for emergency work.

Do not rely on free-form comments as authority.

The metadata is evidence.

The fingerprints remain the authority binding.

## Emergency path

Do not implement emergency mode as “skip controls.”

Define a separate reviewed assurance policy.

Define explicit identities allowed to invoke it.

Require stronger audit.

Require shorter TTL.

Require incident ID.

Require post-event review.

Keep critical risk denied unless there is a separately designed system.

## Production boot checklist

Confirm code revision.

Confirm active release channel.

Confirm release signature.

Confirm safety case.

Confirm policy fingerprint.

Confirm tool catalog digest.

Confirm effect registry digest.

Confirm provider attestation.

Confirm workspace manifest when required.

Confirm signing-key access.

Confirm coordination backend health.

Confirm receipt/evidence backend health.

Confirm sandbox backend health.

Confirm system clock synchronization.

Confirm test and quality gates for deployed revision.

## Model onboarding checklist

Create provider identity.

Create model identity.

Record model version.

Record adapter version.

Record capabilities.

Record supported protocol versions.

Record tool catalog digest.

Run compatibility checks.

Run eval dataset.

Run red-team dataset.

Run regression comparison.

Build safety case.

Register model.

Build release evidence.

Canary before production.

## Tool onboarding checklist

Define logical command.

Pin executable path.

Define argument policy.

Define environment policy.

Define workspace policy.

Define effect contract.

Define reversibility.

Define human-approval recommendation.

Add model-visible tool card.

Regenerate tool catalog digest.

Run contract lint.

Run process-safety scanners.

Add adversarial tests.

Update release evidence.

## Sandbox onboarding checklist

Name backend ID.

Version backend.

Declare maximum isolation level.

Verify private temp.

Verify clean environment.

Verify read-only source support.

Verify network isolation.

Verify home hiding.

Verify process-group lifecycle.

Verify no-new-privileges.

Verify syscall filtering.

Verify resource enforcement.

Set maximum resource profile.

Run compatibility tests.

Record capability digest.

## Production request checklist

Authenticate principal.

Verify current release.

Verify model admission.

Build provenance-labeled context.

Plan within budget.

Reach required consensus.

Run deterministic critique.

Compile immutable plan.

Capture preconditions.

Obtain ordinary approval when required.

Obtain quorum when required.

Build sandbox contract.

Verify sandbox.

Build assurance binding.

Issue seal.

Recheck release.

Recheck stale plan.

Recheck preconditions.

Recheck quorum.

Consume seal.

Consume quorum.

Execute.

Verify.

Finalize evidence.

## Medium-risk checklist

Use production release verification.

Use sealed execution.

Use required ordinary approval from AI policy.

Use source preconditions when configured.

Use host backend only when assurance allows it.

Finalize signed evidence.

## High-risk checklist

Use production release verification.

Use sealed execution.

Use verified sandbox.

Use source preconditions.

Use ordinary human approval.

Use dual-control quorum.

Use exact sandbox binding.

Use short seal TTL.

Use distributed replay protection.

Finalize signed evidence.

Require successful evidence persistence before declaring workflow complete.

## Critical-risk checklist

Do not execute through the default AI shell production assurance policy.

Redesign the operation.

Use a separately governed process if the organization truly requires it.

Do not lower critical to high just to make a workflow pass.

## Completion checklist

Check execution report.

Check verifier result.

Check session terminal phase.

Check session evidence persisted.

Check session journal commitment.

Check recovery checkpoint.

Check audit anchor signature.

Check audit anchor chain.

Check final execution evidence signature.

Check final execution evidence chain.

Record evidence root in operational logs.

## Recovery checklist

Load session checkpoint.

Load recovery checkpoint.

Verify global journal.

Verify session journal.

Verify global receipt chain.

Verify session evidence.

Verify current release.

Verify policy.

Verify tools.

Verify effects.

Verify sandbox binding.

Determine recovery action.

Never rerun an uncertain side effect automatically.

## Audit checklist

Verify release signature.

Verify release evidence digest.

Verify model attestation digest.

Verify provenance digest.

Verify checkpoint digest.

Verify session evidence digest.

Verify session journal digest.

Verify audit anchor signature.

Verify audit chain root.

Verify final execution evidence signature.

Verify final evidence chain root.

Trace seal ID.

Trace quorum digest.

## CI checklist

Run compileall.

Run shell regression glob.

Run backend security regressions.

Run repository process-safety scanner.

Run workflow security scanner.

Run secret scanning.

Run artifact policy.

Run provenance policy.

Run frontier contracts.

Run architecture-specific validation where configured.

Do not declare release green from partial checks.

## Test strategy

Test success paths.

Test every stale binding.

Test every swapped identity.

Test every replay path.

Test expiry.

Test backend outage.

Test CAS races.

Test corrupted evidence.

Test wrong signing key.

Test wrong key ID.

Test release drift.

Test policy drift.

Test source drift.

Test quorum rejection.

Test sandbox drift.

Test model capability regression.

## Adversarial test: model swap

Register model A.

Build requirement for model A.

Replace current registry attestation with a new model version.

Keep old expected attestation digest.

Admission must fail.

Do not call the model after admission failure.

## Adversarial test: provider alias

Configure two model IDs under one provider.

Require two providers.

Both models agree.

Consensus must still fail provider diversity.

## Adversarial test: repeated model vote

One model emits multiple proposal IDs with the same shape.

Unique model vote count remains one.

Consensus threshold must not be satisfied by duplicates.

## Adversarial test: context injection

Place an instruction inside untrusted repository text.

Pass it as untrusted context.

The planner may read it as data.

It must not change tool authority.

Deterministic policy still controls execution.

## Adversarial test: release swap

Issue a seal under release A.

Move production channel to release B.

Attempt execution.

Live release verification should stop it.

Seal release digest also should not match B.

## Adversarial test: quorum swap

Complete quorum A.

Issue seal bound to quorum A digest.

Complete quorum B for the same proposal.

Attempt execution with quorum B and seal A.

Seal verification must fail.

Neither quorum should be consumed by the failed swap attempt.

## Adversarial test: late vote

Complete a quorum.

Issue a seal.

Add another vote when policy allows extra votes.

The quorum digest changes.

The old quorum evidence is stale.

Execution should fail before seal consumption when stale evidence is detected.

## Adversarial test: reject vote

Open a quorum.

Add an explicit reject vote.

Attempt to add approvals.

The quorum remains rejected.

A new quorum is required after corrective review.

## Adversarial test: replay

Admit an MCP request.

Repeat the exact same request.

The second call fails replay admission.

Changing only request content under the same live ID also fails.

## Adversarial test: principal scope

Use the same MCP request ID under two authenticated principals.

They occupy separate replay scopes.

Authorization still evaluates each principal independently.

## Adversarial test: source drift

Seal a plan with source preconditions.

Change a required resource digest.

Execution fails before seal consumption.

The child does not start.

## Adversarial test: stale policy

Review a plan.

Change policy fingerprint.

Attempt sealed execution.

Stale guard fails before one-use authority is consumed.

Replan under new policy.

## Adversarial test: sandbox swap

Bind a VerifiedSandboxExecutionBackend.

Change backend capability version.

Attempt execution.

Capability digest mismatch fails.

No unverified fallback should run.

## Adversarial test: audit tamper

Persist an audit anchor.

Modify anchor content or signature in storage.

Outer content-addressed chain or signature verification fails.

Treat the chain as corrupt.

## Adversarial test: final evidence tamper

Persist signed AIExecutionEvidence.

Modify proposal fingerprint.

Modify session metadata.

Modify seal metadata.

Verification fails.

Do not accept the record for recovery.

## Observability fields

Expose service phase.

Expose shell phase.

Expose release channel.

Expose release ID.

Expose release evidence digest.

Expose policy fingerprint.

Expose tool catalog digest.

Expose effect registry digest.

Expose model registry identity.

Expose model attestation digest.

Expose sandbox backend ID.

Expose sandbox binding digest.

Expose evidence-chain roots.

Avoid high-cardinality raw prompts.

Avoid secret values.

## Metrics for model admission

Count admitted models.

Count inactive-model denials.

Count unknown-model denials.

Count version mismatch.

Count adapter mismatch.

Count capability mismatch.

Count protocol mismatch.

Count tool digest mismatch.

## Metrics for quorum

Count opened quorums.

Count approve votes.

Count reject votes.

Count expired quorums.

Count completed quorums.

Count stale-evidence failures.

Count principal mismatch.

Count consumed quorums.

Count reuse attempts.

## Metrics for seals

Count issued seals.

Count expired seals.

Count replay failures.

Count principal mismatch.

Count session mismatch.

Count plan mismatch.

Count precondition mismatch.

Count release mismatch.

Count assurance mismatch.

## Metrics for sandbox

Count bindings.

Count compatibility failures.

Count capability drift.

Count plan mismatch.

Count contract mismatch.

Count resource-capability failure.

Count execution failure.

## Metrics for evidence

Count session-evidence writes.

Count session-journal commitments.

Count recovery checkpoints.

Count audit anchors.

Count final signed evidence records.

Count signature failures.

Count chain-integrity failures.

Count finalization failures.

## Alert thresholds

Alert immediately on signature verification failure.

Alert immediately on evidence-chain corruption.

Alert immediately on release mismatch in production.

Alert immediately on critical-risk execution attempt.

Alert immediately on seal replay for high-risk work.

Alert immediately on quorum reuse.

Alert immediately on sandbox capability drift during high-risk work.

## Capacity planning

Bound registry sizes.

Bound review queue sizes.

Bound approval counts.

Bound quorum votes.

Bound seal replay records.

Bound MCP replay records.

Bound journal events.

Bound receipt events.

Bound evidence records.

Capacity exhaustion should fail explicitly.

Do not evict live authority silently.

## Backpressure

When evidence storage approaches capacity, stop accepting high-risk work.

When approval storage approaches capacity, stop opening new approvals.

When model rate limits are exhausted, reduce planning availability.

Do not bypass controls to preserve throughput.

## Data minimization

Store digests instead of raw secret material.

Store environment key names, not values.

Store argument digests where raw arguments are sensitive.

Do not put stdout into final evidence by default.

Do not put model hidden reasoning into audit evidence.

## Privacy

Execution evidence can contain user and operational identifiers.

Apply access control.

Apply retention policy.

Avoid unnecessary free-form metadata.

Prefer opaque stable IDs.

## Human-readable review

AIReviewView should show the logical actions.

Show command name.

Show argv when safe.

Show cwd when safe.

Show environment references, not secret values.

Show risk.

Show effects.

Show whether approval is required.

Show whether the action is reversible.

## Human reviewer expectations

Reviewers should understand what is bound.

Approving after the proposal changes is not valid.

Approving one principal does not approve another.

Approving one release does not approve another release when release binding is required.

Review tools should display the proposal fingerprint.

## Quorum reviewer expectations

Each reviewer should make an independent decision.

Do not pre-populate a second reviewer decision from the first.

Display prior votes for transparency only if governance permits.

A reject reason should be retained as evidence.

## Production ownership

Assign an owner for AI policy.

Assign an owner for tool contracts.

Assign an owner for release signing.

Assign an owner for model registry.

Assign an owner for sandbox backends.

Assign an owner for evidence storage.

Assign an owner for incident response.

## Change review

Changes to denied effects require security review.

Changes to assurance bands require security review.

Changes to quorum requirements require governance review.

Changes to sandbox requirements require platform/security review.

Changes to release-signing keys require key-management review.

Changes to tool catalog require release evidence refresh.

## Compatibility

Default policy remains useful for development.

Production should opt into AIExecutionAssurancePolicy.production.

Do not silently turn strict production behavior on inside libraries without deployment preparation.

Make the profile explicit in service construction.

## Staging

Staging should exercise production controls.

Use separate signing keys if required.

Use separate release channels.

Use the same assurance profile where practical.

Test quorum and replay paths before production.

## Canary

Canary should use signed release identity.

Canary should not bypass release guard.

Canary may target a different channel.

Canary results should feed regression and safety-case review.

Promotion should be CAS controlled.

## Rollback

Rollback is a new release/channel state.

Do not mutate old release evidence.

Activate the intended known-good signed release.

CAS-update the channel.

Workers detect drift and should be restarted or reconciled.

Previously issued seals from the prior release should fail release binding.

## Disaster recovery

Restore strongly consistent authority stores first.

Restore release registry and channels.

Restore model registry.

Restore evidence chains.

Verify chain roots from retained anchors.

Restore workers only after verification.

Do not reconstruct approval authority from logs.

Do not reconstruct consumed seals as unused.

## Multi-region

Cross-region authority requires strong consistency or explicit regional authority partitioning.

Do not assume eventual replication is enough for single-use seals.

Do not assume eventual replication is enough for quorum consumption.

If authority is region-scoped, include region in identity and routing policy.

Keep one execution authority domain per request.

## Clock synchronization

Monitor NTP or equivalent.

Alert on skew beyond seal tolerance.

Use server-side backend time for leases where possible.

Do not use local monotonic timestamps as portable persisted timestamps.

Use monotonic clocks for process-local duration measurement.

## Process-local versus durable time

Process-local timeout loops should use monotonic time.

Cross-worker evidence should use portable wall-clock time.

Persisted timestamps are evidence.

Duration enforcement is process-local control.

Do not interchange the two concepts.

## Residual risk

Application-layer controls do not create a kernel sandbox.

HMAC is symmetric integrity, not public non-repudiation.

File preconditions do not atomically lock the filesystem.

Model consensus does not prove correctness.

Human approval does not prove safe implementation.

Evidence proves recorded state, not every external side effect.

Document these limits.

## Stronger isolation

For higher assurance, use container or microVM isolation.

Use immutable source mounts.

Use dedicated network policy.

Use cgroup resource enforcement.

Use seccomp or equivalent syscall policy.

Use separate credentials per task.

Use ephemeral environments.

## External side effects

For remote APIs, use target-system idempotency keys.

Record remote operation IDs.

Verify remote state after execution.

Shell replay protection alone cannot make an arbitrary external API exactly once.

## Compensation

For reversible operations, define compensation before execution where practical.

Do not assume rollback is always possible.

A failed compensation is a new incident.

Record compensation evidence separately.

## Exactly-once language

Avoid claiming true exactly-once execution across arbitrary systems.

The system provides single-use authority and replay barriers.

It provides deterministic evidence.

It provides idempotency hooks.

External systems can still create ambiguity.

## Operator decision rule

When authority is uncertain, stop.

When release identity is uncertain, stop.

When plan identity is uncertain, stop.

When source state is uncertain, stop.

When quorum state is uncertain, stop.

When replay state is uncertain, stop.

When sandbox capability is uncertain, stop.

When evidence integrity is uncertain, stop.

## Final production invariant

A model may suggest.

An ensemble may agree.

A human may approve.

A quorum may authorize.

A release may attest.

A seal may grant one short-lived execution opportunity.

A sandbox may contain the process.

Only the deterministic shell boundary actually launches the child.

Every high-assurance execution should leave a durable, signed, replay-resistant evidence trail that allows an operator to prove which authority surfaces were present and which exact plan crossed the boundary.
