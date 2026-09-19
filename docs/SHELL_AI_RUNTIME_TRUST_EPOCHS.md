# Shell AI Runtime Trust Epochs

## Purpose

This document defines how production AI shell workers establish, pin, verify, rotate, and recover runtime trust.

The runtime trust epoch exists because a process can remain alive while its authority surface changes underneath it.

A worker may start with one model revision and later observe another.

A worker may start under one release and later see the channel move.

A worker may start with one tool catalog and later load another.

A worker may start with one assurance policy and later execute under a different one.

Production execution must not cross those boundaries silently.

The runtime trust epoch turns those mutable surfaces into one deterministic identity.

## Core invariant

A worker may execute only while the current authority surface reproduces the epoch pinned at startup.

If the epoch changes, execution stops.

The service does not automatically repin.

Repinning is a deployment or change-control operation.

## Runtime trust surface

RuntimeTrustSurface binds the local worker identity.

It includes:

- immutable code revision
- AI policy fingerprint
- tool catalog digest
- effect registry digest
- assurance policy digest
- optional workspace manifest digest

The surface contains no secret key material.

The surface contains no raw child output.

The surface contains no provider API token.

The surface contains no model prompt.

The surface is safe to hash and correlate in audit evidence.

## Code revision

The code revision should be immutable.

Recommended values include a Git commit SHA, signed build revision, or image digest tied to source revision.

Do not use a branch name as an immutable identity.

Do not use a mutable container tag as an immutable identity.

Do not use a deployment label as the only code identity.

A worker deployed from a different code revision must produce a different runtime trust epoch.

## Policy fingerprint

The active AI shell policy participates directly in runtime identity.

A policy revision creates a different trust epoch even when the next request would receive the same decision.

This preserves reproducibility.

It also prevents a seal reviewed under one policy from silently crossing into another policy regime.

## Tool catalog digest

The tool catalog digest identifies the exact tool surface available to the model.

Changes that should alter the digest include:

- command addition
- command removal
- argument schema change
- executable mapping change
- capability change
- timeout contract change
- input contract change
- output contract change

Provider attestations are checked against the same tool catalog digest.

A provider attested for one tool surface must not be accepted for another without a new attestation.

## Effect registry digest

Tool names alone do not describe risk.

The effect registry binds the operational effect model.

Examples include:

- filesystem read
- filesystem write
- filesystem delete
- network access
- irreversible external action
- idempotent action
- reversible action

A command may keep the same name while its effect contract changes.

The runtime trust epoch therefore binds tool identity and effect identity separately.

## Assurance policy digest

The assurance policy determines what execution evidence is required by risk band.

Examples include:

- seal required
- release evidence required
- preconditions required
- human approval required
- quorum required
- sandbox required
- critical work denied

If assurance is configured, the trust surface must bind the exact assurance policy digest.

If assurance is not configured, the surface must not pretend that it is.

Changing assurance policy changes the runtime trust epoch.

## Workspace manifest digest

Workspace binding is optional.

Use it when local trusted files affect execution authority.

Examples include:

- trusted prompt templates
- tool wrappers
- policy files
- generated schemas
- execution adapters
- sandbox profiles

Do not include mutable caches as authority inputs unless that is intentional.

Do not include arbitrary user output directories as authority inputs.

Manifest generation must be bounded.

Symlink handling must be explicit.

## Model bindings

Every admitted provider/model identity contributes a RuntimeModelBinding.

The binding contains:

- registry identity
- registry revision
- provider attestation digest

The registry identity is provider_id:model_id.

The registry revision is monotonic.

The attestation digest binds provider and model details.

## Provider attestation

Provider attestation includes:

- provider ID
- model ID
- model version
- adapter version
- structured output capability
- tool-use capability
- critique capability
- parallel-candidate capability
- input capacity
- output capacity
- protocol versions
- tool catalog digest
- bounded metadata

The runtime epoch records the attestation digest.

A silent provider-side model revision therefore changes the epoch when the registry is updated correctly.

## Model admission

Model admission answers whether the current provider/model is acceptable now.

Runtime trust answers whether it is the same accepted provider/model authority surface the worker pinned.

These are different questions.

A newer model may be acceptable.

A running worker should still stop before silently switching to it.

## Exact version policy

High-risk production environments should prefer exact version pins.

Recommended pins include:

- exact model version
- exact adapter version
- exact attestation digest
- exact tool catalog digest
- required protocol version

Looser compatibility policy can be used deliberately.

Even with looser compatibility, a registry revision changes the runtime epoch.

## Canonical ordering

Model bindings are sorted by registry identity.

Configuration order does not affect epoch identity.

The same model set produces the same canonical ordering.

Duplicate model identities are rejected.

One registry identity cannot be counted twice to create fake diversity.

## RuntimeTrustEpoch

RuntimeTrustEpoch binds:

- schema version
- runtime trust surface
- canonical model bindings
- release evidence digest
- release ID
- release revision
- release-channel revision

The epoch has a deterministic SHA-256 digest.

That digest is the runtime trust identity.

## Release evidence

Release evidence remains independently signed and verifiable.

The runtime trust epoch correlates live runtime state with that release evidence.

Release evidence can bind:

- code revision
- policy fingerprint
- tool catalog digest
- effect digest
- provider attestation
- eval evidence
- safety case
- workspace manifest

The epoch does not replace release evidence.

It makes release state part of live worker identity.

## Release ID and revision

Release ID and revision are included in the epoch.

This improves incident correlation.

It also makes change boundaries explicit.

A release promotion changes the runtime trust epoch.

## Release channel revision

Channel revision is part of the epoch.

This matters because the same named production channel can move between releases.

The worker must observe that movement as a trust boundary.

## AIRuntimeTrustGuard

AIRuntimeTrustGuard evaluates the full configured runtime trust surface.

It can verify:

- release channel
- release registry
- runtime release expectation
- model registry
- provider attestations
- assurance policy
- expected epoch digest

## Startup sequence

Recommended startup sequence:

1. start shell service
2. run AI diagnostics
3. verify shell service readiness
4. verify release channel
5. verify release evidence
6. verify model admissions
7. verify assurance policy identity
8. construct runtime trust epoch
9. pin runtime trust epoch
10. verify authority dependency health
11. enter READY
12. emit a signed trust snapshot

If any required trust check fails, startup fails.

Do not enter READY with a partial trust surface.

## Pinning

Pinning stores the expected epoch digest in the guard.

The guard can also receive an externally expected epoch digest.

External pinning is useful for:

- deployment manifests
- signed workload configuration
- orchestration metadata
- canary cohort identity
- recovery validation

The external expected digest must come from a trusted control plane.

Do not derive it from model output.

## Runtime verification

After startup, require_current reconstructs the trust epoch.

It repeats release verification.

It repeats model admission.

It checks assurance policy identity.

It compares the current epoch digest with the pinned digest.

A mismatch is runtime drift.

## Service behavior on drift

AIShellService rechecks runtime trust before:

- creating a new session
- reviewing a plan
- issuing a seal
- sealed execution
- normal execution

Drift while READY transitions the service to DEGRADED.

The operation fails.

No automatic repin occurs.

## Why automatic repin is forbidden

Automatic repin would silently authorize a changed authority surface.

That would convert detection into approval.

Production change boundaries must remain explicit.

A new epoch should enter service through deployment or controlled restart.

## Seal binding

The assurance binding includes runtime_trust_digest.

The signed execution seal therefore commits to the exact runtime epoch.

The seal already binds:

- risk band
- assurance policy
- plan fingerprint
- release evidence
- preconditions
- human approval
- quorum evidence
- execution backend
- sandbox binding

Runtime trust adds live model and authority-surface identity to that signed commitment.

## Model substitution example

Consider the following sequence.

A plan is reviewed under provider attestation A.

A seal is issued.

The model registry moves to attestation B.

The old seal reaches the worker.

Runtime trust verification detects drift.

The assurance binding digest changes.

The old seal cannot verify under the new epoch.

No child process starts.

## Release promotion example

A medium-risk plan is sealed under release R1.

The production channel moves to R2.

The old seal arrives after promotion.

Release verification sees R2.

Runtime trust epoch differs.

Assurance binding differs.

The seal fails.

The plan must be re-reviewed and resealed under R2.

## Assurance change example

A high-risk plan is reviewed while quorum is required.

The assurance policy later changes.

Even if the changed field does not affect one immediate command, the assurance policy digest changes.

The runtime epoch changes.

The seal binding changes.

Old authority does not cross the policy boundary.

## Model deactivation

Model deactivation makes model admission fail.

Runtime trust becomes non-admissible.

The service degrades.

Do not automatically substitute another provider.

Emergency revocation is intentionally disruptive.

## Model upgrade

A planned model upgrade should follow explicit rollout.

Recommended sequence:

1. register new provider attestation
2. keep current model active
3. run admission checks
4. run shell AI evals
5. run red-team cases
6. prepare release evidence
7. compute new runtime epoch
8. deploy canary
9. verify canary epoch
10. capture trust snapshot
11. observe
12. roll forward
13. drain old workers
14. deactivate old model

## Emergency model revocation

Recommended emergency sequence:

1. deactivate compromised model
2. allow existing workers to detect trust failure
3. stop shell execution
4. capture trust snapshot
5. inspect recent seals and receipts
6. rotate credentials if needed
7. prepare replacement attestation
8. run minimum emergency eval set
9. deploy replacement worker
10. pin new epoch
11. resume only after health and release verification

## Ensemble changes

Adding an ensemble member changes the epoch.

Removing an ensemble member changes the epoch.

Changing provider identity changes the epoch.

Changing model identity changes the epoch.

Changing registry revision changes the epoch.

Changing attestation digest changes the epoch.

Reordering the same model bindings does not change the epoch.

## Provider failover

Dynamic failover must not silently expand the admitted provider set.

If a standby provider is part of production policy, include it in the admitted model set before startup.

If it is not part of the pinned set, adding it requires a new epoch.

For high-risk work, loss of required provider diversity should fail closed.

## Model circuit breakers

A model circuit can open without changing registry identity.

Operational policy must decide whether the remaining ensemble is sufficient.

Do not silently lower consensus or diversity requirements because a provider is unavailable.

A degraded planning configuration should be explicit.

## Tool change rollout

Recommended sequence for tool changes:

1. modify command contract
2. update effect contract
3. regenerate tool catalog digest
4. regenerate effect digest
5. update provider attestations
6. run model admission
7. run AI evals
8. run security tests
9. produce release evidence
10. deploy new worker
11. pin new epoch

## Effect change rollout

Effect changes can alter risk classification.

Treat them as security-sensitive.

Examples:

- read becomes write
- write becomes delete
- network becomes enabled
- action becomes irreversible
- action becomes non-idempotent

Run risk and assurance regression tests before rollout.

## Policy change rollout

Recommended sequence:

1. prepare policy revision
2. run migration analysis
3. run tests
4. run evals
5. approve change
6. produce release evidence if required
7. deploy new worker
8. pin new epoch
9. capture trust snapshot
10. drain old workers

## Assurance change rollout

Assurance policy changes affect authority requirements.

Possible consequences include:

- new seal requirement
- new sandbox requirement
- new release requirement
- new preconditions
- new human approval requirement
- new quorum requirement
- changed critical-risk denial

Every production assurance-policy change should create a new runtime epoch.

## Workspace drift

When workspace manifest binding is enabled, source drift changes trust.

Recommended controls:

- immutable checkout
- content-addressed snapshot
- read-only source mount
- narrow writable output root
- explicit symlink policy
- bounded manifest size
- deterministic generated files

## Multi-worker cohorts

Workers in one homogeneous production cohort should normally pin the same epoch.

Canary cohorts may intentionally use a different epoch.

Record cohort identity explicitly.

Do not treat mixed epochs as one homogeneous authority plane.

## Blue-green deployment

Blue-green deployment maps naturally to trust epochs.

Blue keeps epoch A.

Green pins epoch B.

Green receives traffic only after:

- release verification
- model admission
- runtime trust pin
- authority health proof
- sandbox verification
- trust snapshot creation

Rollback routes traffic back to blue.

Blue does not need to repin.

## Rolling deployment

During a rolling deployment:

- old workers keep old epoch
- new workers pin new epoch
- routing should preserve epoch boundaries
- old seals should not execute on new workers
- new seals should not execute on old workers

The signed seal independently enforces the epoch through assurance binding.

## Queue behavior

When runtime trust drifts:

- stop accepting new sessions
- stop review
- stop seal issuance
- stop execution
- preserve queued metadata
- do not automatically replan under the changed model
- do not automatically migrate approvals
- do not automatically migrate quorum evidence

Pending work should be re-reviewed under the new epoch.

## Trust reports

RuntimeTrustReport contains:

- allowed
- reasons
- epoch
- release report
- model admission reports
- expected epoch digest

The report is suitable for internal operations.

It is not intended to expose secrets.

## Logging

Recommended bounded log fields:

- worker instance hash
- runtime epoch digest prefix
- release ID
- release revision
- channel revision
- model registry ID
- model revision
- drift category

Avoid raw prompts.

Avoid raw child output.

Avoid provider response bodies.

Avoid credentials.

## Metrics

Recommended metrics:

- trust inspections
- trust successes
- trust failures
- epoch drift events
- model admission failures
- release drift events
- assurance drift events
- startup trust failures
- service degradation transitions

Avoid high-cardinality labels.

## Alerts

Alert on:

- production worker enters DEGRADED due to trust drift
- workers in one cohort disagree on epoch
- registry revision changes outside rollout
- release channel changes outside rollout
- tool digest mismatch
- effect digest mismatch
- assurance digest mismatch
- repeated startup trust failures

## Trust snapshots

AITrustSnapshot correlates current trust state.

It binds:

- service phase
- runtime trust digest
- authority health policy digest
- audit witness head digest
- audit witness sequence
- release evidence digest
- sandbox binding digest
- observation time

The snapshot is signed.

## Snapshot use cases

Use signed trust snapshots for:

- deployment evidence
- canary promotion
- incident capture
- recovery completion
- audit export
- change-control evidence
- key-rotation boundaries

## Snapshot verification

A valid snapshot signature proves integrity.

It does not by itself prove the snapshot matches the deployment you expected.

Verification can require exact:

- runtime trust digest
- audit witness head digest
- release evidence digest

## Snapshot health policy

Normal production snapshots should require healthy authority dependencies.

Incident snapshots may intentionally capture DEGRADED state.

The builder supports require_healthy=False for that purpose.

Use that override only for evidence capture.

It must not authorize execution.

## Incident capture

Recommended incident capture sequence:

1. stop new execution
2. read service state
3. inspect runtime trust
4. inspect authority health
5. verify release
6. verify audit witness
7. capture sandbox binding
8. build signed trust snapshot
9. store snapshot outside affected worker
10. continue forensic analysis

## Trust signing key

The trust snapshot signer is a service integrity key.

Keep it outside:

- model context
- child environment
- logs
- user-facing output
- arbitrary plugin context

The snapshot contains key ID only.

## Key rotation

When rotating the trust snapshot signing key:

1. record old key ID
2. record final old-key snapshot
3. rotate key
4. record first new-key snapshot
5. preserve verification material according to retention policy

Key rotation does not necessarily change runtime epoch.

Your deployment policy may choose to bind signing-key identity separately.

## Expected epoch distribution

Preferred distribution mechanisms:

- signed deployment manifest
- immutable workload config
- secret manager metadata
- orchestration control plane

Avoid mutable local files without integrity controls.

Avoid user-supplied request metadata.

Avoid model-generated configuration.

## Restart recovery

On restart:

1. reconstruct runtime surface
2. verify release
3. verify models
4. verify assurance
5. construct epoch
6. compare expected digest
7. verify authority health
8. verify audit witness
9. enter READY only if all required checks pass

## Release rollback recovery

If production channel moves backward unexpectedly:

1. service detects release or epoch drift
2. service degrades
3. capture trust snapshot
4. inspect release history
5. verify signatures
6. restore intended channel using CAS
7. restart worker
8. pin intended epoch
9. re-review pending plans

## Registry rollback recovery

If model registry storage is restored to an older state:

- externally pinned epoch detects mismatch
- recent trust snapshots show last accepted epoch
- audit witness history helps locate the recovery boundary
- old model state is not accepted merely because its attestation is valid

## Tool rollback recovery

If an old tool catalog is accidentally deployed:

- local tool digest differs
- release expectation may fail
- runtime epoch differs
- startup should fail
- no shell authority should be issued

## Policy rollback recovery

If an old policy is restored:

- policy fingerprint differs
- runtime trust differs
- release verification may differ
- old seals remain bound to their original epoch
- execution fails until deployment is reconciled

## Threats addressed

Runtime trust helps address:

- silent model upgrade
- silent adapter upgrade
- provider identity substitution
- model registry revision drift
- model deactivation
- tool surface drift
- effect drift
- policy drift
- assurance policy drift
- release promotion during pending authority
- release rollback
- workspace drift
- mixed worker epochs

## Threats not solved alone

Runtime trust does not independently solve:

- compromised operating system
- compromised signing key
- malicious provider
- malicious state backend with unrestricted write authority
- sandbox escape
- rollback of arbitrary external side effects
- malicious human approver

Those require independent controls.

## Production minimum profile

Recommended minimum for production AI shell execution:

- signed release evidence
- model/provider admission
- runtime trust epoch
- execution assurance
- signed execution seal
- distributed seal replay protection
- authority dependency health
- durable execution receipts
- durable decision journal
- audit anchors
- audit witnesses
- signed trust snapshots

## High-risk additions

High-risk work should also require:

- source preconditions
- human approval
- dual-control quorum
- verified sandbox
- resource ceilings
- immutable source snapshot
- sandbox binding
- runtime trust digest inside seal
- terminal audit witness

## Critical risk

The production assurance policy denies critical risk.

Runtime trust does not override that denial.

Trust is not permission.

Trust proves identity of the authority surface.

Policy still decides whether execution is allowed.

## Operator startup checklist

Confirm:

- code revision immutable
- policy fingerprint correct
- tool digest correct
- effect digest correct
- assurance digest correct
- workspace digest correct when enabled
- release channel correct
- release signature valid
- models active
- attestations compatible
- expected epoch correct
- authority health healthy
- service READY

## Operator execution checklist

Before high-risk execution confirm:

- service READY
- runtime epoch current
- release current
- authority health healthy
- plan pin current
- preconditions verified
- human approval valid
- quorum valid
- sandbox verified
- seal unused
- assurance binding matches epoch

## Drift checklist

When drift occurs:

- do not repin in place
- capture status
- capture trust snapshot
- identify changed binding
- stop execution
- classify expected versus unexpected change
- follow rollout or incident process
- restart under intended epoch

## Design principle

A newer runtime can be compatible and still be the wrong runtime for an already-authorized action.

The runtime trust epoch preserves that distinction.

For host-side AI execution, identity continuity is part of authorization.
