# Shell AI Distributed Operation

## Scope

This document defines the expected semantics when the AI shell control plane
runs across multiple service processes or workers.

The core shell execution policy remains unchanged.

Distributed operation affects coordination state such as:

- AI policy revisions
- session checkpoints
- review claims
- idempotency
- execution-seal replay prevention
- release channels
- provider routing state
- task state

The purpose of distributed state is to preserve one logical authority boundary
when many processes participate.

## Core rule

A second process must never create a second authority path.

Multi-instance operation must preserve:

- compare-and-swap
- fencing
- exact revision checks
- principal identity
- single-use approvals
- single-use execution seals
- stale-plan checks
- tool/effect/policy digests
- receipt evidence

Availability may degrade.

Authority must not widen.

## Reference backend

InMemoryFencedStore defines the expected coordination behavior.

It is not a durable distributed database.

It exists so:

- semantics are executable
- tests are deterministic
- durable implementations have a contract to copy
- fencing behavior can be verified

Production distributed backends should implement DistributedAIBackend.

## State backend protocols

VersionedStateBackend defines:

get

put_if_absent

compare_and_swap

delete

FencedLeaseBackend defines:

acquire_lease

renew_lease

release_lease

require_fence

DistributedAIBackend combines those contracts and adds fenced_compare_and_swap.

## Namespace

Every distributed subsystem uses a namespace.

Namespaces separate logical record families.

Examples:

shell-ai-policy

shell-ai-session

shell-ai-review

shell-ai-idempotency

shell-ai-seal-use

shell-ai-release-channel

Do not mix unrelated record schemas in one namespace.

## Keys

Keys must be canonical.

Good examples:

session ID

review item ID

seal ID

idempotency key

release channel name

Avoid:

free-form user text

raw prompts

secret values

unbounded URLs

## Revision semantics

Every VersionedValue has a monotonically increasing revision.

First creation is revision one.

compare_and_swap requires the exact expected revision.

A stale writer fails.

The stale writer must reload.

It must not overwrite blindly.

## Create semantics

put_if_absent creates only when no record exists.

A second create fails with conflict.

This is used for:

seal consumption

idempotency

initial policy state

review item creation

## Delete semantics

Delete is revision checked.

A stale delete fails.

This prevents a process from deleting a record another process has updated.

## Lease purpose

A lease represents temporary exclusive ownership.

A lease is not authorization to execute a shell command.

It is coordination authority for a specific distributed record.

Examples:

human review claim

worker claim

migration ownership

## Fencing token

Every successful lease acquisition receives a fencing token.

The token monotonically increases for that namespace/key pair.

When a lease expires and another owner acquires:

the new owner receives a larger token.

The stale owner cannot use its old token to write.

## Why fencing matters

Lease expiry alone is not enough.

Scenario:

worker A acquires lease

worker A pauses

lease expires

worker B acquires lease

worker B updates record

worker A wakes up

Without fencing, worker A could overwrite worker B.

With fencing, worker A's token is stale.

Its write fails.

## Lease renewal

Renewal preserves the fencing token.

Renewal replaces the lease instance with a later expiry.

An old pre-renewal lease object becomes stale.

This prevents copied lease state from being reused indefinitely.

## Lease release

Only the exact current lease may release.

A stale lease cannot release a new owner's lease.

An expired lease returns no live ownership.

## Lease time

Reference implementation uses monotonic time.

A durable backend should use a consistent lease clock.

For database-backed leases, prefer server-side time.

Avoid trusting arbitrary worker wall clocks.

## Distributed policy store

DistributedAIPolicyStore maps AIPolicyStore semantics to CAS storage.

The active policy resides at one canonical record.

Policy revision is backend revision.

Policy fingerprint remains deterministic content identity.

## Policy initialization

First service instance may initialize policy.

Concurrent initializers race on put_if_absent.

One wins.

Others reload the winner.

A second process cannot silently replace initial policy during startup.

## Policy update

compare_and_swap takes expected revision.

If another service updates first:

the stale service gets AIPolicyConflict.

It must reload and reconcile.

## Policy rollout

AIPolicyRolloutManager uses policy revision fencing at the application level.

PREPARED:

base policy remains active.

CANARY:

base policy remains active globally.

Selected principals resolve target through policy_for.

BROAD:

target is written to policy store with compare-and-swap.

If active policy changed during canary:

BROAD transition fails.

This prevents canary rollout from overwriting an independent security change.

## Distributed session store

DistributedAISessionStore stores AISessionCheckpoint by session ID.

First checkpoint is revision one.

Changed checkpoint increments revision.

Identical checkpoint is idempotent.

## Session writers

When more than one worker can checkpoint a session:

always provide expected_revision.

A stale checkpoint writer must not win.

If a conflict occurs:

reload current checkpoint

compare phase and evidence roots

decide whether to resume, verify, or replan

Use AIRecoveryManager.

## Session ownership

DistributedAISessionStore itself does not lease a session.

A deployment that allows active concurrent session workers should layer a
FencedLease over session ID.

One active execution owner is safer than concurrent execution.

## Distributed human review

DistributedAIReviewQueue uses both CAS and a lease.

The review record holds:

review payload

state

reviewer

reason

expiry

The claim holds:

review item ID

reviewer

fenced lease

## Review claim

A reviewer claims PENDING work.

Claim acquisition:

checks item state

acquires lease

writes CLAIMED under that lease

returns fencing token

A second reviewer cannot claim while lease is live.

## Review decision

Decision requires:

live lease

current fencing token

CLAIMED state

matching reviewer identity

current record revision

Decision writes APPROVED or REJECTED.

Lease is released afterward.

## Expired review

Review item has its own review TTL.

Lease TTL and review TTL are different.

Review TTL controls how long the review decision is valid.

Lease TTL controls how long one reviewer owns the claim.

## Stale reviewer

A reviewer whose lease expired cannot decide after another reviewer acquired a
new lease.

The new reviewer has a higher fencing token.

The stale decision is rejected.

## Distributed execution-seal replay

A short-lived execution seal is cryptographically verifiable.

Cryptographic verification alone does not make it single-use.

DistributedExecutionSealRegistry uses put_if_absent on seal ID.

First consumer wins.

Every other worker sees conflict.

This is the global replay barrier.

## Seal consumption order

Recommended order:

verify source preconditions

verify execution seal signature and bindings

atomically consume seal ID

recheck local stale-plan pin

consume human approval if required

admit ShellService execution

The application should keep this sequence narrow.

## Failed execution after seal consumption

A consumed seal should normally remain consumed even if later execution fails.

Do not return a seal to unused state automatically.

A retry should obtain a new reviewed seal.

This avoids replay ambiguity.

## Distributed idempotency

DistributedAIIdempotencyRegistry globally binds:

idempotency key

request digest

proposal fingerprint

expiry

Concurrent registrations with identical data converge.

Conflicting data fails.

## Idempotency expiry

After expiry, the old record may be deleted by revision.

A new request can claim the key.

If delete races:

the caller reloads winner.

Do not allow conflicting request data under a still-live key.

## Idempotency scope

Choose key scope deliberately.

Examples:

principal + operation ID

workflow + task ID

API request ID

MCP task ID

Do not use a globally reused constant.

## Idempotency is not approval

An idempotency record says:

this key maps to this request/proposal.

It does not authorize execution.

It does not replace approval.

It does not replace capability policy.

## Release channels

AIReleaseChannelStore maps a channel to an active signed release.

Example channels:

development

canary

staging

production

A channel record pins:

release ID

release registry revision

release evidence digest

registry signature

## Release channel CAS

Channel update uses expected revision.

Two deployment controllers cannot silently overwrite each other.

A stale promotion attempt fails.

## Release activation order

Recommended:

build release evidence

build safety case

sign release evidence

register release

activate registered release

set canary channel with CAS

observe

set production channel with CAS

## Active release

Only active RegisteredRelease can become a channel state.

This prevents unapproved evidence from being deployed simply by writing a
channel record.

## Signed artifact

ArtifactSigner provides HMAC integrity for service-to-service artifacts.

Use it for:

release evidence

policy bundle digests

eval bundle digests

snapshot digests

HMAC key must not be available to:

model

child process

review UI

MCP client

## HMAC limitations

HMAC proves integrity to parties sharing the key.

It does not provide independent public verification.

For external compliance or cross-organization verification use a proper
public-key signing service outside this module.

## Distributed key management

Do not copy HMAC keys into application configuration files.

Use a secret manager.

Rotate keys using key ID.

Retain old verification keys for evidence retention windows where necessary.

## Source preconditions

SourceDigestProvider hashes reviewed source files.

Preconditions can bind these file digests to execution.

This closes one class of review-to-execution race.

## Source root

SourceDigestPolicy pins one absolute root.

resource_id must be relative.

Absolute paths are rejected.

Parent traversal is rejected.

Resolved path must remain under root.

## Symlinks

Symlinks are denied by default.

If symlinks are enabled:

resolved target must still remain under root.

External symlink targets are denied.

## Digest limits

SourceDigestPolicy limits:

per-file bytes

manifest entries

manifest total bytes

This prevents source verification from becoming an unbounded I/O operation.

## Workspace manifest

WorkspaceManifest is a deterministic list of path metadata and content digests.

It can be used as:

release evidence

execution precondition

audit evidence

drift comparison

## Workspace drift

WorkspaceManifestComparator reports:

added

removed

changed

A critical reviewed write plan should generally require clean expected source
state before execution.

## What manifest does not solve

A manifest is not atomic filesystem locking.

Files can still change after digest verification.

For stronger semantics:

execute in immutable snapshot

use content-addressed workspace

use copy-on-write sandbox

use VCS worktree at pinned commit

use filesystem snapshot

## Multi-instance shell receipts

The current in-memory receipt ledger is process-local unless backed by durable
storage elsewhere.

A production distributed shell service should use durable execution evidence.

At minimum preserve:

receipt ID

command fingerprint

principal

correlation ID

return code

timeout/output flags

receipt-chain or signed evidence

## Decision journal

The current decision journal is also process-local.

For multiple instances:

persist events to a transactional append log

retain sequence or per-session sequence

preserve hash links

reject duplicate sequence

export immutable copies

Do not reconstruct missing events from model text.

## Provider health

ProviderHealthRegistry is local reference state.

In distributed routing, health can be:

local per instance

aggregated centrally

or both.

Do not let a stale healthy score override explicit quarantine.

## Model circuits

Circuit state can be local.

A globally failing provider may benefit from shared circuit state.

If shared:

use monotonic backend expiry

do not allow one stale worker to close another worker's open circuit.

## Rate limits

Provider rate limits often need global enforcement.

The in-memory token bucket is a reference.

A distributed implementation should use:

atomic counters

token bucket in Redis-like store

provider gateway limits

or central scheduler.

Never assume per-worker limit equals global limit.

## Quarantine

High-severity quarantine should be shared across instances.

Model, proposal, and command quarantine must propagate quickly.

If a worker cannot read current quarantine:

fail closed for high-risk execution.

## Review queue availability

If review backend is unavailable:

approval-required work stops.

Do not treat queue outage as implicit approval.

## Policy backend availability

If active policy cannot be read:

new high-risk work should stop.

A service may use a recently pinned signed policy only under explicit
availability policy.

Do not silently use defaults.

## Seal backend availability

If global seal replay backend is required and unavailable:

sealed execution should stop.

Do not fall back to local replay state for production multi-instance execution.

## Idempotency backend availability

If an operation depends on exactly-once planning semantics:

backend outage should fail the operation.

Do not create a new proposal under the same unknown key.

## Release channel backend availability

If release channel cannot be read:

service should not invent a release.

Use last verified signed release only under explicit startup policy.

## Split-brain

Distributed stores must avoid split-brain writes.

CAS plus fencing assumes one consistent backend.

Eventually consistent storage may not provide enough safety for:

approval

seal consumption

review claims

policy revision

release channels

Use strongly consistent primitives.

## Database implementation

A relational backend can implement CAS with:

revision column

UPDATE ... WHERE revision = expected

check affected row count

increment revision in transaction

Lease can use:

owner

fencing_token

expires_at

atomic token increment

server-side time

## Redis-style implementation

Use Lua or transactions for:

put-if-absent

CAS

lease token increment

lease owner replacement

fenced write

Do not implement fencing as separate non-atomic GET and SET calls.

## Durable queue implementation

Review queue can use a database row plus lease columns.

Decision write should include:

item ID

expected row revision

expected fencing token

reviewer

terminal state

All in one transaction.

## Worker identity

Worker owner strings should be stable and authenticated internally.

Do not use arbitrary user-provided strings as fencing identity.

Recommended:

service instance ID

worker UUID

authenticated reviewer ID for human claims

## Principal identity

Execution principal is not worker identity.

Principal represents caller authority.

Worker identity represents coordinator ownership.

Keep them separate.

## Correlation identity

Correlation ID traces work.

It is not authorization.

It is not lease ownership.

It is not idempotency unless explicitly chosen.

## Clock behavior

Leases and TTLs require consistent time semantics.

In-memory reference uses monotonic clock.

Distributed backends should prefer backend/server time.

Avoid trusting client wall-clock timestamps for lease validity.

## Recovery

After worker crash:

load session checkpoint

load policy

load tool/effect contracts

load receipt evidence

inspect lease state

run AIRecoveryManager

resume only if safe

Never replay a child command solely because session was EXECUTING.

## Exactly-once illusion

True exactly-once side effects are generally impossible across arbitrary
external systems.

The architecture aims for:

single-use authority

fenced coordination

idempotent planning

detectable receipts

explicit verification

compensation planning

This is safer than claiming exactly once.

## Side-effect idempotency

For external side effects prefer application-level idempotency keys accepted by
the target API.

Shell-level idempotency cannot make a non-idempotent remote API safe.

## Distributed MCP

MCP protocol envelope is stateless.

That does not mean authorization state is stateless.

Remote workers should share:

principal policy

quarantine

release channel

tool catalog version

policy version

if those affect request handling.

## Principal-filtered discovery

MCPPrincipalDiscovery filters tool descriptors by MCPAuthorization.

Returned list is private.

Digest is bound to principal identity.

Two principals with same visible tools still receive distinct discovery digests.

This prevents one principal's cached discovery identity from being treated as
another principal's authority.

## Routing headers

MCPTransportValidator verifies:

header count

header name bytes

header value bytes

required Mcp-Method

required Mcp-Name

method/body equality

name/body equality

A remote gateway should run equivalent validation before deeper dispatch.

## Header trust

Headers help routing.

Authentication must derive principal independently.

Mcp-Name does not authorize the named tool.

## Release deployment

Each running instance should know:

release channel

release ID

release evidence digest

policy fingerprint

tool digest

effect digest

model attestation digest

code revision

Expose these in internal status.

## Drift detection

Instances with different release evidence should be considered configuration
drift.

A load balancer or orchestrator should not mix incompatible AI policy surfaces
without an intentional canary.

## Canary instances

Canary may intentionally run target policy for selected principals.

The principal selection function should be deterministic.

The service should record which policy fingerprint handled a session.

## Observability

Distributed dashboards should distinguish:

local instance state

global coordination state

provider state

shell execution state

release state

Do not average away critical failures.

## Failure modes

Expected failures include:

DistributedStateConflict

LeaseConflict

AIPolicyConflict

AISessionConflict

ReviewQueueConflict

SealReplay

AIIdempotencyConflict

ReleaseChannelConflict

These are control-plane safety signals.

Do not catch and ignore them.

## Retry policy

Retry only after reloading current state.

Blind retry with same expected revision is pointless.

Recommended pattern:

read

reconcile

derive new expected state

CAS

## Security invariant

A network partition, stale worker, or lost lease must not create additional
execution authority.

When coordination is uncertain, stop or require review.

Do not widen.
