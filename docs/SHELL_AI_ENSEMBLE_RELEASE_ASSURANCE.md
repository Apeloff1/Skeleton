# Shell AI Ensemble, Release, and Assurance Operations

## Purpose

This document describes the controls around model diversity, release identity, and execution assurance.

These controls answer three different questions.

Which model proposal should be considered?

Which reviewed software/model/policy release is allowed to serve traffic?

What isolation level must be used before a reviewed plan can execute?

Those questions are intentionally separate.

## Model diversity is not authority

Multiple models agreeing does not grant shell authority.

Consensus can improve proposal confidence.

Consensus cannot bypass:

guardrails.

risk assessment.

AI policy.

approval.

release verification.

execution seals.

sandbox requirements.

ShellService.

ShellExecutor.

ShellRunner.

## Robust consensus

RobustProposalConsensus fixes a common ensemble failure.

Repeated proposals from one model identity count as one vote.

A single model cannot manufacture consensus by producing several proposal IDs.

## Proposal shape

Consensus groups proposals by action shape.

Shape includes:

logical command.

argv.

cwd.

environment key names.

timeout.

dependencies.

continue-on-failure.

Provider or model identity does not change the shape.

## Unique model votes

Each model ID receives at most one vote for a shape.

If the same model emits multiple proposals for the same shape, the deterministic better proposal is retained.

The comparison favors:

higher confidence.

lower uncertainty.

stable proposal ID tie break.

## Provider diversity

Consensus can also require unique providers.

This protects against several model aliases backed by one provider being treated as fully independent evidence.

Provider identity must come from trusted configuration.

Do not accept a model-provided provider ID.

## Missing provider identity

Policy can reject missing provider identity.

For low-assurance experimentation, unknown provider IDs can be represented distinctly per model.

Production multi-provider consensus should require explicit provider identity.

## Confidence threshold

Consensus can require a minimum average confidence.

Confidence remains model-reported.

It is only one filter.

Deterministic risk and policy remain authoritative.

## Uncertainty threshold

Consensus can require a maximum average uncertainty.

This helps prevent ambiguous plans from becoming the ensemble winner merely because several models agree.

## Eligible groups

A group is eligible only when all configured consensus conditions pass.

Group size alone is not enough.

## Group ranking

Eligible groups rank before ineligible groups.

Ranking then considers:

provider diversity.

model diversity.

confidence.

uncertainty.

shape digest.

This ordering is deterministic.

## EnsembleAIPlanner

EnsembleAIPlanner turns robust consensus into a planning workflow.

It owns a bounded set of EnsembleMember values.

Each member contains:

AIPlanner.

trusted provider ID.

## Member compatibility

By default every ensemble member must expose the same tool catalog digest.

By default every member must use the same AI policy fingerprint.

A mismatch fails construction.

This prevents fallback or ensemble planning from widening execution authority.

## Bounded members

EnsemblePolicy limits how many members are called.

The ensemble does not fan out without limit.

## Minimum successes

A minimum number of successful proposals is required.

If provider failures leave too few results, planning fails closed.

The system does not lower the threshold automatically.

## Health-aware ordering

Members are ordered by provider health.

Healthy providers are preferred.

Unknown providers remain usable.

Degraded providers rank lower.

Unhealthy providers rank lower still.

Quarantined providers are skipped.

## Circuit breakers

An open model circuit excludes that member.

A model outage does not cause direct shell execution.

The ensemble continues only if enough other members remain.

## Rate limiting

Each provider/model key is rate limited.

A rate-limited member is skipped.

The required success count still applies.

## Provider failure

A failed provider attempt records:

provider ID.

model ID.

status.

latency.

error type.

Health and circuit state are updated.

The exception does not widen authority.

## Consensus after collection

The ensemble builds robust consensus over successful proposals.

If consensus is not reached, planning fails.

No proposal executes merely because it was the highest confidence individual result.

## Candidate selection

After a winning shape is known, CandidateSelector performs deterministic critique on candidates in that shape.

It considers:

guardrails.

risk.

policy.

confidence.

uncertainty.

action count.

Only a candidate accepted for execution is selected.

## Normal review still follows

The chosen ensemble result still enters the ordinary orchestration review.

Ensemble selection is not the final review.

This intentional duplicate checking is defense in depth.

## Release evidence

Model behavior is only one part of production identity.

ReleaseEvidence binds:

code revision.

AI policy fingerprint.

tool catalog digest.

effect registry digest.

eval dataset digest.

eval run digest.

provider attestation digest.

optional workspace manifest digest.

safety case.

## Safety case

SafetyCase can block a release when:

AI diagnostics contain errors.

eval pass rate is below threshold.

red-team cases fail.

a regression is detected.

provider attestation is absent or incompatible.

A blocked safety case is not deployable.

## Provider attestation

ProviderAttestation describes:

provider ID.

model ID.

model version.

adapter version.

capabilities.

supported AI protocol versions.

tool catalog digest.

The digest gives that capability statement a stable identity.

## Release registry

AIReleaseRegistry stores release evidence.

It signs the release evidence digest.

A registered release is not automatically active.

Activation is explicit.

A non-deployable release cannot activate.

## Release signature

ArtifactSigner uses HMAC.

Activation verifies the signature.

A tampered registered release does not activate.

## Release channels

AIReleaseChannelStore maps channels to active releases.

Typical channels:

development.

canary.

staging.

production.

The channel state pins:

release ID.

release revision.

evidence digest.

registry signature.

## Channel CAS

Channel promotion is compare-and-swap.

Two deploy controllers cannot silently overwrite one another.

A stale promotion fails.

## Runtime release expectation

RuntimeReleaseExpectation declares what the running worker believes it is.

It includes:

channel.

code revision.

policy fingerprint.

tool catalog digest.

effect digest.

optional provider attestation digest.

optional workspace manifest digest.

## Startup guard

AIStartupReleaseGuard compares runtime expectation with the active channel and signed release.

It verifies:

channel exists.

release exists.

release is active.

channel revision matches registry.

evidence digest matches.

channel signature matches.

registry signature verifies.

safety case is deployable.

code matches.

policy matches.

tool catalog matches.

effects match.

provider attestation matches when required.

workspace manifest matches when required.

## Startup failure

AIShellService can receive a release guard and expectation.

They must be configured together.

During start, release mismatch moves the AI service to FAILED.

The worker does not accept sessions.

## Live release drift

Startup checking alone is insufficient.

A production channel can move after a worker is READY.

AIShellService therefore rechecks the release before authority transitions.

Current checks occur before:

new session.

review.

seal issue.

sealed execution.

normal execution.

## Drift reaction

If a READY worker discovers release drift, it transitions to DEGRADED.

The attempted authority transition fails.

This prevents an old worker from continuing to serve after the production release identity changed.

## Worker rollout

A deployment can intentionally keep canary and production workers on different release channels.

Each worker must declare the channel it serves.

A production worker should not silently follow canary.

## Release digest in provenance

Execution provenance can include the verified release evidence digest.

This ties a completed execution to the exact signed release identity.

## Release digest in execution seal

ExecutionSeal also binds release evidence digest.

A seal issued under one release cannot be consumed as though it belonged to another.

## Channel move after seal issue

Suppose a seal is issued.

Then production channel changes.

Before execution, live release verification fails.

Even if the service still reached seal verification, release digest mismatch would invalidate the old seal.

This is deliberate double protection.

## Execution assurance

AI policy answers whether a plan is allowed or needs approval.

Execution assurance answers how strongly it must be contained.

These are different controls.

## Assurance levels

STANDARD.

SEALED.

SANDBOXED.

DENIED.

## Default assurance policy

Low risk defaults to STANDARD.

Medium risk defaults to SEALED.

High risk defaults to SANDBOXED.

Critical risk defaults to DENIED.

Deployments can narrow this further.

## Standard execution

STANDARD means the reviewed plan may use the configured default execution backend.

All lower shell policy still applies.

Standard does not mean unrestricted.

## Sealed execution

SEALED requires execute_sealed.

The plan must have a valid one-use execution seal.

Preconditions can be bound into that seal.

Release evidence is bound when release enforcement is enabled.

## Sandboxed execution

SANDBOXED requires:

sealed execution.

actual VerifiedSandboxExecutionBackend.

compatible sandbox attestation.

exact plan fingerprint binding.

sandbox contract digest binding.

sandbox capability digest binding.

## Backend-name spoofing

A backend cannot satisfy sandbox assurance merely by returning a string beginning with "sandbox:".

AIShellService checks the backend type.

The verified sandbox wrapper must be present.

## Critical risk

Default assurance denies critical-risk execution.

Even a valid seal and sandbox do not override this default.

A plan should be redesigned or governed through a separate higher-assurance process.

## Assurance before seal consumption

AIShellService checks assurance before consuming a one-use seal.

An operator mistake selecting the wrong backend does not burn a valid seal.

Once assurance passes, seal replay protection applies.

## Verified sandbox backend

VerifiedSandboxExecutionBackend is bound to:

one plan fingerprint.

one sandbox contract digest.

one sandbox capability digest.

Construction verifies compatibility.

Execution rechecks compatibility.

## Capability drift

A sandbox backend can change after binding.

Before execution the wrapper checks:

current capabilities still satisfy contract.

capability digest still matches.

contract digest still matches.

plan fingerprint still matches.

A drifted backend fails.

## Sandbox contract

AISandboxContract combines:

IsolationRequirement.

AIResourceProfile.

process group requirement.

no-new-privileges requirement.

syscall-filter requirement.

network-namespace requirement.

## Effect-driven isolation

AIIsolationCompiler derives isolation from effect declarations and deterministic risk.

Read-only work remains workspace isolated.

Mutable or external effects require at least workspace isolation.

High-risk or destructive effects can require SANDBOXED.

## Network control

Network remains disabled unless both:

the tool declares network effect.

the intent allows network.

A model cannot enable network merely by asking for it.

## Write roots

Write roots are configured by trusted caller policy.

A requested root must be inside a configured allowed root.

No configured write roots means a requested write root fails closed.

## Resource ceilings

AIResourceProfile can bound:

wall time.

CPU time.

memory.

process count.

file bytes.

open file count.

output bytes.

The contract is declarative until enforced by the sandbox backend.

## Sandbox attestation

SandboxCapabilities describes what a backend can actually enforce.

The verifier checks the requested contract against those capabilities.

A backend without required enforcement is incompatible.

## No-new-privileges

High-risk sandbox contracts can require no-new-privileges enforcement.

This is a backend responsibility.

The Python control plane does not pretend to emulate kernel enforcement.

## Syscall filtering

High-risk sandbox contracts can require syscall filtering.

A backend that cannot enforce it fails attestation.

## Network namespace

No-network work can require a network namespace or equivalent backend isolation.

A mere environment convention is not enough.

## Process group

The sandbox should own child lifecycle.

A process group is a minimum lifecycle primitive.

Container or cgroup lifecycle can be stronger.

## Assurance deployment

To enable production assurance:

construct AIExecutionAssuranceInspector.

pass it to AIShellService.

configure verified sandbox backend for high-risk plans.

use execute_sealed for medium and high risk.

Keep critical denied unless a separately reviewed governance path exists.

## Medium-risk caller behavior

If normal execute is called for a medium-risk plan, assurance rejects it.

The caller should:

obtain approval if required.

capture preconditions.

issue execution seal.

call execute_sealed.

## High-risk caller behavior

For high risk:

obtain approval.

compile isolation requirement.

compile resource profile.

build sandbox contract.

attest sandbox.

construct VerifiedSandboxExecutionBackend for the exact plan.

issue execution seal.

call execute_sealed with verified backend.

## Audit evidence

AIDecisionProvenance can record:

execution backend ID.

session execution evidence digest.

sandbox binding digest.

release evidence digest.

These fields let operators prove not only what ran but under which runtime boundary.

## Signed audit anchors

AIAuditAnchorStore creates a final durable signed commitment.

The anchor ties:

recovery checkpoint.

execution provenance.

journal root.

receipt root.

session evidence.

release evidence.

sandbox binding.

## Evidence finalization

AIExecutionEvidenceFinalizer should run after COMPLETE or FAILED execution.

It verifies the current chains.

It confirms stable proposal identity.

It persists session execution evidence.

It builds session journal commitment.

It builds recovery checkpoint version two.

It appends signed audit anchor.

## Release and audit separation

Release signature proves which software/model/policy evidence was approved.

Execution audit anchor proves what a particular session produced.

Both are needed for strong traceability.

## Canary release

A canary release should have its own signed ReleaseEvidence.

The canary channel should point at that release.

Canary workers verify that channel.

Do not emulate canary by running production channel workers with hidden overrides.

## Policy canary

Policy rollout and release rollout can coexist.

If policy is materially part of the release identity, release evidence must reflect the target policy fingerprint.

Do not let a worker claim release A while executing policy B.

## Ensemble canary

A new model can be canaried through a new provider/model attestation and release evidence.

Run evals.

Build safety case.

Sign release.

Promote canary channel.

Observe ensemble and calibration metrics.

Then promote production channel.

## Metrics

Track ensemble:

successful member count.

failed members.

quarantined members.

circuit-open skips.

rate-limited skips.

consensus reached.

provider diversity.

unique model votes.

candidate selection failures.

Track release:

startup verification failure.

live release drift.

channel revision.

release ID.

evidence digest.

signature verification failure.

Track assurance:

standard executions.

sealed executions.

sandboxed executions.

assurance denials.

seal replay.

sandbox capability drift.

critical-risk denials.

## Alerting

Critical alerts:

production worker release mismatch.

signed release verification failure.

sandbox capability drift during high-risk execution.

critical-risk execution attempt.

audit-anchor verification failure.

reused execution seal.

High alerts:

ensemble provider diversity collapse.

repeated consensus failure.

unexpected policy/catalog mismatch across ensemble members.

sandbox resource capability below contract.

## Incident response

For release drift:

stop new authority transitions.

mark worker degraded.

inspect production channel.

compare signed release.

restart worker on correct release.

do not manually edit expected digests.

For sandbox drift:

stop high-risk execution.

quarantine backend.

inspect backend deployment/version.

rerun attestation.

issue fresh execution seals after remediation.

For ensemble anomaly:

quarantine suspicious provider.

inspect proposal shapes.

review model/version attestation.

rerun red-team and eval suite.

Do not relax consensus thresholds during incident pressure.

## Fail-safe behavior

When an ensemble cannot reach consensus, planning fails.

When release identity cannot be verified, service fails or degrades.

When assurance cannot be met, execution fails.

When sandbox capability cannot be verified, high-risk execution fails.

These are availability failures by design.

## Operational principle

Intelligence can be redundant.

Authority must remain singular.

Several models can propose.

Several workers can coordinate.

Several backends can exist.

But every execution must still prove one coherent release identity, one reviewed plan, one assurance level, and one evidence trail.
