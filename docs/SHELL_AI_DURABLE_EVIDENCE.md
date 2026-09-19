# Durable AI Shell Evidence and Recovery

## Purpose

This document defines the durable evidence model for AI-directed shell execution.

It describes how one reviewed execution remains auditable after:

- worker restart;
- process crash;
- concurrent writers;
- later unrelated executions;
- partial finalization;
- evidence-store interruption;
- secondary-index loss;
- stale readers;
- retry after a successful child process;
- audit-chain growth;
- receipt-chain growth.

The design separates execution authority from evidence durability.

A durable record never grants permission to execute.

A durable record only proves what authority existed, what was executed, and what evidence was committed.

The execution boundary remains the policy-first shell service.

The model-facing planner still proposes logical commands only.

Deterministic controls still own admission.

Signed seals still bind reviewed authority.

Durable evidence begins after or around those authority decisions.

## Scope

The durable path covers five evidence planes:

1. AI decision journal.
2. Shell execution receipts.
3. Session-scoped evidence manifests.
4. Recovery checkpoints and finalization state.
5. Signed audit and execution evidence.

The primary implementations are:

- `DistributedAIDecisionJournal`;
- `DistributedReceiptChain`;
- `SessionEvidenceIntegrityVerifier`;
- `AIRecoveryCheckpointStore`;
- `AIExecutionFinalizationStore`;
- `AIExecutionEvidenceFinalizer`;
- `AIExecutionFinalizationReconciler`;
- `DurableSessionRecoveryVerifier`.

The compatibility import for durable receipts remains:

- `skeleton.shells.durable_receipts.DistributedReceiptChain`.

The canonical implementation is:

- `skeleton.shells.distributed_receipts.DistributedReceiptChain`.

Both imports resolve to the same class.

## Core invariant

The central invariant is:

> A finalized execution is valid only when every session-scoped claim can be traced to an exact committed historical prefix of the authoritative decision and receipt chains.

A current global root is not enough.

A globally valid chain is not enough.

A session manifest is not enough.

A signed bundle is not enough.

The evidence layers must agree.

## Authority versus evidence

Execution authority includes:

- reviewed proposal identity;
- policy fingerprint;
- tool-catalog digest;
- effect-registry digest;
- approval identity where required;
- quorum approval where required;
- execution seal;
- runtime trust epoch;
- release evidence;
- optional execution fence;
- sandbox binding;
- backend identity;
- execution attempt identity.

Evidence durability includes:

- decision events;
- execution receipts;
- session journal projection;
- session execution evidence;
- session integrity report;
- recovery checkpoint;
- audit anchor;
- audit witness;
- signed execution evidence;
- finalization progress.

Evidence does not widen authority.

Authority does not make evidence durable by itself.

## Threat model

The durable evidence design assumes failures can occur at any instruction boundary.

Examples include:

- crash after immutable node write but before head CAS;
- crash after head CAS but before secondary index write;
- crash after receipt commit but before finalization;
- crash after recovery checkpoint write but before audit anchor;
- crash after audit anchor but before witness;
- crash after witness but before signed execution evidence;
- crash after signed evidence write but before finalization state advances;
- competing workers appending unrelated events;
- delayed retry on another worker;
- stale worker reading an old head;
- malformed or substituted stored values;
- manual storage corruption;
- accidental duplicate identifiers.

The design treats storage corruption differently from incomplete work.

Missing durable work can be resumable.

Conflicting or corrupted durable work requires manual review.

## Non-goals

The durable evidence layer does not claim:

- distributed transaction atomicity across all stores;
- exactly-once external side effects;
- rollback of already executed child processes;
- public-key provenance for HMAC-signed artifacts;
- filesystem snapshot atomicity;
- consensus across arbitrary storage systems;
- automatic repair of contradictory signed evidence;
- authority to re-run a command during recovery.

Recovery verifies and resumes evidence finalization.

Recovery does not silently replay a child process.

## Data-plane overview

The durable decision path is:

```text
model proposal
  -> deterministic review
  -> optional human/quorum approval
  -> execution seal
  -> execution attempt
  -> ShellExecutor
      -> durable receipt chain
  -> AI orchestrator
      -> durable decision journal
  -> session execution evidence
  -> session journal projection
  -> session inclusion verification
  -> recovery checkpoint
  -> audit anchor
  -> optional audit witness
  -> signed execution evidence
  -> finalization COMPLETE
```

Each arrow represents a separately verifiable boundary.

## Durable decision journal

### Purpose

The distributed decision journal records host-visible AI shell decisions.

It never stores hidden model reasoning.

Typical events include:

- plan proposed;
- plan reviewed;
- plan approved;
- plan completed;
- plan failed.

### Storage model

Each event is immutable.

The key is derived from the event hash.

The mutable state is a small CAS head containing:

- sequence;
- root hash.

The event hash preserves the existing `AIDecisionJournal` hash contract.

This allows the distributed implementation to remain compatible with existing event semantics.

### Append algorithm

A writer:

1. Reads the current head and revision.
2. Assigns sequence = head sequence + 1.
3. Computes the event hash over:
   - previous root;
   - sequence;
   - kind;
   - observed time;
   - session ID;
   - intent ID;
   - proposal ID;
   - summary;
   - structured data.
4. Stores the immutable event by hash.
5. Attempts CAS on the head.
6. Returns if the CAS wins.
7. Re-reads head if the CAS loses.
8. Retries against the new committed head.

### Orphan events

A losing writer may leave an immutable event that is not reachable from the committed head.

This is expected.

It is not corruption.

The event is an orphan candidate.

An orphan candidate:

- may be internally self-consistent;
- may have a valid hash;
- may form a valid prefix from genesis;
- is not authoritative unless it is an ancestor of the committed head.

This distinction is critical during restart verification.

### Journal ancestry

Historical roots are supported through:

- `snapshot_at(root_hash)`;
- `verify_root(root_hash)`;
- `root_is_ancestor(root_hash)`.

A historical root is acceptable for finalized evidence only if:

1. the prefix verifies cryptographically;
2. the root is reachable from genesis;
3. the root is an ancestor of the current committed head.

A self-consistent orphan fails condition 3.

### Current versus historical roots

The current root can advance after an execution is finalized.

That does not invalidate prior evidence.

A finalization captures the journal root observed during its integrity proof.

Later unrelated events may advance the current root.

Recovery reconstructs the historical prefix at the captured root.

It does not require the captured root to remain current.

## Durable receipt chain

### Purpose

The durable receipt chain records actual shell execution outcomes.

Each receipt contains:

- command identity;
- correlation ID;
- command fingerprint;
- start time;
- finish time;
- duration;
- return code;
- success state;
- timeout state;
- output-limit state;
- output byte counts;
- retry attempt number;
- receipt ID;
- bounded metadata.

### Hash compatibility

The distributed implementation uses the existing `ReceiptChain._hash` semantics.

That preserves receipt identity across the local and durable implementations.

### Storage model

The receipt chain uses:

- immutable receipt nodes keyed by receipt hash;
- a CAS head;
- an immutable receipt-ID index.

The index maps a receipt ID to:

- receipt hash;
- command fingerprint;
- global sequence.

### Why the index exists

Session execution evidence references receipt IDs.

Recovery must prove that each ID exists in the authoritative committed chain.

Scanning the entire chain for every lookup is avoidable in the normal case.

The index provides direct lookup.

### Post-head-CAS crash window

There is a narrow failure window:

1. immutable receipt node is written;
2. head CAS succeeds;
3. worker crashes;
4. receipt-ID index has not yet been written.

The committed receipt is authoritative because the head points to it.

The missing index must not cause a retry to append the same receipt again.

The implementation therefore self-heals.

On lookup with a missing index:

1. scan the committed chain;
2. search for the receipt ID;
3. require exactly one committed match;
4. rebuild the immutable index;
5. continue lookup.

If multiple committed nodes use the same receipt ID, recovery fails closed.

### Receipt-ID collision

A receipt ID may not bind different receipt content.

If an existing index binds the ID to another receipt:

- append fails;
- recovery treats the condition as conflict.

### Receipt historical roots

The receipt chain exposes:

- `snapshot_at(root_hash)`;
- `verify_root(root_hash)`;
- `root_is_ancestor(root_hash)`.

The same orphan rule applies as for the decision journal.

A self-consistent uncommitted receipt node is not authoritative.

## Session journal evidence

The global decision journal is shared.

One session does not own the entire global chain.

`SessionJournalEvidence` projects only the events whose `session_id` matches the target session.

Each projected event records:

- global sequence;
- event hash;
- kind;
- proposal ID.

The session projection preserves global ordering.

It does not renumber events.

This matters because an event's global sequence is part of its durable identity.

## Session execution evidence

`SessionExecutionEvidence` is built from the actual plan execution report.

For each plan step it captures:

- step ID;
- correlation ID;
- receipt IDs;
- receipt fingerprints;
- return codes;
- attempt count;
- step success.

A skipped or never-dispatched step can have zero attempts.

A dispatched step must have aligned vectors.

Receipt IDs, fingerprints, and return codes must have the same length as the attempt count.

## Session integrity verification

### Purpose

A valid global chain does not prove that a session manifest is truthful.

The session integrity verifier closes that gap.

It checks both chain integrity and exact inclusion.

### Journal checks

For every `SessionJournalEvent`, the verifier checks:

- global sequence exists;
- event hash matches;
- event kind matches;
- proposal ID matches;
- stored event session ID matches the target session.

### Receipt checks

For every receipt reference, the verifier checks:

- receipt ID exists exactly once;
- receipt fingerprint matches;
- correlation ID matches;
- return code matches;
- attempt number matches its position in the retry sequence.

### Chain checks

The verifier also checks:

- decision journal integrity;
- receipt chain integrity.

When historical roots are supplied, it verifies those exact historical prefixes.

### Historical verification

When an expected root is supplied and the chain supports historical resolution:

1. reconstruct the prefix ending at expected root;
2. verify the prefix;
3. verify the current chain;
4. require the expected root to be an ancestor of current head;
5. perform session inclusion checks against the historical prefix.

This makes a finalized proof stable after later chain growth.

### Integrity report

`SessionEvidenceIntegrityReport` contains:

- session ID;
- journal-chain status;
- receipt-chain status;
- journal root;
- receipt root;
- journal manifest digest;
- receipt manifest digest;
- journal inclusion rows;
- receipt inclusion rows;
- issue list;
- deterministic report digest.

The report digest is committed into later evidence layers.

## Integrity digest binding

The integrity digest is included in:

- `AIRecoveryCheckpoint.session_integrity_digest`;
- `AIExecutionEvidence.session_integrity_digest`.

The same digest must appear in both.

A mismatch is evidence conflict.

This prevents a recovery checkpoint from proving one inclusion set while signed execution evidence proves another.

## Recovery checkpoint

### Role

The recovery checkpoint is the restart handoff.

It binds:

- session checkpoint;
- session execution evidence digest;
- session journal digest;
- release evidence digest;
- sandbox binding digest;
- runtime trust digest;
- authority-health policy digest;
- execution attempt identity;
- execution attempt authority digest;
- session integrity digest.

The embedded session checkpoint binds:

- session phase;
- transition count;
- journal root;
- receipt root;
- policy fingerprint;
- tool-catalog digest;
- effect-registry digest;
- other session identity.

### Historical roots in the checkpoint

The journal and receipt roots in the checkpoint are not expected to remain globally current.

They identify the exact evidence prefix observed during finalization.

Recovery verifies those roots as committed historical ancestors.

## Recovery checkpoint store

The recovery store uses immutable per-finalization records.

It also maintains a monotonic per-session head.

The per-session head records:

- session ID;
- finalization ID;
- checkpoint digest;
- transition count.

### Rollback protection

A new checkpoint with a lower transition count does not replace a newer session head.

A checkpoint at the same transition count with a different digest is conflict.

A checkpoint at a higher transition count can advance the head through CAS.

### Immutable item rule

One finalization ID may not bind two different recovery checkpoint digests.

A retry with the same digest is idempotent.

A retry with another digest is conflict.

## Finalization state

Finalization progresses through:

1. STARTED.
2. SESSION_EVIDENCE.
3. CHECKPOINTED.
4. ANCHORED.
5. WITNESSED.
6. SIGNED.
7. COMPLETE.

Each phase is monotonic.

Retries at an older phase do not roll state backward.

Retries at the same phase with different evidence are conflicts.

### Required durability capabilities

A finalization also records which layers were required:

- recovery checkpoint;
- audit witness;
- signed execution evidence.

This prevents COMPLETE from having different meanings on different workers.

If witness support was required, COMPLETE requires a witness.

If signed execution evidence was required, COMPLETE requires it.

## Audit anchor

The audit anchor binds:

- session;
- recovery checkpoint digest;
- provenance digest;
- journal root;
- receipt root;
- session execution evidence digest;
- release evidence;
- sandbox binding;
- runtime trust;
- authority-health policy;
- execution attempt identity;
- execution-attempt authority digest;
- finalization ID.

### Finalization ID idempotency

Audit anchor append can be retried by finalization ID.

If the same finalization ID already exists with the same bindings, the existing anchor is reused.

If the same finalization ID binds different data, the operation fails.

## Audit witness

The optional audit witness publishes the audit root.

Witness lookup can resolve historical witnesses.

A retry does not require an old witness to remain the latest global witness.

It requires the old witness to remain canonical at its sequence.

This allows unrelated later sessions to advance the witness chain.

## Signed execution evidence

The signed execution bundle binds:

- session;
- intent fingerprint;
- proposal fingerprint;
- provenance digest;
- recovery checkpoint digest;
- session execution evidence digest;
- session journal digest;
- session integrity digest;
- audit anchor;
- audit chain node;
- release evidence;
- sandbox binding;
- model attestation;
- execution seal;
- quorum approval;
- runtime trust;
- authority-health policy;
- execution attempt;
- audit witness;
- terminal attempt state.

### Attempt idempotency

When an execution attempt ID is available, signed evidence is indexed logically by that attempt.

A retry for the same attempt may reuse the existing signed bundle.

The same attempt may not bind a different final evidence digest.

## Finalization ordering

The normal finalizer order is:

1. validate terminal session;
2. validate execution/provenance bindings;
3. validate terminal execution attempt;
4. reserve finalization state;
5. verify decision journal chain;
6. verify receipt chain;
7. build session execution evidence;
8. persist session execution evidence;
9. advance finalization to SESSION_EVIDENCE;
10. build session journal projection;
11. verify exact session inclusion;
12. capture sampled historical roots;
13. build recovery checkpoint;
14. persist recovery checkpoint;
15. advance to CHECKPOINTED;
16. append or reuse audit anchor;
17. verify audit anchor chain;
18. advance to ANCHORED;
19. publish or reuse witness if configured;
20. verify witness;
21. advance to WITNESSED;
22. build signed execution evidence if configured;
23. append or reuse signed evidence;
24. verify signed evidence chain;
25. advance to SIGNED;
26. advance to COMPLETE.

No step executes the child process.

The child process has already reached a terminal state.

## Service-level execution

`AIShellService.execute_sealed_and_finalize` combines:

- sealed execution;
- durable execution-attempt lookup;
- evidence finalization.

If child execution completes but finalization fails:

- the execution attempt remains terminal;
- the service transitions to DEGRADED;
- new work is blocked;
- recovery resumes evidence work;
- the child is not silently executed again.

This behavior intentionally favors evidence correctness over availability.

## Durable recovery verifier

### Purpose

`DurableSessionRecoveryVerifier` is the operator-facing restart proof.

It begins with only:

- finalization ID;
- durable stores;
- durable journal;
- durable receipt chain.

It reconstructs the rest.

### Verification order

The verifier checks:

1. finalization record exists;
2. recovery checkpoint exists;
3. finalization and checkpoint digests agree;
4. checkpoint session matches finalization session;
5. runtime trust matches;
6. release evidence matches;
7. execution attempt identity matches;
8. durable session execution evidence exists;
9. session evidence digest agrees with finalization;
10. session evidence digest agrees with recovery checkpoint;
11. historical journal prefix can be reconstructed;
12. session journal digest agrees with recovery checkpoint;
13. historical receipt prefix can be reconstructed;
14. session inclusion proof succeeds;
15. reconstructed integrity digest matches checkpoint;
16. required signed execution evidence exists;
17. signed evidence chain verifies;
18. signed evidence digest matches finalization;
19. signed evidence session matches;
20. signed evidence provenance matches;
21. signed evidence checkpoint digest matches;
22. signed evidence session evidence digest matches;
23. signed evidence session journal digest matches;
24. signed evidence integrity digest matches;
25. signed evidence runtime trust matches;
26. signed evidence release evidence matches;
27. signed evidence attempt identity matches;
28. signed evidence attempt authority matches;
29. signed evidence chain node matches finalization.

## Recovery status

The verifier returns one of three statuses.

### VERIFIED

VERIFIED means:

- finalization is COMPLETE;
- all required durable layers are present;
- no conflict exists;
- no corruption exists;
- historical roots are committed ancestors;
- inclusion proof succeeds;
- signed evidence bindings agree.

### INCOMPLETE

INCOMPLETE means durable work is missing but no contradictory evidence has been found.

Examples:

- finalization record missing;
- recovery checkpoint missing;
- session execution evidence missing;
- required signed-evidence store unavailable;
- required signed evidence missing;
- finalization has not reached COMPLETE.

INCOMPLETE can be safe to resume.

It does not authorize process replay.

### MANUAL_REVIEW

MANUAL_REVIEW means stored evidence conflicts or is corrupted.

Examples:

- finalization checkpoint digest differs from stored checkpoint;
- session IDs conflict;
- runtime trust differs;
- release evidence differs;
- attempt identity differs;
- session evidence digest differs;
- historical journal node is corrupted;
- historical receipt node is corrupted;
- integrity digest differs;
- signed evidence points to another checkpoint;
- signed attempt authority differs;
- signed evidence chain fails.

Manual review is intentionally fail closed.

## Recovery decision rule

Use this rule:

```text
if VERIFIED:
    allow evidence-dependent recovery consumers to proceed
elif INCOMPLETE:
    resume evidence finalization only
elif MANUAL_REVIEW:
    stop automatic recovery and escalate
```

Do not convert MANUAL_REVIEW into INCOMPLETE automatically.

Conflict is stronger evidence than absence.

## Restart procedure

### Step 1: stop new execution admission

If the service degraded because finalization failed:

- keep new execution blocked;
- preserve the terminal attempt;
- do not discard the seal-use record;
- do not mint a replacement seal for the same attempt.

### Step 2: identify the finalization

Use:

- finalization ID from partial state;
- or derive it from session, provenance, and execution attempt when appropriate.

### Step 3: run finalization reconciliation

Use `AIExecutionFinalizationReconciler`.

The reconciler can:

- inspect current phase;
- find already-written evidence;
- fast-forward lagging finalization state when exact evidence proves it;
- distinguish resumable gaps from manual review.

### Step 4: run durable recovery verification

Use `DurableSessionRecoveryVerifier.verify(finalization_id)`.

Read:

- status;
- findings;
- historical roots;
- reconstructed integrity report.

### Step 5: handle VERIFIED

If VERIFIED:

- evidence is internally consistent;
- the historical chain roots are committed;
- the signed bundle agrees;
- recovery consumers can use the proof.

Do not re-execute the child.

### Step 6: handle INCOMPLETE

If INCOMPLETE:

- inspect missing finding codes;
- resume only the missing finalization stages;
- reuse idempotent append operations;
- re-run verification.

Typical missing layers can be:

- recovery checkpoint;
- witness;
- signed evidence;
- state advance after an already committed artifact.

### Step 7: handle MANUAL_REVIEW

If MANUAL_REVIEW:

- stop automated finalization;
- snapshot relevant durable records;
- capture current global heads;
- capture historical root lookup results;
- preserve conflicting values;
- investigate storage corruption or substitution.

Do not overwrite the conflicting record in place.

## Common restart scenarios

### Crash before session evidence persistence

Expected state:

- execution attempt terminal;
- receipt chain contains execution receipt;
- decision journal may contain terminal event;
- finalization STARTED;
- session evidence missing.

Expected recovery status:

- INCOMPLETE.

Action:

- rebuild session evidence from the terminal execution bundle if still available;
- or use a durable execution report source if one exists;
- continue finalization.

### Crash after session evidence persistence

Expected state:

- finalization may still say STARTED;
- session evidence exists.

Reconciler behavior:

- verify exact session evidence;
- advance state to SESSION_EVIDENCE.

### Crash after recovery checkpoint persistence

Expected state:

- immutable recovery item exists;
- finalization may still be SESSION_EVIDENCE.

Reconciler behavior:

- verify checkpoint authority bindings;
- advance state to CHECKPOINTED.

### Crash after audit anchor append

Expected state:

- audit anchor exists;
- finalization may still be CHECKPOINTED.

Reconciler behavior:

- locate anchor by finalization ID;
- verify anchor chain;
- recover historical audit root from anchor chain node;
- advance state to ANCHORED.

### Crash after witness publish

Expected state:

- canonical witness exists;
- finalization may still be ANCHORED.

Reconciler behavior:

- find witness by exact audit root, trust, and release;
- verify canonical sequence/signature;
- advance state to WITNESSED.

### Crash after signed evidence append

Expected state:

- signed bundle exists;
- finalization may still be WITNESSED.

Reconciler behavior:

- find bundle by execution attempt;
- verify chain and signature;
- advance to SIGNED;
- advance to COMPLETE when all required layers exist.

### Crash after receipt head CAS

Expected state:

- receipt node is committed;
- receipt-ID index may be missing.

Reader behavior:

- scan committed chain for receipt ID;
- require exactly one match;
- rebuild index;
- avoid duplicate receipt append.

## Multi-worker deployment

### Shared backend requirement

For cross-worker recovery, workers must share the durable backend used for:

- decision journal;
- receipts;
- finalization state;
- recovery checkpoints;
- session evidence;
- audit anchors;
- witnesses when enabled;
- signed execution evidence;
- execution attempts when distributed tracking is enabled.

A process-local backend cannot provide cross-worker recovery.

### Namespace stability

Namespaces are part of storage identity.

Changing a namespace creates a logically different store.

Deployment configuration must keep namespaces stable across restarts.

Recommended practice:

- version namespace changes explicitly;
- migrate data before switching;
- never silently change production namespace names.

### Clock semantics

Durable event timestamps use wall-clock time.

Process-local control loops may use monotonic time.

Do not compare monotonic values generated by separate processes.

Historical chain ordering is sequence-based, not clock-based.

### CAS semantics

The backend must provide:

- read with revision;
- put-if-absent;
- compare-and-swap;
- delete where required by stores.

CAS conflicts are normal under concurrency.

A conflict is not corruption by itself.

Writers retry against the newly committed head.

## Storage backend expectations

A production backend should provide:

- linearizable or sufficiently strong per-key CAS;
- durable immutable value retention;
- no silent last-writer-wins overwrite of CAS keys;
- stable binary/text serialization;
- bounded latency;
- operational backups;
- explicit corruption monitoring.

The in-memory fenced store is a reference implementation.

It is not process-persistent.

## Historical root retention

Historical recovery depends on immutable nodes remaining available.

A compaction policy must not delete nodes still referenced by:

- recovery checkpoints;
- finalization state;
- audit anchors;
- signed execution evidence;
- retention policy.

A current head alone is insufficient to reconstruct an older finalized proof.

## Compaction rules

Safe compaction requires a reachability analysis.

Before deleting an old node, prove that no retained finalization references a historical root whose prefix includes that node.

For journal nodes:

- follow previous hashes from every retained journal root.

For receipt nodes:

- follow previous hashes from every retained receipt root.

For audit evidence:

- follow the evidence-chain retention policy.

Do not rely only on age.

A young finalization can reference an older shared prefix.

## Secondary index retention

Receipt-ID index entries are secondary.

They can be rebuilt from the committed chain.

Deleting an index is recoverable.

Deleting the referenced immutable receipt node is not.

Therefore:

- node retention is authoritative;
- index retention is an optimization.

## Backup guidance

Back up together when possible:

- finalization store;
- recovery checkpoint store;
- session evidence store;
- decision-journal nodes/head;
- receipt nodes/head/index;
- audit anchors;
- witnesses;
- signed execution evidence.

A backup that captures a newer finalization record but omits its referenced historical nodes is inconsistent.

Prefer snapshot mechanisms with cross-key consistency.

When unavailable, restore conservatively and run durable verification on every retained finalization.

## Restore validation

After restore:

1. verify current decision journal;
2. verify current receipt chain;
3. verify audit anchor chain;
4. verify witness chain;
5. verify signed execution evidence chain;
6. enumerate retained finalizations;
7. run durable recovery verifier for each COMPLETE finalization;
8. quarantine any MANUAL_REVIEW result;
9. report INCOMPLETE results for controlled repair.

## Root mismatch interpretation

A checkpoint root that differs from the current root is normal after later work.

A checkpoint root is invalid when:

- it cannot be reconstructed;
- its prefix hash fails;
- it is not an ancestor of current committed head.

Do not classify ordinary root advancement as corruption.

## Orphan interpretation

An orphan immutable node is normal after a lost CAS race.

It is not part of committed history.

An orphan becomes a problem only if another durable record incorrectly references it as authoritative.

Historical recovery rejects such references because `root_is_ancestor` fails.

## Duplicate identifier interpretation

### Duplicate event hashes

Identical event hashes imply identical hashed event content.

A key collision with different content is corruption.

### Duplicate receipt IDs

Receipt IDs are stronger logical identities.

One receipt ID must correspond to one receipt.

Two committed receipts with the same ID are corruption/conflict even if both nodes hash correctly.

## Correlation ID checks

Session inclusion verifies receipt correlation IDs.

This prevents a receipt from another execution from being substituted merely because:

- command fingerprint matches;
- return code matches;
- receipt ID was copied into a report.

## Attempt-number checks

Retry attempt numbers are verified in order.

For a step with two receipts:

- first receipt must have attempt = 1;
- second receipt must have attempt = 2.

This prevents reordering or mixing retry receipts.

## Return-code checks

The session manifest captures return codes.

Inclusion verifies them against committed receipts.

A substituted return code invalidates the session proof.

## Fingerprint checks

Receipt command fingerprints are part of the inclusion proof.

A receipt ID pointing to another command fingerprint is rejected.

## Decision event checks

A projected session decision event must match:

- exact global sequence;
- exact event hash;
- exact kind;
- exact proposal ID;
- exact session ID.

The verifier does not trust the projection alone.

## Empty session journal

By default, finalization requires at least one session journal event.

This is fail closed.

The integrity verifier has an explicit `require_session_journal=False` mode for controlled compatibility cases.

Production finalization should keep the default.

## Session with zero receipts

A session can have a step with zero receipts if the step never dispatched.

Examples:

- dependency prevented execution;
- prior step failed and plan policy stopped;
- admission failed before process launch.

The session evidence still records the step.

Receipt inclusion has nothing to prove for that step.

## Failed child processes

A failed child can still have complete durable evidence.

Expected state:

- execution attempt FAILED;
- receipt records failure;
- session phase FAILED;
- recovery checkpoint captures FAILED;
- inclusion proof remains valid;
- finalization can reach COMPLETE;
- signed execution evidence records attempt state = failed.

COMPLETE means evidence finalization completed.

It does not mean the child command succeeded.

## Service degradation semantics

Evidence finalization failure after terminal execution causes service degradation.

Reason:

- the process result already exists;
- accepting new work can increase ambiguity;
- evidence repair should finish before additional execution pressure.

The degraded service can be restored only after operators or recovery logic establish a consistent durable state.

## Idempotency model

Idempotency exists at several layers.

### Receipt append

Same receipt ID and same content returns existing committed receipt.

Same receipt ID and different content fails.

### Recovery checkpoint

Same finalization ID and same checkpoint returns existing record.

Different checkpoint fails.

### Audit anchor

Same finalization ID and same bindings returns existing anchor.

Different bindings fail.

### Witness

Same audit root/trust/release returns existing canonical witness.

### Signed evidence

Same execution attempt and same evidence returns existing bundle.

Same attempt and different final evidence fails.

### Finalization phase

Retry at same phase with same evidence is no-op.

Retry at same phase with different evidence fails.

## Exactly-once statement

The architecture does not claim exactly-once external side effects.

It provides:

- single-use authority where possible;
- durable execution-attempt identity;
- idempotent evidence commits;
- CAS/fenced coordination;
- terminal receipts;
- restart verification.

External systems can still receive side effects before a crash.

Recovery must not infer that missing finalization evidence means the side effect did not happen.

## Performance considerations

### Append complexity

Normal journal append:

- one head read;
- one immutable-node write;
- one head CAS.

Normal receipt append adds:

- receipt-ID index read;
- immutable-node write;
- head CAS;
- index write.

### Recovery lookup

Normal receipt lookup is index-based.

Index repair requires committed-chain scan.

Historical verification walks the prefix from historical root to genesis.

### Long chains

Historical prefix verification is O(prefix length).

For very large deployments, consider:

- checkpointed Merkle structures;
- periodic signed roots;
- segmented chains;
- retention epochs.

Any optimization must preserve ancestor proof.

## Segmentation guidance

If chains are segmented in the future:

- segment root must commit previous segment root;
- finalization must identify segment and root;
- recovery must verify segment ancestry;
- receipt IDs must remain globally unique or namespace-scoped;
- compaction must preserve retained finalization dependencies.

## Monitoring

Track at least:

- journal append CAS retries;
- receipt append CAS retries;
- orphan node count if observable;
- receipt index repairs;
- duplicate receipt-ID conflicts;
- finalization phase lag;
- incomplete finalizations;
- manual-review finalizations;
- historical-root verification failures;
- signed-evidence verification failures;
- recovery verification latency.

## Alerting

Alert immediately on:

- chain corruption;
- content-address collision;
- duplicate committed receipt ID;
- finalization digest conflict;
- recovery checkpoint conflict at same transition count;
- signed evidence conflict for same attempt;
- historical root not ancestor;
- signature verification failure.

Alert with lower urgency on:

- missing receipt index repaired successfully;
- transient CAS retries;
- incomplete finalization after known worker restart.

## Diagnostics payload

An operator diagnostic should include:

- finalization ID;
- session ID;
- execution attempt ID;
- finalization phase;
- finalization revision;
- checkpoint digest;
- checkpoint revision;
- journal historical root;
- current journal root;
- receipt historical root;
- current receipt root;
- session integrity digest;
- signed execution evidence digest;
- finding codes;
- recovery status.

Avoid logging:

- resolved secrets;
- raw environment values;
- full sensitive command output.

## Incident: historical root is missing

Symptoms:

- `snapshot_at` fails;
- durable recovery returns MANUAL_REVIEW;
- current chain may still verify.

Possible causes:

- incorrect compaction;
- partial restore;
- storage deletion;
- wrong namespace;
- backend corruption.

Response:

1. stop evidence-dependent automation;
2. confirm namespace configuration;
3. inspect backup inventory;
4. locate missing immutable node by hash;
5. restore without rewriting unrelated nodes;
6. rerun root verification;
7. rerun durable session verification.

## Incident: historical root is not an ancestor

Symptoms:

- historical prefix verifies;
- `verify_root` succeeds;
- `root_is_ancestor` fails.

Likely cause:

- record references an orphan CAS candidate;
- wrong chain/namespace;
- head history was rewritten incorrectly.

Response:

- treat as manual review;
- do not bless the orphan;
- compare finalization timestamps and writer logs;
- identify the committed sibling branch;
- preserve both immutable candidates for investigation.

## Incident: duplicate receipt ID

Symptoms:

- index repair sees multiple committed matches;
- inclusion fails.

Possible causes:

- receipt ID generation defect;
- manual data mutation;
- incompatible writer implementation;
- legacy migration duplication.

Response:

- stop automatic recovery for affected session;
- identify both receipt hashes;
- inspect command fingerprints and correlation IDs;
- determine whether one is invalid;
- do not silently delete one without an audited repair procedure.

## Incident: integrity digest mismatch

Symptoms:

- recovery checkpoint digest differs from reconstructed integrity;
- signed execution evidence may also differ.

Response:

- classify as conflict;
- compare:
  - journal root;
  - receipt root;
  - journal manifest;
  - receipt manifest;
- find the first divergent inclusion row;
- preserve all signed artifacts;
- do not regenerate signatures over substituted evidence.

## Incident: signed execution evidence missing

If the finalization requires signed evidence but none exists:

- status is INCOMPLETE if no conflicting evidence is found;
- resume signing/finalization using already committed checkpoint and anchor;
- never rerun the child merely to regenerate signed evidence.

## Incident: signed execution evidence conflicts

If the same execution attempt binds different final evidence:

- status is MANUAL_REVIEW;
- automatic recovery stops;
- inspect attempt authority, checkpoint, provenance, trust epoch, and release evidence.

## Migration from in-memory journal

A safe migration strategy is:

1. deploy distributed journal support;
2. keep one writer while validating behavior;
3. configure orchestrator with `DistributedAIDecisionJournal`;
4. verify new sessions use distributed roots;
5. do not fabricate durable history for old sessions unless an explicit migration procedure preserves hashes;
6. mark pre-migration sessions as legacy evidence if needed.

Because event sequence and previous root are hashed, arbitrary import into the middle of a live chain changes hashes.

## Migration from in-memory receipts

For new sessions:

- configure `ShellExecutor.receipt_chain` with `DistributedReceiptChain`;
- pass the same chain to `ShellService`.

For old receipts:

- avoid re-hashing them into a new chain and pretending roots are unchanged;
- if migration is required, create a separately identified legacy segment or migration artifact.

## Compatibility path

The legacy Python import path remains supported:

```python
from skeleton.shells.durable_receipts import DistributedReceiptChain
```

The canonical implementation path is:

```python
from skeleton.shells.distributed_receipts import DistributedReceiptChain
```

Both names reference the same class.

## Recommended construction

A multi-worker deployment should construct shared durable components from the same backend family.

Illustrative shape:

```python
backend = durable_backend

journal = DistributedAIDecisionJournal(
    backend,
    namespace="prod-ai-decisions",
)

receipts = DistributedReceiptChain(
    backend,
    namespace="prod-shell-receipts",
)

executor = ShellExecutor(
    runner,
    receipts=receipts,
)

shell_service = ShellService(
    executor,
    receipts=receipts,
)

orchestrator = AIShellOrchestrator(
    ...,
    shell_service=shell_service,
    journal=journal,
)
```

Use deployment-specific stable namespaces.

## Recommended finalizer construction

Illustrative shape:

```python
finalizer = AIExecutionEvidenceFinalizer(
    journal=journal,
    receipt_chain=receipts,
    session_evidence=session_evidence_store,
    audit_anchors=audit_anchor_store,
    audit_witnesses=witness_store,
    execution_evidence=signed_evidence_store,
    finalizations=finalization_store,
    recovery_checkpoints=recovery_store,
)
```

The finalizer creates its integrity verifier from the supplied chains unless one is explicitly provided.

## Recommended restart verification

Illustrative shape:

```python
verifier = DurableSessionRecoveryVerifier(
    finalizations=finalization_store,
    recovery_checkpoints=recovery_store,
    session_evidence=session_evidence_store,
    journal=journal,
    receipt_chain=receipts,
    execution_evidence=signed_evidence_store,
)

report = verifier.verify(finalization_id)
```

Interpret status, not just exceptions.

## Public API surfaces

Durable journal APIs:

- `append`;
- `snapshot`;
- `snapshot_at`;
- `verify`;
- `verify_root`;
- `root_is_ancestor`;
- `root_hash`;
- `length`;
- `events_for_session`;
- `require_root`.

Durable receipt APIs:

- `append`;
- `snapshot`;
- `snapshot_at`;
- `verify`;
- `verify_root`;
- `root_is_ancestor`;
- `root_hash`;
- `length`;
- `find_by_receipt_id`;
- `require_receipt`;
- `require_receipts`;
- `require_root`.

Session integrity APIs:

- `verify`;
- `require`.

Durable recovery APIs:

- `verify`;
- `require_verified`.

## Testing strategy

Durability tests intentionally include more than normal unit cases.

They simulate:

- concurrent head races;
- orphan immutable writes;
- missing secondary index;
- index repair;
- fresh process readers;
- wrong backend value types;
- node tampering;
- missing nodes;
- historical corruption;
- historical ancestry;
- duplicate receipt IDs;
- substituted session manifests;
- substituted recovery checkpoints;
- missing signed evidence;
- conflicting signed evidence;
- real child process execution.

## Canonical regression files

Important regression files include:

- `test_shell_ai_distributed_journal.py`;
- `test_shell_ai_distributed_receipts.py`;
- `test_shell_ai_session_integrity.py`;
- `test_shell_ai_durable_chain_integration.py`;
- `test_shell_ai_durable_public_api.py`;
- `test_shell_ai_finalization_state.py`;
- `test_shell_ai_finalization_reconciler.py`;
- `test_shell_ai_recovery_store.py`;
- `test_shell_ai_restart_finalization.py`;
- `test_shell_ai_service_finalization.py`.

All match the canonical `test_shell_*.py` quality-gate pattern.

## Test invariant: competing journal writers

The journal race regression proves:

- writer A prepares sequence N;
- writer B commits sequence N first;
- writer A loses CAS;
- writer A retries as sequence N+1;
- writer A's old sequence-N candidate remains unreachable;
- committed chain verifies.

## Test invariant: competing receipt writers

The receipt race regression proves the same property for execution receipts.

It also verifies the receipt-ID index follows the committed node.

## Test invariant: index repair

The index-repair regression proves:

- receipt is committed;
- index is removed to simulate crash;
- fresh reader scans committed chain;
- index is rebuilt;
- retrying append returns existing receipt;
- chain length does not grow.

## Test invariant: historical root stability

Historical-root tests prove:

- old root verifies after later appends;
- old root remains ancestor;
- old prefix excludes later work;
- corruption of an old prefix is detected;
- orphan prefix is rejected as non-ancestor.

## Test invariant: end-to-end restart

The integration suite executes a real bounded Python child.

It then:

- finalizes the execution;
- records integrity digest;
- executes unrelated later session;
- creates fresh durable-chain readers;
- reconstructs first session at historical roots;
- obtains the same integrity digest;
- verifies full durable recovery report.

## Test invariant: failed child

A real failed child is also finalized.

The test proves:

- receipt exists;
- attempt state is failed;
- integrity proof succeeds;
- checkpoint is durable;
- signed evidence can be complete;
- evidence completion is independent from child success.

## Test invariant: destructive corruption

Destructive tests modify durable backend values after commit.

Expected result:

- chain verification fails or binding conflicts;
- durable recovery returns MANUAL_REVIEW;
- automated recovery does not rewrite the contradiction.

## Security properties

The durable evidence layer provides:

- tamper evidence through hashes;
- signed final evidence where configured;
- exact historical inclusion proof;
- conflict detection;
- CAS ordering;
- ancestry validation;
- rollback resistance for session checkpoint heads;
- replay-safe finalization append semantics.

It does not provide confidentiality.

Sensitive payload policy must be enforced before data enters durable evidence.

## Privacy and redaction

Decision journal summaries should remain bounded and non-secret.

Receipt metadata should avoid resolved secrets.

Command output is represented by byte counts and other bounded metadata in receipts; raw output handling remains governed by output policy.

Audit export should continue using redaction allowlists.

## Key management

Signed artifact HMAC keys must be:

- managed separately from evidence data;
- rotated through an explicit process;
- available for verification according to retention requirements;
- protected from ordinary application logs.

A key rotation must not make retained signed evidence unverifiable without a documented key-history strategy.

## Release binding

Finalized execution can bind release evidence.

Recovery checks release digest consistency between:

- finalization;
- recovery checkpoint;
- signed execution evidence.

Release drift does not mutate old evidence.

Old evidence remains bound to the release that authorized it.

## Runtime trust binding

Runtime trust is similarly immutable for one finalization.

A later runtime trust epoch does not rewrite prior evidence.

Recovery verifies the original trust digest.

## Sandbox binding

When a verified sandbox backend is used, the sandbox binding digest enters provenance and recovery evidence.

The durable chain does not itself enforce sandboxing.

It records the sandbox contract/binding used by the execution path.

## Model attestation

Signed execution evidence can bind a model attestation digest.

Model attestation is advisory for model identity and compatibility.

It does not replace deterministic shell authority.

## Quorum approval

Where quorum approval is required, its digest can be bound into signed execution evidence.

Recovery verifies signed bundle consistency but does not recreate missing human votes.

## Execution seals

A seal is single-use authority.

Durable evidence may reference the seal ID.

Evidence recovery must not consume a new seal merely to complete evidence.

## Execution attempt identity

The execution attempt is the key cross-crash identity for terminal process work.

The finalization binds:

- attempt ID;
- attempt authority digest;
- terminal state.

A completed session requires a successful terminal attempt.

A failed session requires a failed terminal attempt.

## Service readiness after recovery

A degraded service should return to normal admission only after:

- required evidence finalization completes;
- durable recovery verification returns VERIFIED;
- other service diagnostics pass.

The durable verifier alone does not mutate service phase.

## Operational checklist: before enabling distributed mode

- Choose a durable backend.
- Verify CAS semantics.
- Set stable namespaces.
- Configure shared journal.
- Configure shared receipt chain.
- Configure shared session evidence store.
- Configure shared recovery store.
- Configure shared finalization store.
- Configure shared attempt store.
- Configure audit stores.
- Configure signing keys.
- Run real-process integration tests.
- Run concurrency tests.
- Run restart tests.
- Run restore tests.
- Confirm retention policy preserves historical prefixes.

## Operational checklist: worker start

- Verify backend connectivity.
- Verify current decision journal.
- Verify current receipt chain.
- Verify audit chains.
- Verify active release.
- Verify runtime trust.
- Verify service diagnostics.
- Inspect incomplete finalizations.
- Resume only evidence work for terminal attempts.
- Reject ambiguous manual-review cases.

## Operational checklist: worker shutdown

- Stop new admission.
- Drain active execution.
- Record terminal attempts.
- Finish finalization where possible.
- Persist service diagnostics.
- Do not delete orphan immutable nodes during shutdown.
- Leave repair to retention/maintenance logic.

## Operational checklist: incident response

- Record finalization ID.
- Record session ID.
- Record attempt ID.
- Record current journal root.
- Record checkpoint journal root.
- Record current receipt root.
- Record checkpoint receipt root.
- Run durable verifier.
- Save finding codes.
- Preserve conflicting records.
- Disable automated replay.
- Escalate MANUAL_REVIEW.

## Finding-code interpretation

Finding codes are designed for machines and operators.

Examples:

- `finalization.missing`;
- `recovery.missing`;
- `recovery.digest_conflict`;
- `recovery.session_conflict`;
- `recovery.runtime_trust_conflict`;
- `recovery.release_conflict`;
- `recovery.attempt_conflict`;
- `session_evidence.missing`;
- `session_evidence.finalization_conflict`;
- `session_evidence.recovery_conflict`;
- `session_journal.digest_conflict`;
- `session_journal.corruption`;
- `session_integrity.failed`;
- `session_integrity.digest_conflict`;
- `signed_evidence.store_missing`;
- `signed_evidence.missing`;
- `signed_evidence.chain_corruption`;
- `signed_evidence.finalization_digest`;
- `signed_evidence.session`;
- `signed_evidence.provenance`;
- `signed_evidence.checkpoint`;
- `signed_evidence.session_evidence`;
- `signed_evidence.session_journal`;
- `signed_evidence.session_integrity`;
- `signed_evidence.runtime_trust`;
- `signed_evidence.release`;
- `signed_evidence.attempt`;
- `signed_evidence.attempt_authority`;
- `signed_evidence.chain_node`.

## Missing versus conflict

Missing means the expected artifact is absent.

Conflict means two present artifacts disagree.

Examples:

- missing recovery checkpoint: INCOMPLETE;
- recovery checkpoint digest differs: MANUAL_REVIEW;
- missing signed bundle: INCOMPLETE;
- signed bundle references another checkpoint: MANUAL_REVIEW.

This distinction should remain stable.

## Why absence can be resumable

A crash can happen before a write.

Absence alone does not prove tampering.

If the terminal execution evidence and authority bindings remain consistent, missing post-execution evidence can often be written idempotently.

## Why conflict is not auto-repaired

A conflict means at least two durable claims disagree.

Choosing one automatically would erase evidence of the disagreement.

Therefore conflicts are escalated.

## Recovery report digest

The durable recovery report has its own deterministic digest.

This digest can be used for:

- diagnostics;
- incident attachments;
- external monitoring;
- operator approvals.

It is not itself execution authority.

## Future extensions

Potential future improvements include:

- segmented historical chains;
- Merkle inclusion proofs;
- durable index compaction;
- public-key signing for external audit;
- multi-region replicated CAS backend;
- explicit evidence retention epochs;
- signed recovery reports;
- operator repair transactions;
- evidence export bundles;
- offline verifier tooling.

Any extension must preserve:

- exact historical identity;
- ancestor proof;
- no silent authority widening;
- conflict visibility.

## Design summary

The durable evidence system intentionally makes one distinction repeatedly:

> committed history is not the same thing as all data ever written.

CAS losers can leave data.

Crashes can leave partial data.

Later sessions can advance roots.

Indexes can disappear.

What matters is whether a finalization can prove its claims against a committed historical lineage.

The durable journal provides lineage for decisions.

The durable receipt chain provides lineage for process outcomes.

The session integrity report proves exact inclusion.

The recovery checkpoint fixes the historical roots and authority bindings.

The signed execution bundle commits the final proof.

The durable recovery verifier reconstructs the proof from storage after restart.

If required data is merely absent, recovery can remain resumable.

If durable claims conflict or historical lineage is corrupted, automation stops for manual review.
