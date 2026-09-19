# Shell AI Sealed Execution

## Purpose

Sealed execution adds a high-assurance layer between plan review and child
process creation.

It binds one reviewed plan to:

principal

session

plan-control digests

optional source/workspace preconditions

optional human approval

short TTL

single-use replay state

The seal does not replace shell policy.

It narrows when a reviewed plan may cross into the shell service.

## Threat addressed

A normal reviewed plan can become stale before execution.

Possible drift:

AI policy changes

tool catalog changes

effect contracts change

model schema changes

compiled plan changes

source files change

workspace files change

approval expires

principal changes

another worker replays the same authorization

Sealed execution provides explicit binding and replay resistance.

## Components

High-assurance path uses:

AIPlanStaleGuard

PlanPin

Preconditions

PreconditionChecker

SourceDigestProvider

WorkspaceManifest

ExecutionSealAuthority

ExecutionSealRegistry

DistributedExecutionSealRegistry

AIShellService.seal_review

AIShellService.execute_sealed

## Plan pin

PlanPin binds:

intent fingerprint

proposal fingerprint

tool catalog digest

effect digest

AI policy fingerprint

AI response schema digest

execution plan fingerprint

A plan pin is deterministic review evidence.

## Stale-plan check

Before seal issuance AIShellService revalidates PlanPin.

Before normal execution AIShellService revalidates PlanPin again.

If a control surface changed:

execution stops.

The caller must review again.

## Preconditions

Preconditions bind external resources to expected SHA-256 digests.

A precondition has:

resource ID

expected digest

required flag

description

Required mismatches block execution.

Optional mismatches are reported but do not fail the aggregate report.

## Digest provider

PreconditionChecker delegates to a digest provider.

For source files use SourceDigestProvider.

Applications may provide another digest provider for:

database schema version

cloud deployment revision

artifact digest

container image digest

Git commit

lockfile digest

external configuration version

## Precondition provider rules

A provider should be:

deterministic

bounded

non-mutating

authenticated where external state is queried

free from model authority

The model must not control the digest returned.

## SourceDigestProvider

SourceDigestProvider pins a root directory.

resource_id must be relative.

Absolute resource IDs are rejected.

Resolved paths must remain under root.

Symlinks are denied by default.

## Symlink policy

When allow_symlinks is false:

any symlink component fails.

When true:

the resolved target must still be under root.

A symlink outside root fails.

## File size

Each hashed file has a maximum size.

Manifest has:

maximum entry count

maximum total file bytes

Hashing is chunked.

This prevents precondition verification from reading arbitrary unbounded files.

## Workspace manifest

WorkspaceManifest records:

path

entry kind

content digest

size

mode

Entries are sorted.

Duplicate paths fail.

Manifest itself has a deterministic digest.

## Manifest comparison

WorkspaceManifestComparator reports:

added paths

removed paths

changed paths

This is useful before:

code modification

build

test

deployment

release promotion

## Manifest limitations

A manifest is a point-in-time observation.

It does not lock files.

A file may change after the digest is checked.

For stronger guarantees execute from:

immutable VCS checkout

content-addressed snapshot

copy-on-write sandbox

read-only mount plus narrow write volume

## Execution seal

ExecutionSeal contains:

seal ID

principal

session ID

PlanPin

preconditions digest

approval ID

issued time

expiry

nonce

HMAC signature

## Seal key

ExecutionSealAuthority uses an HMAC key.

Minimum key length is 32 bytes.

The key must remain in trusted service memory or secret storage.

Never send the key to:

model

child process

MCP caller

review UI

audit export

## Seal issue

AIShellService.seal_review:

requires READY state

requires compiled plan

requires review pin

revalidates stale-plan state

validates human approval if review requires it

binds optional preconditions digest

issues short-lived seal

It performs no child execution.

## Approval binding

If AI policy requires approval:

seal issuance requires a valid AIPlanApproval.

The seal records approval ID.

execute_sealed must receive matching approval.

Normal execution later consumes the approval.

## Why approval is not consumed at seal issue

Seal issuance and execution may be separated by a very short review-to-run
boundary.

Consuming approval at seal issue could leave no approval for actual execution.

Instead:

seal issue validates approval

seal binds approval ID

execute_sealed consumes seal

normal execute consumes approval

Both are single-use controls.

## Seal TTL

Keep seal TTL short.

Recommended default is tens of seconds, not hours.

A seal represents final review-to-execution authority.

Long TTL increases drift risk.

## Seal verification

ExecutionSealAuthority verifies:

expiry

principal

session

PlanPin

preconditions digest

approval ID

HMAC signature

Any mismatch fails.

## Signature tamper

Changing any unsigned field invalidates signature.

Changing signature fails constant-time comparison.

A seal is not a bearer token for another principal.

## Single-use seal

ExecutionSealRegistry stores consumed seal IDs.

Second consume raises SealReplay.

This is enough for one process.

## Distributed seal

DistributedExecutionSealRegistry uses backend put_if_absent.

First worker consumes globally.

Other workers fail.

Use distributed replay state whenever more than one execution worker can receive
the same seal.

## Consumption durability

For high-impact work, seal consumption should be durable before child execution.

If the process crashes after consume but before spawn:

the seal remains consumed.

The operator should issue a new seal after checking evidence.

This favors duplicate-side-effect prevention over transparent retry.

## execute_sealed sequence

Current high-assurance service path:

verify service ready

verify compiled plan

load review pin

verify provided preconditions

compute preconditions digest

consume execution seal

call normal AIShellService.execute

normal execute rechecks PlanPin

normal execute checks quarantine

normal orchestrator validates/consumes approval

ShellService executes

verify

record provenance

## Precondition drift

If required source digest changed:

PreconditionChecker raises.

Seal remains unconsumed because preconditions are checked first.

No child is created.

Caller can:

reinspect source

replan if needed

review again

issue new seal

## Principal mismatch

If context principal differs from seal principal:

seal verification fails.

No child is created.

Do not rewrite context principal to match the seal.

## Session mismatch

Seal is bound to one AIShellSession.

A seal cannot move to another session.

## Plan mismatch

A PlanPin mismatch fails.

A changed proposal or plan must be resealed.

## Preconditions mismatch

A seal issued without preconditions cannot later be executed as though it were
bound to preconditions.

A seal issued with one precondition set cannot use another set.

Digest mismatch fails.

## Approval mismatch

An approval-required seal records approval ID.

Passing another approval fails seal validation or normal approval validation.

## Expiry

Expired seal fails.

No grace window is implicit.

If an operation missed its seal TTL:

revalidate plan

revalidate approval

issue a fresh seal

## Replay

Consumed seal cannot be reused.

Do not implement an unconsume operation.

A retry is new authority.

## Failed child

If child starts and fails:

seal remains consumed

approval remains consumed if it was required

receipt evidence records attempt

session becomes failed

A new retry should be a new reviewed or explicitly retried operation according
to policy.

## Stale policy after seal

AIShellService normal execute still performs stale-plan check.

If policy changes after seal issue but before execute:

execution fails stale.

Cryptographic seal does not freeze global policy into continued validity.

This is deliberate.

## Stale tool catalog after seal

Same rule.

Current control-plane drift invalidates reviewed work.

## Stale effect registry after seal

Same rule.

Risk/effect meaning changed.

Review again.

## Source change after precondition check

There remains a race between digest check and process file access.

For high-risk modification:

use immutable snapshot or sandbox mount.

The seal binds what was checked.

It does not create an OS filesystem transaction.

## Sandbox contract

For model-directed code or high-risk tools combine sealed execution with
AISandboxContract.

The contract derives:

isolation level

network isolation

home hiding

private tmp

clean environment

read-only source

write roots

CPU ceiling

memory ceiling

PID ceiling

file-byte ceiling

open-file ceiling

output ceiling

## Effect-to-isolation compile

AIIsolationCompiler reads effect contracts.

Read-only work stays workspace isolated.

Mutable/external work stays at least workspace isolated.

High-risk effects or high/critical risk require SANDBOXED.

## Write roots

Write roots are caller-configured allowlist.

Requested write root must be within a configured root.

If no roots are configured:

a requested write root fails.

An empty allowlist does not mean arbitrary write.

## Network

Network is allowed only when:

effect contract includes NETWORK

and intent constraint allows network.

Otherwise generated isolation requirement keeps network disabled.

## Home

AI isolation keeps home hidden.

Tools that need home should receive explicit isolated configuration rather than
ambient user home.

## Private tmp

AI isolation requires private temp.

This reduces cross-task file interference and secret leakage.

## Clean environment

AI isolation requires clean environment.

This reduces startup hooks and environment-driven code loading.

## Resource policy

AIResourcePolicy defines risk-band ceilings.

Higher risk receives tighter default resource bounds.

Resource profile includes:

wall seconds

CPU seconds

memory bytes

process count

file bytes

open files

output bytes

## Resource compile

AIResourceCompiler selects risk-band base.

Wall time is additionally bounded by:

intent max timeout

action timeout

action count

CPU never exceeds wall-time profile.

## Resource enforcement

Resource profile is declarative.

A sandbox backend must enforce it.

Do not claim memory/PID/file quotas merely because the contract contains them.

## Sandbox attestation

SandboxCapabilities declares what backend can enforce.

SandboxAttestationVerifier checks contract against capabilities.

Checks include:

isolation level

private tmp

clean environment

read-only source

network namespace

home hiding

process group

no-new-privileges

syscall filtering

resource limits

resource maximums

## High-risk contract

SANDBOXED plans require:

no-new-privileges

syscall filter

process group

network namespace when network disabled

resource limits

A backend without these fails attestation.

## Backend attestation identity

Sandbox capabilities include:

backend ID

backend version

capability digest

Record this with release evidence for high-assurance execution.

## Release safety case

AISafetyCaseBuilder combines:

AI diagnostics

eval run

red-team run

provider attestation

regression comparison

A blocked safety case is not deployable.

## Release evidence

ReleaseEvidence binds:

release ID

code revision

policy fingerprint

tool digest

effect digest

eval dataset digest

eval run digest

provider attestation digest

workspace manifest digest

safety case

## Release signing

AIReleaseRegistry signs evidence digest with ArtifactSigner.

Activation verifies signature.

Non-deployable release cannot activate.

## Release channel

AIReleaseChannelStore pins an active release to a channel with CAS.

Production can therefore identify exact evidence used by workers.

## Recommended high-assurance release sequence

hash reviewed source

build workspace manifest

run tests

run AI evals

run red team

verify provider attestation

verify sandbox attestation

build safety case

build release evidence

sign evidence

register release

activate release

promote canary channel

observe

promote production channel

## Recommended high-assurance execution sequence

load active signed release

verify release channel

create AI intent

plan

critique

compile

build review view

human approve if required

capture source preconditions

pin plan

issue execution seal

verify sandbox backend

consume distributed seal

consume approval

execute in sandbox

verify result

persist receipts

persist decision provenance

checkpoint terminal session

## Incident behavior

If a seal fails:

do not alter it

do not extend it

do not bypass

record reason

replan or reseal as appropriate

If precondition drift fails:

inspect source change

do not blindly update expected digest

Human review may need repetition.

## Operational metric

Track:

seals issued

seal verification failures

seal expiry

seal replay

precondition failures

stale-plan failures after seal

approval mismatch

sandbox attestation failures

Do not include HMAC keys or secret values in metrics.

## Audit

Audit records may include:

seal ID

seal expiry

principal

session ID

PlanPin digest fields

preconditions digest

approval ID

consume time

Do not export HMAC key.

Signature itself may be retained as evidence.

## Principle

A final execution authorization should be narrower than the plan that produced
it.

The execution seal is that final narrowing boundary.
