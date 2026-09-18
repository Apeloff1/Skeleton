# Shell AI High-Assurance Execution Runbook

## Purpose

This runbook defines the production operating procedure for AI-directed shell
execution when the action is important enough that ordinary policy admission is
not sufficient.

The high-assurance path is designed for Jeeves and other structured planning
agents that can propose host-side work but must not independently create shell
authority.

The core principle is simple:

**model output proposes; deterministic controls authorize; the shell executes.**

No model response, confidence value, consensus vote, MCP request, or natural
language instruction is executable by itself.

## Scope

Use this runbook for:

- medium-risk sealed execution
- high-risk sandboxed execution
- production release-bound execution
- distributed multi-worker execution
- human dual-control workflows
- source-sensitive changes
- deployment or externally visible side effects
- privileged or destructive plans
- incident recovery after interrupted AI execution

This runbook does not turn the host shell into a complete operating-system
sandbox.

High-risk execution requires a separately verified sandbox backend.

## Control stack

A production execution may involve the following independent control layers:

1. authenticated principal
2. AI intent constraints
3. model/provider admission
4. tool catalog
5. effect registry
6. deterministic risk assessment
7. plan critic
8. plan compiler
9. policy decision
10. stale-plan pin
11. human approval
12. dual-control quorum
13. source preconditions
14. signed release evidence
15. assurance policy
16. assurance binding
17. signed execution seal
18. global seal replay barrier
19. runtime trust epoch
20. durable runtime-trust pin
21. distributed execution fence
22. durable execution-attempt ledger
23. sandbox capability attestation
24. resource ceilings
25. shell command policy
26. receipt evidence
27. decision journal
28. session evidence commitment
29. signed audit anchor
30. anti-rollback audit witness
31. recovery checkpoint
32. signed final execution evidence

These layers are intentionally not collapsed into one opaque "AI safety" score.

## Authority hierarchy

The model has proposal authority.

The critic has deterministic review authority.

The policy engine has admission authority.

Human approvers have review authority.

The quorum has dual-control authority.

The execution seal has final short-lived authorization authority.

The shell service has process creation authority.

The sandbox backend has isolation enforcement authority.

The child process has no authority to widen any of those controls.

## Risk-adaptive assurance

Default execution assurance is:

- low risk: standard execution
- medium risk: sealed execution
- high risk: sealed + verified sandbox execution
- critical risk: denied

The production profile additionally requires:

- release evidence for medium and high risk
- preconditions for high risk
- human approval for high risk
- dual-control quorum for high risk

Critical work remains denied even if every other control is present.

If critical work needs to run, change the policy deliberately through the policy
change-control process rather than bypassing the assurance layer.

## Assurance policy identity

AIExecutionAssurancePolicy has a deterministic SHA-256 digest.

The digest changes when any risk-band requirement changes.

Examples:

- medium moves from SEALED to SANDBOXED
- high stops requiring quorum
- medium begins requiring release evidence
- high begins requiring another evidence class

A reviewed execution seal binds the assurance policy digest.

Changing assurance policy after sealing invalidates the old seal.

This prevents a seal issued under policy A from silently executing under policy
B.

## Assurance binding

AssuranceBinding captures the non-secret execution authority surface.

The binding contains:

- schema version
- risk band
- assurance policy digest
- compiled plan fingerprint
- release evidence digest
- preconditions digest
- human approval ID
- quorum digest
- execution backend ID
- sandbox binding digest

The binding itself has a deterministic digest.

The execution seal signs that digest.

## Why bind the backend

Without backend binding, a plan could be reviewed for one sandbox and later sent
to a different backend.

The backend may differ in:

- syscall filter
- network namespace
- memory ceiling
- process ceiling
- filesystem isolation
- source mutability
- runtime version
- implementation identity

High-assurance sealing therefore commits to the exact verified sandbox binding.

A backend substitution changes the assurance digest.

Seal verification fails before execution.

## Why bind assurance policy

A policy change is a security-relevant state change.

Even a change that does not alter the current risk band's immediate outcome can
matter for audit and reproducibility.

The seal commits to the exact assurance policy identity.

This makes review-time policy part of the execution evidence.

## Why bind release evidence

The running worker must match an active signed release.

Release evidence commits to:

- code revision
- AI policy fingerprint
- tool catalog digest
- effect registry digest
- eval dataset digest
- eval result digest
- provider attestation
- safety case
- optional workspace manifest

The active release digest is bound into the assurance surface.

A production promotion changes release evidence.

Old seals do not cross the promotion boundary.

## Why bind preconditions

A reviewer may approve a plan against source state X.

If the source changes to Y before execution, the old review may no longer be
valid.

Preconditions bind expected resource digests.

For source files use SourceDigestProvider.

The preconditions digest is included both directly in the execution seal and in
the assurance binding.

## Why bind human approval

Human approval is bound to:

- principal
- intent fingerprint
- proposal fingerprint
- approval ID
- expiry

The approval ID is part of the assurance binding.

Approval substitution after sealing invalidates the seal.

Approval validity is independently checked at the service boundary.

The mere presence of an object named "approval" is not sufficient.

## Assurance-only human approval

A deterministic critic may not require human approval while the production
assurance profile does.

AIShellService therefore validates supplied human approval independently of the
critic policy.

If assurance required the approval but critic policy did not, the service still
consumes that approval as single-use authority.

This prevents one approval from authorizing multiple executions.

## Dual-control quorum

High-risk production execution uses AIApprovalQuorumStore.

A quorum approval is bound to:

- principal
- intent fingerprint
- proposal fingerprint
- required vote count
- distinct approvers
- vote roles
- vote timestamps
- vote decisions
- vote reasons
- expiry
- metadata
- consumed state

The quorum digest changes whenever material quorum evidence changes.

## Minimum quorum

The default quorum is two distinct approving identities.

A production deployment may require more.

The required vote count must never be one.

Single-person review is represented by the ordinary human approval layer, not
the dual-control quorum layer.

## Self approval

By default the execution principal may not approve their own quorum request.

This is separate from the ordinary human approval mechanism.

If policy explicitly allows principal voting, record that policy choice.

## Role policy

Quorum policy can restrict voter roles.

Examples:

- security
- release-manager
- on-call
- platform-owner
- compliance

A role string is evidence, not authentication.

The application authenticating the reviewer must establish that the reviewer
actually owns the role.

Do not trust a role supplied by an untrusted UI field.

## Quorum rejection

A reject vote is terminal.

After a reject:

- the approval state is REJECTED
- no additional vote may make it approved
- require fails
- consume fails
- service sealing/execution cannot use it

Rejection reason is retained in quorum evidence.

A new attempt requires a new quorum request.

## Vote immutability

One approver gets one decision.

The same approver may not change APPROVE to REJECT or REJECT to APPROVE.

An exact repeated vote may be treated idempotently.

A different role or different decision is rejected.

This prevents identity replay from rewriting the decision history.

## Quorum metadata

Bounded metadata may identify operational context such as:

- change request
- incident ID
- deployment ID
- maintenance window
- ticket ID

Do not place secrets in quorum metadata.

Metadata participates in the quorum digest.

## Quorum consumption

A complete quorum is single-use.

After the final execution seal is consumed, the quorum is consumed before child
execution crosses the final boundary.

A consumed quorum cannot be reused.

A failed child does not restore the quorum.

A retry requires new authority.

## Quorum storage

AIApprovalQuorumStore uses a strongly consistent VersionedStateBackend.

Votes use compare-and-swap.

Concurrent reviewers cannot silently overwrite each other.

A stale revision retries against the latest value.

Consumption uses compare-and-swap.

If the quorum changes between require and consume, consumption fails.

## Runtime trust epoch

Long-lived workers must not assume that startup validation remains true.

AIRuntimeTrustGuard binds the live authority surface into one epoch:

- code revision
- AI policy fingerprint
- tool catalog digest
- effect registry digest
- assurance policy digest
- workspace manifest digest
- admitted model/provider identities
- model registry revisions
- provider attestation digests
- release evidence digest
- release revision
- release-channel revision

The service pins the epoch at startup.

It rechecks the epoch before:

- creating new sessions
- review
- seal issuance
- execution-fence acquisition
- sealed execution

If the epoch drifts, the worker degrades and refuses new authority.

A provider/model upgrade is therefore not a transparent runtime mutation. It is
a trust-epoch change.

## Durable runtime-trust pin

Process-local pinning is not sufficient across worker restart.

RuntimeTrustPinStore persists a signed epoch pin per deployment scope.

Explicit rollover requires:

- current revision
- predecessor digest
- new epoch digest
- change ID
- reason
- valid signature

Restarting a worker does not automatically bless a changed model/release
surface.

A durable rollover is an operational change event.

## Distributed execution fence

A signed execution seal proves that a principal may execute a reviewed plan.

In a multi-worker fleet, that does not identify the one worker currently
entitled to cross the process boundary.

AIExecutionFenceManager adds a short-lived distributed lease bound to:

- session ID
- principal
- worker ID
- plan fingerprint
- runtime trust digest
- release evidence digest
- fence policy digest
- worst-case execution window

The backend issues a monotonic fencing token.

A stale worker cannot reuse an older token after lease expiry, release, renewal,
or takeover.

The fence TTL must cover the deterministic worst-case plan wall-time budget.

Do not renew implicitly in a hidden background thread.

## Durable execution-attempt ledger

The fence proves current ownership, but crash recovery also needs to know whether
the worker had already begun execution.

AIExecutionAttemptStore records a CAS-backed state machine:

- AUTHORIZED
- BOUNDARY_ENTERED
- SUCCEEDED
- FAILED
- ABANDONED

The authority binding includes:

- attempt/seal ID
- session ID
- principal
- worker ID
- plan fingerprint
- execution fence digest
- fencing token
- runtime trust digest
- release evidence digest
- execution backend ID

The tracking backend writes BOUNDARY_ENTERED immediately before delegating to
the real execution backend.

This location matters.

Writing the state too early would create false ambiguity.

Writing it after process creation would leave a crash window in which side
effects may have happened but the ledger still says NOT_STARTED.

## Attempt recovery semantics

Recovery must interpret attempt state conservatively.

AUTHORIZED means:

- the seal was consumed
- durable authority was reserved
- the process boundary was not entered

The old seal is no longer reusable.

A new plan/review/seal cycle is required.

BOUNDARY_ENTERED means:

- execution may have produced side effects
- no trustworthy terminal result is yet bound

Recovery requires verification.

Never auto-replay.

SUCCEEDED means a terminal provenance digest is bound.

FAILED means the execution path recorded a terminal failure.

ABANDONED means the attempt stopped before boundary entry.

A new authorization cycle is required.

## Recovery severity ordering

When several recovery findings exist, never let a weaker later finding downgrade
a stronger earlier one.

The recovery ordering is:

1. MANUAL_REVIEW
2. REQUIRE_VERIFICATION
3. REQUIRE_REPLAN
4. MARK_FAILED
5. RESUME_REVIEW
6. NONE

Examples:

- journal corruption plus release drift remains MANUAL_REVIEW
- boundary-entered ambiguity plus trust drift remains REQUIRE_VERIFICATION
- an abandoned pre-boundary attempt plus policy drift remains REQUIRE_REPLAN

Integrity failure always wins over convenience.

## Attempt evidence in final audit chain

Completed execution evidence binds the durable attempt authority into:

- AIRecoveryCheckpoint
- AIAuditAnchor
- AIExecutionEvidence

The execution attempt ID and authority digest must be paired.

For service-integrated attempts the attempt ID is the consumed execution seal
ID.

Changing the attempt authority binding changes the recovery checkpoint, audit
anchor, and final execution-evidence digests.

## Anti-rollback audit witness

A content-addressed audit chain detects internal mutation, but an attacker who
can restore an older complete chain may still present a valid historical root.

AIAuditWitnessStore publishes a separate signed monotonic witness over the
current audit root.

The witness also binds:

- sequence
- predecessor witness digest
- runtime trust digest
- release evidence digest
- observed time

Recovery and external audit can compare the expected latest witness with the
presented chain root.

A valid but older root is therefore detectable as rollback.

## Execution seal

The execution seal is a short-lived HMAC-protected authority artifact.

It binds:

- principal
- session
- exact PlanPin
- preconditions digest
- human approval ID
- release evidence digest
- assurance binding digest
- issue time
- expiry
- nonce

The HMAC key remains outside model context and child process environment.

## Seal TTL

Production seals should be short lived.

Recommended order of magnitude:

- seconds to a few minutes
- never hours by default

The authority enforces a maximum TTL.

Issue time too far in the future is rejected using clock-skew limits.

## Seal replay

Local single-worker mode uses ExecutionSealRegistry.

Multi-worker mode uses DistributedExecutionSealRegistry.

Distributed consumption is atomic put-if-absent on seal ID.

The first consumer wins.

All later consumers fail.

Never downgrade a production distributed deployment to process-local replay
protection during a backend outage.

If the replay backend is unavailable, fail closed.

## Seal consumption order

Recommended sequence:

1. ensure service is READY
2. verify current release/channel
3. verify PlanPin is current
4. verify source/resource preconditions
5. validate human approval
6. validate quorum
7. derive current assurance binding
8. run deterministic assurance policy
9. verify and atomically consume execution seal
10. consume quorum
11. consume assurance-only human approval
12. run final stale-plan check
13. execute through bound backend
14. verify result
15. write receipts
16. write provenance
17. checkpoint terminal session
18. anchor audit evidence

Changing this order requires explicit security review.

## Why assurance runs before seal consumption

If the currently selected backend cannot satisfy the required assurance level,
the operation should stop without consuming the seal.

Example:

a high-risk plan is presented with a host backend.

The assurance inspector rejects it before seal replay state is mutated.

The operator may select the correct verified sandbox and retry with a seal that
was actually bound to that sandbox.

## Sandbox binding

VerifiedSandboxExecutionBackend binds:

- plan fingerprint
- sandbox contract digest
- backend capability digest

Its binding has a deterministic digest.

That digest is included in AssuranceBinding.

## Sandbox capability attestation

The sandbox declares:

- backend ID
- backend version
- maximum isolation level
- private temporary directory
- clean environment
- read-only source capability
- network namespace
- home hiding
- process-group control
- no-new-privileges
- syscall filtering
- resource-limit support
- maximum enforceable resource profile

The verifier compares declared capability against the contract.

A missing required capability blocks binding.

## Capability drift

Capabilities are checked again at execution.

If the backend capability digest changed after binding:

execution fails.

Do not auto-accept a "stronger-looking" capability change.

A changed backend identity is changed evidence.

Re-attest and reseal.

## Sandbox contract

AISandboxContract includes isolation and resource requirements.

Typical high-risk requirements include:

- SANDBOXED isolation
- private tmp
- clean environment
- no ambient home
- network namespace when network is disabled
- process group
- no-new-privileges
- syscall filter
- resource limits

## Resource ceilings

AIResourceProfile includes:

- wall-clock seconds
- CPU seconds
- memory bytes
- process count
- file bytes
- open files
- output bytes

Risk-adaptive resource policy tightens ceilings for higher-risk plans.

The contract is declarative.

The backend must prove it can enforce the ceilings.

## Source preconditions

SourceDigestProvider pins one configured root.

It rejects:

- absolute resource IDs
- parent traversal
- missing files
- non-files
- oversized files
- symlinks by default
- symlink targets outside root

Manifest hashing is bounded by entry count and total bytes.

## Immutable execution workspace

Digest verification alone leaves a check-to-use race.

For high-risk source modification prefer:

- immutable VCS checkout
- content-addressed snapshot
- copy-on-write filesystem
- read-only source mount plus narrow output mount
- sandbox-specific filesystem snapshot

Preconditions should describe the immutable snapshot actually presented to the
sandbox.

## Model admission

Model/provider identity should be admitted before ensemble planning.

AIModelAdmission checks:

- model/provider exists
- registry entry is active
- exact provider identity
- exact model identity
- optional exact model version
- optional exact adapter version
- optional attestation digest
- structured-output capability
- tool-use capability
- optional critique capability
- optional parallel-candidate capability
- minimum input capacity
- minimum output capacity
- protocol version
- exact tool catalog digest

An unregistered model does not get proposal authority in production.

## Model registry revision

Provider attestations are versioned.

A changed attestation creates a new registry revision.

If an admitted ensemble pins an attestation digest and the registry changes,
planning fails until admission requirements are updated.

This prevents silent model upgrades.

## Ensemble planning

Provider-diverse ensemble planning may improve planning robustness.

It does not create shell authority.

The ensemble:

- queries admitted members
- records provider health
- respects model circuits
- respects rate limits
- groups exact proposal shapes
- counts unique model identities
- can require provider diversity
- applies deterministic candidate selection

The selected proposal still goes through the ordinary critic, compiler, policy,
approval, seal, and shell execution path.

## Consensus limitations

Two models agreeing does not prove correctness.

Models may share:

- training data
- provider infrastructure
- prompt vulnerabilities
- systematic assumptions
- compromised context

Consensus is one planning signal.

It is never a substitute for deterministic effect policy or sandboxing.

## MCP admission

Remote MCP tools/call requests may use MCPReplayGuard.

The guard binds:

- authenticated principal
- request ID
- canonical request payload

Admission uses atomic put-if-absent.

A validated tool call is single use during the replay window.

## MCP validation order

Recommended gateway order:

1. validate protocol version
2. validate method
3. validate tool name
4. validate argument shape
5. validate environment reference shape
6. validate timeout
7. authorize principal/tool
8. atomically admit replay ID
9. produce AIAction

Malformed or unauthorized requests must not burn a valid replay token.

A second valid identical tools/call request is still a replay and is rejected.

## MCP principal scope

The replay key is principal scoped.

Two distinct authenticated principals may use the same request ID without
sharing authority.

Do not derive principal from request body or routing headers.

## Release-bound startup

Production AIShellService may use AIStartupReleaseGuard.

At startup it verifies:

- active release channel exists
- referenced release exists
- release is active
- channel revision matches release revision
- channel evidence digest matches
- registry signature matches
- signature verifies
- safety case is deployable
- runtime code revision matches
- runtime policy fingerprint matches
- runtime tool digest matches
- runtime effect digest matches
- optional provider attestation matches
- optional workspace manifest matches

A mismatch puts startup into FAILED state.

## Release drift while running

The service rechecks release/channel state at operational boundaries.

If drift is detected while READY:

the service transitions to DEGRADED.

New sessions or execution fail.

Do not continue on a stale release just because startup originally succeeded.

## Release promotion

Recommended production promotion:

1. run tests
2. run AI eval suite
3. run red-team suite
4. verify provider attestation
5. verify sandbox attestation
6. build safety case
7. build release evidence
8. sign release evidence
9. register release
10. activate release
11. CAS-promote canary channel
12. observe
13. CAS-promote production channel

Existing seals tied to the previous release do not cross promotion.

## Evidence and receipts

Every child attempt should produce an ExecutionReceipt.

Receipt evidence should include:

- logical command name
- correlation ID
- command fingerprint
- start/finish timestamps
- duration
- return code
- timeout flag
- output-limit flag
- stdout/stderr byte counts
- attempt number
- receipt ID
- bounded metadata

Do not store secret output in receipts.

## Durable receipt chain

DistributedReceiptChain preserves ReceiptChain hash semantics over a durable
content-addressed CAS store.

Immutable nodes are addressed by hash.

Only the chain head is mutable via CAS.

A losing concurrent writer cannot corrupt the committed chain.

## Decision journal

DistributedAIDecisionJournal stores AI control events durably.

The journal captures decisions, not hidden chain-of-thought.

Useful events include:

- planning started
- proposal accepted
- critic result
- approval issued
- quorum state
- execution started
- verification result
- terminal state

## Session-scoped evidence

Global receipt and journal chains may advance because unrelated sessions run.

Recovery therefore uses session-scoped commitments.

SessionExecutionEvidence commits to the receipts belonging to one AI session.

SessionJournalEvidence commits to the journal events belonging to one AI
session while retaining their global sequence references.

## Recovery checkpoint

AIRecoveryCheckpoint v2 binds:

- legacy session checkpoint
- session execution evidence digest
- session journal digest
- release evidence digest
- sandbox binding digest

This prevents unrelated global traffic from falsely invalidating recovery while
still detecting changes to the interrupted session itself.

## Strict recovery

StrictAIRecoveryManager evaluates:

- decision journal integrity
- session journal commitment
- global receipt-chain integrity
- session execution evidence
- AI policy fingerprint
- tool catalog digest
- effect registry digest
- release evidence
- sandbox binding

Possible actions include:

- NONE
- RESUME_REVIEW
- REQUIRE_REPLAN
- REQUIRE_VERIFICATION
- MANUAL_REVIEW
- ABORT

## Interrupted execution

If the process crashed while the AI session was EXECUTING:

do not blindly replay the plan.

Inspect session-scoped receipt evidence.

If execution evidence is missing or changed:

require verification.

If side effects cannot be proven:

manual review may be necessary.

## Exactly-once limits

Shell infrastructure cannot guarantee exactly-once behavior for arbitrary
external systems.

Single-use seals and quorum approvals prevent duplicate authority.

They cannot make an external non-idempotent API atomic.

For external actions use target-system idempotency keys when available.

## Failure behavior

### Missing release

Stop.

Do not fall back to unsigned defaults.

### Release mismatch

Degrade or fail.

Reconcile deployment.

### Missing precondition checker

Stop.

Do not treat unchecked preconditions as verified.

### Precondition mismatch

Stop before consuming the seal.

Reinspect source state and review again.

### Human approval invalid

Stop.

Do not count object presence as approval.

### Quorum incomplete

Stop.

Do not lower required vote count dynamically.

### Quorum rejected

Stop.

Open a new review only after the rejection reason is addressed.

### Quorum stale

Stop.

Reload current quorum evidence.

Do not reuse a digest from an older vote set.

### Seal expired

Stop.

Revalidate and issue new seal.

### Seal replay

Stop and investigate.

Do not create a replacement automatically for a high-risk action.

### Sandbox unavailable

Stop high-risk execution.

Do not fall back to host execution.

### Sandbox capability drift

Stop.

Re-attest backend and reseal.

### Receipt corruption

Stop recovery.

Escalate to manual review.

### Journal corruption

Stop recovery.

Escalate to manual review.

## Incident response

For suspected unsafe AI execution:

1. stop new AI execution
2. quarantine affected model/proposal/command
3. freeze release promotion
4. capture active release/channel state
5. capture decision journal root
6. capture receipt root
7. capture session evidence
8. capture audit anchor
9. identify seal ID
10. identify human approval ID
11. identify quorum ID
12. identify sandbox binding
13. identify principal
14. identify worker instance
15. inspect external side effects
16. decide compensation manually
17. rotate signing/seal keys if compromise is suspected
18. create regression eval case
19. update safety case
20. release through normal signed promotion

## Key compromise

If execution-seal HMAC key may be compromised:

- disable sealing
- stop sealed execution
- rotate key
- invalidate outstanding seals operationally
- inspect recent seal consumption
- review affected audit period

Because seal IDs are short lived, keep TTL low to reduce exposure.

## Release signing compromise

If ArtifactSigner key may be compromised:

- freeze release channels
- rotate signing key
- verify active release through independent deployment evidence
- rebuild and resign evidence
- record key-rotation boundary

Do not silently trust artifacts signed during the uncertain period.

## Backend outage

### Policy backend

Fail closed for new high-risk work.

### Quorum backend

Fail closed for quorum-required work.

### Seal replay backend

Fail closed for distributed sealed execution.

### Release channel backend

Do not invent a release.

### Durable evidence backend

Do not claim durable audit guarantees while unavailable.

Execution policy may choose to stop entirely for production high-risk work.

## Observability

Track at least:

- plans by risk band
- assurance denials by reason
- release verification failures
- precondition failures
- human approval failures
- quorum opens
- quorum approvals
- quorum rejections
- quorum expiry
- quorum consumption
- seal issuance
- seal expiry
- seal replay
- execution-fence acquisition/expiry/takeover
- stale fencing token
- attempt AUTHORIZED
- attempt BOUNDARY_ENTERED
- attempt terminal failure
- attempt ledger outage
- attempt authority mismatch
- runtime-trust drift
- durable trust-pin rollover
- audit-witness rollback mismatch
- assurance digest mismatch
- sandbox attestation failure
- sandbox capability drift
- source drift
- recovery action
- audit verification failure

Avoid high-cardinality labels containing raw prompts or child output.

## Sensitive data

Never put these into model-visible context or routine logs:

- seal HMAC key
- release signing key
- raw secret values
- inherited process environment
- unrestricted home-directory contents
- authentication bearer tokens
- private reviewer credentials

Use references and digests instead.

## Operator checklist: medium risk

Before execution confirm:

- service READY
- current release verified when production policy requires it
- PlanPin current
- seal issued under current assurance policy
- principal matches
- approval present if policy requires it
- replay registry available

Execute only through the backend bound into the seal.

## Operator checklist: high risk

Before execution confirm:

- all medium-risk checks
- preconditions verified
- human approval valid
- quorum complete
- no reject vote
- quorum digest matches seal
- verified sandbox selected before seal issuance
- sandbox binding matches seal
- source state is immutable or acceptably snapshotted
- resource ceilings are enforceable
- release evidence is current
- audit/evidence backend is healthy

If any item is uncertain, stop.

## Operator checklist: recovery

Before resuming confirm:

- journal verifies
- session journal digest matches
- receipt chain verifies
- session execution evidence matches
- release digest matches
- sandbox binding matches
- runtime trust epoch matches
- durable trust pin matches
- execution-attempt authority digest matches
- attempt state is understood
- audit witness is current
- policy/tool/effect surfaces match
- external side effects are understood

Resume only according to StrictAIRecoveryManager action.

## Design invariant

No single AI-generated value should be sufficient to authorize host execution.

The final authority must be:

- deterministic
- bounded
- identity-bound
- state-bound
- short-lived
- single-use
- auditable
- replay-resistant
- revocable through policy/release state

That invariant is the standard for the 2026 AI-ready shell plane.
