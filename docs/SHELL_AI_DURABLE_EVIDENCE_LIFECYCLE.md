# Shell AI Durable Evidence Lifecycle

## Purpose

The AI shell execution plane produces more than child-process output.

A terminal execution can create or bind all of the following:

- a model planning decision,
- a reviewed proposal,
- a deterministic compiled plan,
- a short-lived execution seal,
- an execution-attempt authority record,
- one or more shell execution receipts,
- a session-scoped decision-journal manifest,
- a session execution-evidence record,
- a recovery checkpoint,
- an audit anchor,
- an audit witness,
- signed execution evidence,
- a durable finalization record,
- runtime-trust and release bindings,
- and operator recovery requirements.

Those records have different lifetimes and different authority.

This document defines how they are retained, checkpointed, archived, verified,
and surfaced to the long-lived AI shell service.

The central rule is:

> Preserve recovery authority before optimizing hot-storage footprint.

The lifecycle implemented here is intentionally non-destructive.

It can:

1. inspect durable-chain pressure,
2. publish signed checkpoints,
3. identify an eligible historical prefix,
4. persist real historical node payloads,
5. verify redundant archive replicas,
6. reconstruct historical roots after live-chain growth,
7. prove non-destructive compaction readiness,
8. sign an expiring readiness certificate,
9. and gate new AI shell work on current lifecycle health.

It cannot delete live chain nodes.

There is no deletion executor in this architecture.

A readiness report or certificate is not deletion authority.

---

## Security invariants

The durable lifecycle is built around the following invariants.

### Models never control evidence retention authority

A model can propose shell actions.

A model cannot:

- publish a durable-chain checkpoint,
- select an archival checkpoint,
- sign an archive manifest,
- modify the archive repository,
- issue a compaction-readiness certificate,
- change lifecycle policy,
- remove protected roots,
- or delete historical evidence.

All lifecycle decisions are deterministic host decisions.

### Archive metadata is not enough

A signed archive manifest describes a committed prefix.

That does not by itself preserve recovery.

The archive repository therefore stores the actual canonical node payloads for
supported durable chains.

Currently supported portable archived node types are:

- AI decision journal events,
- shell execution receipts,
- generic content-addressed evidence nodes.

Every restored node is revalidated against its native hash function.

### Historical roots remain first-class recovery objects

A finalized execution binds exact historical roots.

Later work is allowed to advance the live decision journal and receipt chain.

Recovery must verify the historical roots captured at finalization, not demand
that those roots remain the current global heads.

The live durable chains therefore support:

- `snapshot_at(root)`,
- `verify_root(root)`,
- `root_is_ancestor(root)`.

The archive repository supports equivalent historical reconstruction.

The archive-backed historical reader tries the live chain first and then falls
back to signed archived payloads.

### Archive replicas are redundant records, not duplicate authority

A later archive may contain historical roots already represented by an earlier
archive.

Each root index may therefore contain multiple archive replicas.

The first archive remains the primary replica for stable identity.

Later archives are appended as fallback replicas.

If the primary archive record is lost or corrupted, historical reconstruction
can use a later verified replica.

Content-addressed nodes are shared across archive replicas.

Therefore:

- losing one archive record can be survivable,
- losing one root index can be repaired,
- losing an archive head can be repaired,
- but corrupting a shared content-addressed node invalidates every archive
  replica that depends on that node.

That distinction is intentional.

### Checkpoints are canonical authority

An archive is admitted only when its signed checkpoint is uniquely present in
the canonical durable checkpoint registry.

The archive repository verifies:

- checkpoint registry integrity,
- checkpoint chain identity,
- checkpoint sequence,
- checkpoint root,
- manifest checkpoint digest,
- manifest signature,
- archive-record digest,
- every manifest entry,
- every stored node,
- and reconstructed prefix continuity.

A foreign or substituted checkpoint cannot authorize an archive.

### Compaction readiness is explicitly non-destructive

`DurableCompactionReadiness.destructive_action_authorized` always returns
`False`.

`SignedDurableCompactionCertificate.destructive_action_authorized` always
returns `False`.

The signed certificate metadata contains:

`authority = non-destructive-compaction-readiness`

No readiness object is accepted as delete authority.

### The service never performs lifecycle mutation automatically

The long-lived `AIShellService` may be configured with a durable lifecycle
coordinator.

The service only calls lifecycle inspection.

It does not call lifecycle `prepare()`.

Therefore startup and admission can fail closed on:

- checkpoint pressure,
- archive requirements,
- invalid archive coverage,
- compaction-readiness drift,
- or protected-root gaps,

without silently changing durable evidence state.

Publishing checkpoints and archives remains an explicit operator workflow.

---

## Durable chain layers

The execution plane currently uses several durable structures.

### Decision journal

`DistributedAIDecisionJournal` is a CAS-backed global decision journal.

Properties:

- immutable content-addressed events,
- mutable CAS head,
- contiguous sequence verification,
- historical prefix verification,
- session filtering,
- multi-writer serialization,
- tolerated unreachable orphan candidates after lost CAS races.

A journal event is committed only if reachable from the current canonical head.

An internally valid orphan event is not treated as a committed historical root.

### Receipt chain

`DistributedReceiptChain` is a CAS-backed global execution-receipt chain.

Properties:

- immutable content-addressed chained receipts,
- CAS head,
- receipt-ID index,
- historical prefix verification,
- fresh-reader recovery,
- post-head-CAS index self-healing,
- duplicate receipt-ID conflict detection.

Receipt-ID indexing is secondary.

The committed chain remains authoritative.

If a process crashes after head CAS but before receipt-ID index insertion, a
fresh reader reconstructs the missing index from the committed chain before
allowing another append.

### Session integrity proof

`SessionEvidenceIntegrityVerifier` proves that session-scoped evidence is
actually represented in the global durable chains.

For journal events it checks:

- global sequence,
- event hash,
- event kind,
- proposal ID,
- session ID.

For receipts it checks:

- receipt ID,
- receipt fingerprint,
- correlation ID,
- attempt number,
- return code,
- chain inclusion.

The resulting integrity digest is bound into:

- the recovery checkpoint,
- and the signed execution-evidence bundle.

This prevents a globally valid chain from being mistaken for the correct
session-specific evidence.

---

## Finalization and restart semantics

A terminal child process and terminal evidence finalization are separate
durability domains.

A child can finish while evidence finalization is still incomplete.

The finalization state machine therefore records monotonic phases:

1. STARTED
2. SESSION_EVIDENCE
3. CHECKPOINTED
4. ANCHORED
5. WITNESSED
6. SIGNED
7. COMPLETE

Finalization records bind required durability layers.

A deployment can explicitly require:

- persisted recovery checkpoint,
- audit witness,
- signed execution evidence.

A COMPLETE finalization cannot silently mean different things on different
workers.

### Restart-idempotent writes

Finalization uses stable execution/finalization identities to make terminal
evidence restart-safe.

Important idempotent operations include:

- audit-anchor append by finalization ID,
- audit-witness publication by historical audit root,
- signed execution-evidence append by execution attempt,
- recovery-checkpoint put by finalization ID,
- finalization state phase advance by CAS.

A crash after an append but before local acknowledgement must not create a
second canonical evidence item on retry.

### Historical audit roots

An audit witness is historical evidence.

After later sessions publish newer witnesses, retrying an older finalization
must verify its original canonical witness at its original sequence.

It must not demand that the old root remain the current global witness head.

---

## End-to-end durable recovery

`DurableSessionRecoveryVerifier` begins with a finalization ID and verifies the
durable execution across storage layers.

The verification path is:

1. load finalization state,
2. load recovery checkpoint,
3. verify finalization/checkpoint identity,
4. load durable session execution evidence,
5. reconstruct the session journal at the checkpoint's historical journal root,
6. reconstruct receipts at the checkpoint's historical receipt root,
7. recompute session-integrity proof,
8. verify integrity digest against recovery checkpoint,
9. locate signed execution evidence,
10. verify signed evidence chain,
11. compare signed evidence against:
    - finalization,
    - recovery checkpoint,
    - session evidence,
    - session journal,
    - integrity digest,
    - runtime trust,
    - release evidence,
    - execution attempt,
    - execution-attempt authority.

Recovery statuses are:

- VERIFIED,
- INCOMPLETE,
- MANUAL_REVIEW.

### INCOMPLETE

Missing work that can plausibly result from an interrupted finalization is
classified as incomplete.

Examples:

- missing recovery checkpoint,
- missing session execution evidence,
- missing required signed execution evidence.

Incomplete work may be resumable.

### MANUAL_REVIEW

Conflicting or corrupted durable evidence is not automatically repaired.

Examples:

- checkpoint digest substitution,
- session-evidence substitution,
- historical journal corruption,
- receipt corruption,
- signed-evidence provenance mismatch,
- signed-evidence attempt mismatch,
- runtime-trust mismatch,
- release mismatch.

These conditions require manual review.

---

## Durable recovery health gate

`DurableRecoveryHealthGuard` evaluates one or more required finalization IDs.

Typical policy controls include:

- require non-empty required set,
- minimum verified count,
- maximum incomplete count,
- maximum tracked finalizations.

The health gate is suitable for long-lived service admission.

It does not mutate finalization state.

---

## Signed recovery requirements

Static configuration of required finalization IDs is not sufficient for a
long-running distributed service.

The recovery requirement subsystem therefore supports signed durable manifests
that define the currently required recovery set for an operator scope.

A requirement manifest can be updated only through the requirement store and
operator workflow.

Retiring a required finalization should require verified recovery evidence.

This prevents a worker from making a recovery problem disappear by simply
dropping the ID from local configuration.

---

## Durable checkpoints

`DurableChainCheckpointStore` creates signed checkpoints of committed durable
chain heads.

A checkpoint includes:

- chain ID,
- sequence,
- root hash,
- previous checkpoint digest,
- observed time.

Checkpoints themselves are stored in an append-only evidence chain.

A checkpoint can remain valid after the live chain grows.

A checkpoint does not automatically mean that an archive should be created.

It establishes a signed historical authority that retention may later select.

---

## Retention planning

`DurableRetentionPlanner` is non-destructive.

It evaluates chain pressure and existing signed checkpoints.

Common states include:

- healthy,
- checkpoint required,
- archive candidate / archive recommended,
- warning,
- critical capacity.

The planner preserves protected historical roots.

The retention plan contains:

- current sequence/root,
- capacity and utilization,
- chosen checkpoint,
- archive-through sequence/root,
- live tail,
- protected roots,
- deterministic plan digest.

Retention planning does not delete anything.

Historically, the retention plan exposed `local_deletion_safe=False`.

That remains the intended architecture.

---

## Why checkpoint priming is two-stage

When a chain is under pressure but has no suitable older checkpoint, the
correct first action is to checkpoint the current head.

That checkpoint cannot immediately create a useful hot/cold split because the
live tail is zero.

Later chain growth creates a tail after the checkpoint.

At that point the older signed checkpoint can become an eligible archive
boundary.

The lifecycle therefore behaves like:

1. pressure detected,
2. current head checkpointed,
3. more events arrive,
4. retention selects old checkpoint,
5. prefix becomes archive candidate,
6. archive is persisted,
7. archive coverage is verified,
8. compaction readiness can become true.

This avoids inventing a retention boundary that was never signed.

---

## Portable archive repository

`DurableArchiveRepository` stores actual historical payloads.

An archive record contains:

- signed archive manifest,
- signed canonical checkpoint,
- ordered node hashes,
- store timestamp,
- archive-record digest.

The archive-record digest protects repository metadata that is not part of the
archive manifest itself.

### Node encoding

Supported node types are serialized canonically.

#### AI decision event

Restoration re-runs the decision-journal hash over:

- previous hash,
- sequence,
- kind,
- observed time,
- session ID,
- intent ID,
- proposal ID,
- summary,
- data.

#### Execution receipt

Restoration re-runs the receipt-chain hash over:

- previous hash,
- sequence,
- reconstructed execution receipt.

The reconstructed receipt retains:

- command,
- correlation ID,
- fingerprint,
- timestamps,
- duration,
- return code,
- status flags,
- byte counts,
- attempt,
- receipt ID,
- metadata.

#### Generic evidence node

Restoration re-runs the generic content-addressed evidence-node digest over:

- previous hash,
- sequence,
- kind,
- payload.

### Every prefix root is indexed

An archive checkpoint can contain many historical prefix roots.

The repository indexes every root in the archived prefix.

That lets a finalized execution recover a historical root that predates the
archive's terminal checkpoint root.

---

## Archive replica model

A root index contains:

- chain ID,
- root hash,
- sequence,
- primary archive ID,
- primary manifest digest,
- ordered archive replicas.

When later archives include the same historical root, they are added as
replicas.

### Replica resolution

Historical reconstruction resolves replicas in order.

A replica must pass:

1. archive record lookup,
2. archive-record digest,
3. manifest signature,
4. canonical checkpoint authority,
5. archive manifest verification,
6. node reconstruction,
7. terminal-root equality.

The first verified replica is used.

### Primary archive record loss

If the primary archive record disappears but a later replica contains the same
root, reconstruction can continue through the later replica.

### Primary archive-record tamper

A bad archive record digest invalidates that replica.

The resolver can continue to a later replica.

### Shared node corruption

Archived nodes are content-addressed and intentionally deduplicated.

If two archives refer to the same node hash, they share the canonical stored
node.

Corrupting that shared node invalidates all replicas that depend on it.

Archive replicas are therefore not independent physical node copies.

If independent physical-copy fault domains are required, the backend should
replicate the content-addressed object storage itself.

---

## Archive crash recovery

The archive repository is designed for restart repair.

Possible crash windows include:

### Nodes written, archive record missing

Retry verifies the existing immutable nodes and writes the missing archive
record.

### Archive record written, root indexes missing

The archive record can be verified directly from stored node hashes without
using root indexes.

Retry or `repair_indexes()` recreates missing root indexes.

### Archive head missing

The latest archive head is repairable from a verified archive.

### Root index present, archive missing

Historical resolution rejects the missing replica and can try another replica.

### Same archive retried with different process clock

The first immutable archive record remains canonical.

A retry reuses it instead of treating a different local store timestamp as a
new archive payload.

---

## Archive-backed historical reader

`ArchiveBackedHistoricalChain` wraps:

- a live durable chain,
- one archive repository,
- one chain ID.

Current operations still come from the live chain.

Historical operations work as follows:

### snapshot_at(root)

1. try the live chain,
2. if unavailable, resolve the root from archive replicas,
3. reconstruct and verify the archived prefix,
4. return the historical nodes.

### verify_root(root)

1. try live historical verification,
2. otherwise verify archived reconstruction.

### root_is_ancestor(root)

1. use live committed ancestry when available,
2. otherwise require verified archive coverage.

The archive reader is designed to preserve recovery after future hot-store
compaction.

It does not perform that compaction itself.

---

## Archive-backed finalization recovery

`DurableSessionRecoveryVerifier` can be configured with:

- journal archive repository + journal chain ID,
- receipt archive repository + receipt chain ID.

When configured, it wraps the live chains in archive-backed historical readers.

This allows old finalizations to remain verifiable after live-chain historical
reads are intentionally unavailable.

Tests exercise a "forgetful" live reader that:

- continues to expose the current live head,
- deliberately refuses selected older roots.

With verified archives, recovery remains VERIFIED.

Without archive fallback, the same condition becomes MANUAL_REVIEW.

---

## Durable compaction readiness

`DurableCompactionPlanner` consumes:

- one retention plan,
- one current live chain,
- one verified archive repository,
- a compaction policy.

It produces `DurableCompactionReadiness`.

Readiness requires, depending on policy:

- current live chain integrity,
- live head consistent with retention plan,
- non-empty archive candidate,
- candidate size within bound,
- minimum live tail preserved,
- verified archive coverage for cutoff root,
- protected-root coverage,
- verified archive replica resolution.

### Protected roots

A protected root at or before the cutoff would be removed by hypothetical
compaction.

By default it therefore requires verified archive coverage.

A protected root after the cutoff remains in the live tail and may be covered
by the live chain.

A policy can explicitly permit live-only coverage for a root that would be
evicted, but this is not the recommended high-assurance configuration.

### Stale retention plan

If the live head changes after the retention plan was created, readiness
normally becomes STALE_RETENTION_PLAN.

This fences time-of-check/time-of-use drift.

A policy can disable exact current-head matching, but archive and cutoff
verification still apply.

---

## Compaction readiness states

Possible states include:

- READY
- NO_ARCHIVE_CANDIDATE
- ARCHIVE_MISSING
- ARCHIVE_INVALID
- STALE_RETENTION_PLAN
- LIVE_TAIL_TOO_SMALL
- PROTECTED_ROOT_GAP
- CHAIN_INVALID

READY means:

> Archive coverage is sufficient for non-destructive compaction readiness.

READY does not mean:

> Delete these nodes.

---

## Signed compaction-readiness certificates

`DurableCompactionCertificateStore` can sign a READY report.

The certificate binds:

- chain ID,
- readiness digest,
- retention-plan digest,
- compaction-policy digest,
- live sequence/root,
- cutoff sequence/root,
- archive ID,
- archive-manifest digest,
- protected-roots digest,
- issue time,
- expiry time.

The certificate metadata explicitly contains:

`authority = non-destructive-compaction-readiness`

### Expiry

Readiness certificates are short lived.

A certificate can be validly signed but expired.

Expired certificates are not allowed for current readiness use.

### Renewal

If the latest matching certificate is still valid, issuance reuses it.

If it is expired, the same readiness state can receive a new certificate with a
new immutable ID and new issue/expiry times.

### Current-use verification

`require_current()` re-runs the compaction planner.

The certificate becomes stale if any bound property changes, including:

- live head,
- retention plan,
- compaction policy,
- cutoff,
- archive resolution,
- archive manifest,
- protected roots.

### Non-destructive authority

The certificate object, signed wrapper, and verification report all expose:

`destructive_action_authorized = False`

A consumer must not reinterpret this certificate as deletion permission.

---

## Durable lifecycle coordinator

`DurableEvidenceLifecycleCoordinator` composes:

- durable checkpoint store,
- retention planner,
- archive manifest builder,
- archive repository,
- compaction planner.

It has two important surfaces.

### inspect()

Read-only.

It never publishes a checkpoint or archive.

### prepare()

Operator mutation surface.

Depending on state and policy it may:

- publish a signed checkpoint,
- persist a verified archive.

It still never deletes hot evidence.

---

## Lifecycle states

### HEALTHY

No lifecycle action is currently required.

### CHECKPOINT_REQUIRED

Chain pressure exists, but there is no suitable historical signed checkpoint.

Operator action can prime the current head.

### CHECKPOINT_PRIMED

The operator explicitly published a checkpoint.

This state documents mutation performed by `prepare()`.

It does not imply immediate archive eligibility.

### ARCHIVE_REQUIRED

Retention selected an older signed checkpoint, but its prefix is not yet
persisted in the archive repository.

### ARCHIVE_STORED

The archive exists, but policy does not require compaction readiness or
readiness is not yet satisfied under a permissive lifecycle policy.

### COMPACTION_READY

Archive persistence and non-destructive compaction readiness both pass.

### BLOCKED

A required lifecycle condition cannot currently be satisfied.

Examples:

- archive corruption,
- archive stored but required readiness fails,
- retention pressure without an actionable safe path,
- checkpoint identity mismatch.

---

## Lifecycle actions

Reports can record:

- NONE
- CHECKPOINT_PUBLISHED
- ARCHIVE_PERSISTED
- ARCHIVE_REUSED

The long-lived service's read-only inspection path reports NONE.

Mutation actions belong to explicit operator calls.

---

## Long-lived service admission

`AIShellService` can optionally be configured with:

- one durable lifecycle coordinator,
- one or more `(chain_id, chain)` pairs,
- protected roots per chain,
- explicit capacities per chain.

### Startup

Startup inspects every configured lifecycle chain.

It does not call `prepare()`.

If any configured lifecycle report is non-operational, service startup fails
closed.

### New session

Lifecycle state is rechecked before a new AI session is created.

### Review

Lifecycle state is rechecked before model planning/review work continues.

### Execution fence

Lifecycle state is rechecked before distributed execution-fence acquisition.

### Seal issuance

Lifecycle state is rechecked before an execution seal is issued.

### Sealed execution

Lifecycle state is rechecked before a seal is consumed or a child is spawned.

### Direct execution

Lifecycle state is rechecked before assurance/execution.

If lifecycle state drifts after startup, the service transitions from READY to
DEGRADED and refuses the operation.

### Status

Service status includes:

- overall lifecycle allowed flag,
- per-chain serialized lifecycle report.

This status is read-only evidence.

---

## Service mutation rule

The service must never do this automatically:

1. detect checkpoint pressure,
2. publish a checkpoint,
3. create an archive,
4. continue execution as if nothing happened.

That would let ordinary admission traffic mutate the durable evidence
governance state.

Instead:

1. service detects pressure,
2. service refuses new work,
3. operator inspects lifecycle,
4. operator explicitly invokes `prepare()`,
5. operator verifies resulting state,
6. service can be restarted or re-evaluated.

This separation is deliberate.

---

## Recommended operator workflow

### Normal state

1. inspect service status,
2. confirm durable lifecycle allowed,
3. allow normal AI shell work.

### Checkpoint pressure

When lifecycle reports CHECKPOINT_REQUIRED:

1. stop admitting new work,
2. inspect live chain integrity,
3. inspect retention report,
4. confirm protected-root set,
5. call lifecycle `prepare()`,
6. verify CHECKPOINT_PRIMED,
7. retain the checkpoint,
8. do not expect immediate archive eligibility.

### Later archive eligibility

After more live events arrive:

1. inspect lifecycle again,
2. confirm ARCHIVE_REQUIRED,
3. verify selected checkpoint sequence/root,
4. call lifecycle `prepare()`,
5. archive builder signs the manifest,
6. archive repository persists payloads,
7. root indexes and replicas are written,
8. archive is verified,
9. compaction readiness is evaluated.

### Compaction ready

When lifecycle reports COMPACTION_READY:

1. confirm archive record is valid,
2. confirm cutoff root resolves,
3. confirm protected roots are covered,
4. confirm live tail satisfies policy,
5. optionally issue a signed readiness certificate,
6. keep hot data unchanged.

There is currently no step 7 that deletes data.

---

## Readiness certificate workflow

1. obtain COMPACTION_READY retention/readiness state,
2. call certificate store `issue()`,
3. persist signed certificate,
4. verify certificate metadata says non-destructive readiness,
5. use `require_current()` before relying on the certificate,
6. if expired, renew,
7. if stale, recompute lifecycle/retention/readiness.

A stale certificate is evidence of a prior readiness state only.

It is not valid for current use.

---

## Archive replica recovery workflow

If a historical root fails from the primary archive:

1. resolve root index,
2. verify primary archive record,
3. if primary is missing/corrupt, try next replica,
4. verify replica manifest signature,
5. verify canonical checkpoint,
6. verify archive-record digest,
7. reconstruct prefix,
8. verify terminal root,
9. continue historical recovery.

If all replicas fail, recovery fails closed.

---

## Archive corruption workflow

If archive verification fails:

1. do not create a replacement by guessing,
2. do not mutate the signed manifest,
3. determine whether another archive replica covers the root,
4. if another replica is valid, continue from it,
5. otherwise classify affected finalized executions for manual review,
6. restore from an independently verified backup if available,
7. only then rebuild repository indexes.

A root index alone cannot repair missing payloads.

---

## Root-index loss workflow

If archive nodes and archive record exist but a root index is missing:

1. verify archive record independently of root indexes,
2. call `repair_indexes(archive_id)`,
3. recreate all prefix-root indexes,
4. verify historical root resolution,
5. verify archive-backed recovery.

This is a supported crash-repair path.

---

## Archive-head loss workflow

The latest archive head is convenience/operational metadata.

If it is lost:

1. select a verified archive,
2. repair indexes/head,
3. confirm monotonic head sequence,
4. do not roll the head back below a newer known archive.

Historical root indexes remain the primary lookup mechanism for recovery.

---

## Failure matrix

| Condition | Expected behavior |
| --- | --- |
| Live chain healthy | Continue |
| Live chain invalid | Block |
| Capacity healthy | Continue |
| Checkpoint pressure | Block admission; operator checkpoint |
| Archive required | Block admission; operator archive |
| Archive missing | Not ready |
| Archive signature bad | Not ready / manual review |
| Archive record digest bad | Not ready / try replica |
| Primary archive missing | Try verified replica |
| All archive replicas missing | Fail closed |
| Shared archived node corrupt | All dependent replicas fail |
| Protected evicted root unarchived | Not ready |
| Live tail below policy | Not ready |
| Retention head stale | Not ready |
| Readiness certificate expired | Reject current use |
| Readiness certificate stale | Reject current use |
| Service lifecycle drift | DEGRADED |
| Service lifecycle inspector outage | Startup FAILED / live admission DEGRADED |
| Recovery evidence conflict | MANUAL_REVIEW |
| Recovery evidence missing | INCOMPLETE |

---

## Backend requirements

The reference implementation uses the versioned-state backend contract.

A production backend should provide:

- linearizable or equivalently strong compare-and-swap for authoritative heads,
- durable put-if-absent,
- durable read-after-write,
- monotonic revisions,
- independent backup/replication for archive object storage,
- operational monitoring,
- bounded latency,
- explicit failure behavior.

The architecture must not silently downgrade to a weak eventually-consistent
store for:

- execution attempts,
- finalization state,
- archive heads,
- checkpoint authority,
- policy authority,
- execution-seal replay protection.

---

## Content-addressed archive storage

Content-addressed archive nodes allow deduplication across archive manifests.

Benefits:

- one canonical payload per node hash,
- lower duplicate storage,
- simple native digest verification,
- later archives can reuse old historical nodes.

Tradeoff:

- archive-manifest redundancy does not imply independent physical payload
  redundancy.

If physical fault-domain redundancy is required, replicate the object store
itself.

---

## Why live deletion is not implemented yet

A naïve prefix deletion breaks the ordinary chain assumption that every node
can be walked back to genesis inside the hot store.

A production compaction executor would need a new explicit hot-chain base
anchor.

That base anchor would need to bind at least:

- evicted prefix sequence,
- evicted prefix root,
- archive repository authority,
- signed archive manifest digest,
- canonical checkpoint digest,
- compaction policy digest,
- protected-root coverage digest,
- operator authorization,
- fencing token,
- execution time,
- post-compaction live-root commitment.

Readers would then need to understand:

- local base anchor,
- hot suffix,
- archived historical prefix.

That protocol does not exist yet.

Therefore deletion is correctly absent.

---

## Requirements before a future destructive executor

Before any hot node can be deleted, implement and verify all of the following.

### Explicit destructive policy

A separate policy object must say deletion is enabled.

Default must be disabled.

### Human/operator authorization

Destructive retention must require explicit operator approval.

A model cannot authorize it.

### Fenced compaction lease

Only one worker can compact one chain generation.

A stale worker must be rejected by fencing token.

### Base-anchor format

The hot chain must have a verifiable base anchor after prefix eviction.

### Archive proof binding

The base anchor must bind the exact archive root and signed authority.

### Protected-root proof

Every protected root affected by deletion must remain reconstructable.

### Crash protocol

Handle crashes:

- before deletion,
- midway through deletion,
- after deletion but before head/base update,
- after base update but before acknowledgement.

### Restart reconciliation

A fresh worker must determine whether compaction:

- never started,
- partially executed,
- completed,
- or requires manual review.

### Rollback / restoration

A tested procedure must restore hot evidence from archive when needed.

### Independent archive durability

Deleting the hot copy should require stronger archive durability than merely
one logical archive manifest.

### Audit event

Compaction must append its own immutable governance evidence.

### Verification tests

At minimum test:

- every crash boundary,
- stale fence,
- concurrent compactor,
- protected root,
- archive loss,
- archive corruption,
- base-anchor tamper,
- restart,
- full restore.

Until those conditions exist, deletion should remain unavailable.

---

## Observability

Recommended metrics include:

### Chain pressure

- current sequence,
- configured capacity,
- utilization,
- retention state,
- live tail,
- candidate prefix size.

### Checkpoints

- checkpoint count,
- latest checkpoint sequence,
- checkpoint verification status,
- checkpoint publication failures.

### Archives

- archive count,
- latest archive sequence,
- archive verification failures,
- node count,
- root-index repair count,
- archive replica count,
- replica fallback count,
- missing archive records,
- native node digest failures.

### Compaction readiness

- readiness state,
- live tail,
- cutoff sequence,
- candidate count,
- protected-root gaps,
- stale plan count.

### Certificates

- current valid certificate,
- certificate age,
- time to expiry,
- renewal count,
- stale-certificate count,
- signature failures.

### Service

- lifecycle allowed,
- per-chain lifecycle state,
- transition to DEGRADED,
- startup lifecycle failures.

---

## Status interpretation

### HEALTHY

No operator action required.

### CHECKPOINT_REQUIRED

Operator should publish a checkpoint.

Do not bypass the gate by increasing capacity without understanding why the
chain is under pressure.

### CHECKPOINT_PRIMED

Checkpoint publication succeeded.

Wait for a meaningful live tail before archival.

### ARCHIVE_REQUIRED

Persist the exact signed prefix.

Do not choose a different root ad hoc.

### ARCHIVE_STORED

Archive exists, but readiness requirements may remain.

Inspect compaction report.

### COMPACTION_READY

Archive/readiness proof is valid.

Hot evidence still remains.

### BLOCKED

Do not admit new work until the underlying condition is understood.

---

## Testing strategy

The durable lifecycle test corpus covers:

### Distributed journal

- empty genesis,
- append hashing,
- fresh readers,
- concurrent writers,
- CAS conflicts,
- orphan candidates,
- corruption,
- historical roots.

### Distributed receipts

- append hashing,
- receipt-ID index,
- duplicate IDs,
- post-CAS index repair,
- concurrent writers,
- corruption,
- historical roots.

### Session integrity

- missing/substituted journal entries,
- missing/substituted receipts,
- correlation mismatch,
- attempt mismatch,
- return-code mismatch,
- historical root verification,
- fresh readers.

### Durable recovery

- complete verification,
- later chain growth,
- missing layers,
- substituted layers,
- historical corruption,
- signed-evidence mismatch,
- manual-review classification.

### Archive repository

- empty/non-empty archives,
- journal/receipt/evidence nodes,
- fresh process,
- retry idempotency,
- record digest,
- root-index repair,
- archive-head repair,
- primary replica loss,
- multi-replica fallback,
- shared-node corruption,
- wrong signer,
- noncanonical checkpoint,
- historical fallback.

### Compaction readiness

- ready state,
- archive missing,
- archive invalid,
- stale plan,
- minimum tail,
- candidate bound,
- protected roots,
- archive replica failover,
- receipt-chain parity,
- non-destructive authority.

### Lifecycle coordinator

- healthy no-op,
- checkpoint priming,
- future archive eligibility,
- archive persistence,
- readiness,
- idempotent inspect,
- policy-disabled mutations,
- archive corruption,
- protected roots,
- receipt chain.

### Service lifecycle gate

- healthy startup,
- ready startup,
- multiple chains,
- checkpoint-required failure,
- archive-required failure,
- no hidden mutations,
- live drift,
- review drift,
- seal drift,
- child-spawn prevention,
- archive tamper,
- status serialization,
- capacity overrides.

### Signed readiness certificate

- issue,
- current verification,
- reuse,
- expiry,
- renewal,
- stale head,
- retention drift,
- archive tamper,
- signature tamper,
- wrong signer,
- fresh reader,
- TTL bounds,
- non-destructive authority.

---

## Operational principle

The durable evidence system should make the safe path the easy path:

1. evidence grows,
2. pressure becomes visible,
3. service stops accepting unsafe new work,
4. operator checkpoints deliberately,
5. live tail grows,
6. operator archives a signed prefix,
7. archive is independently verified,
8. recovery remains possible through archived historical roots,
9. non-destructive compaction readiness is proven,
10. service can continue under current policy.

The system deliberately stops before deletion.

That boundary is part of the security model, not unfinished bookkeeping.
