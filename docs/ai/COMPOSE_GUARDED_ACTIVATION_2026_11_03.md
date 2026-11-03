# Studio C — guarded native activation on Compose (2026-11-03)

**State: implementation WIP, NOT consumer-qualified.** The default Compose
configuration currently uses a standalone MongoDB container. A standalone
`mongod` cannot satisfy the canonical source epoch's **linearizable**
read concern. The safe default is therefore **AI unavailable**, not a
guard-disabled fallback. Existing volumes MUST NOT be converted automatically.

## What the new code does

`MongoGuardedActivation` is an explicit startup state machine
(`blocked -> verifying -> active`, with terminal local `revoked`).
It requires the same database object that constructed
`MongoCanonicalSourceEpoch`, a primary-backed replica set, an already
provisioned stable actor epoch, and the installed canonical conversation and
memory writer inventory. It binds the exact native transformer backend,
runtime and tokenizer digests. It receives a reviewer from the trusted
application root rather than from model output, prompts or request metadata.
The trusted root must also pin a `ReviewerTrustAnchor` containing an
Ed25519 public key, authority ID and deployment domain. Every activation
and pre/postflight check sends a fresh nonce challenge to the reviewer
signing client. The signed payload binds canonical scope, epoch and exact
model/runtime/tokenizer digests. The epoch is read linearly again after
attestation to reject a writer entering WRITING during the reviewer round trip.
A valid signature proves key possession only, NOT independently audited
reviewer isolation or policy correctness. Never place a private reviewer
signing key in the application, Compose environment, or repository.

`compose_mongo_guarded_native_adapter` constructs the native backend,
performs explicit activation, and creates the canonical guarded service with
an activation permit. Each protected generation checks the permit before
source reads, both before and after the pre-dispatch authority read, and again after
generation before returning the answer. Any changed epoch, model, tokenizer,
Mongo authority outage or local revocation
blocks release. A stable epoch advance is NOT implicitly accepted: the
operator must re-establish the binding and explicitly activate again.

This is a **guarded native transformer** path, not a generic GGUF or Metal
attestation. It does not prove any model has been downloaded, that weights
are suitable, that the machine can execute them, or that an adversarial
reviewer is actually independent merely because it is callable.

## Operator prerequisites (manual, no migration automation)

1. Stop canonical conversation and memory writers. Back up the existing
   authenticated Mongo data and verify restoration on an isolated copy.
2. Plan and execute an operator-approved replica-set migration with MongoDB
   maintenance procedures. Verify primary election, majority durability,
   client retry behavior and an authenticated linearizable read. Do not
   change a running standalone volume by merely adding `--replSet` to
   Compose. Do not infer qualification from `hello` alone.
3. Provision the actor epoch using the separately audited, quiescent
   `provision_migration_epoch` procedure. Never provision on inference
   request paths. Reconcile preexisting prepared writes, deletion custody,
   memento witness state and external writer inventory before provisioning.
4. Install the SAME epoch instance on both
   `MongoConversationAuthority` and `MongoMemoryRepository`, and verify
   all known entrypoints with
   `verify_canonical_source_writer_inventory`. The activation probe now
   verifies that the epoch collections, conversation threads/messages and
   memory collections all belong to the SAME Mongo client and logical
   database. The default Compose backend and engine currently configure
   different logical database names; merely pointing both at the same
   Mongo server is not enough. Reconcile the canonical owner deployment
   explicitly before activation. Separately audit other services, direct
   Mongo clients, backups, migrations and maintenance scripts; in-process
   inventory cannot fence an unknown external writer.
5. Construct an independently administered `BoundedAdversarialReviewer`
   and an authoritative `TrustedSnapshotReader`. Provide a pinned
   `ReviewerTrustAnchor` and async `attest_challenge(payload)` method
   on the reviewer client backed by a separately administered signer.
   Audit the signing-key isolation, reviewer trust domain and separation
   from model execution. Bind actual loaded native
   model, runtime and tokenizer digests from the backend, never from a
   user request or unchecked environment variable.
6. Invoke the explicit async composition factory only after all checks
   pass. Do not expose a route to the unguarded `LocalInferenceEngine`
   for protected traffic. Keep the UI accessible with a truthful
   `local_ai_unavailable` status while this is incomplete.
7. Validate real restart and revocation on a production-equivalent
   replica set. Verify that a writer in `writing`, an unprovisioned actor,
   stale epoch, changed tokenizer, changed reviewer authority, lost
   primary, cancelled request, failed witness and unavailable disk
   custody cannot release an answer.

## Remaining security/release holds

The epoch is a majority-durable seqlock over known writer entrypoints,
**not** a distributed transaction or a physical Mongo permission fence.
A writer that bypasses the registered owner can still mutate canonical
collections. Operators must restrict database write roles and verify all
services share the same writer authority. The opt-in `MongoCanonicalSourceEpoch.revoke_actor` now provides an
operator-authorized, majority-durable CAS from a known STABLE even epoch
to a terminal REVOKED odd epoch. It does not preempt a WRITING owner:
the operator must reconcile that writer before a safe revocation.
Its authorization callback must be injected by the trusted application
root, never from a request. `MongoGuardedActivation.revoke()` is a
separate local irreversible hold. Cross-process revocation is observed
at the next linearizable epoch check; it is not instantaneous physical
writer termination, nor can an already delivered answer be recalled.

The guard's final read precedes network delivery; there is no claim of
atomic publication against an independently racing writer. No automatic
recovery of an odd/writing epoch is permitted. Crash recovery requires
operator reconciliation of partially committed source writes, WAL and
sealed memento custody before explicit reactivation.

This patch does not modify the default Compose Mongo service, enable AI
by default, add credentials, or perform a consumer migration. Studio D
should expose the unavailability reason without hiding the setup UI.
Before release, run focused tests, full exact-head security/CI, a real
authenticated Mongo replica-set integration drill, cold-start/restart,
writer collision/revocation, native tokenizer mismatch and first-run
Windows/WSL2 evidence. No skipped, stale or pending gate is a pass.


## Read-only backend preflight for Studio D

From the backend container, with its existing authenticated `MONGO_URL`
and `DB_NAME`, set operator-selected `SKL_CANONICAL_TENANT_ID`,
`SKL_CANONICAL_ACTOR_ID` and `SKL_CANONICAL_CONTEXT_ID` in the private
process environment. Run:

`python -m skeleton.app.compose_guarded_preflight`

This command only issues Mongo `hello` and a bounded linearizable epoch
read. It emits a fixed-schema, credential-free JSON result. Exit 0 means
**only** that the Mongo actor epoch preflight was observed stable; the JSON
always retains `guarded_local_ai_ready=false` because the command does
not establish full writer inventory, reviewer trust, model/tokenizer
activation or device readiness. Exit 2 indicates the Mongo preflight did
not pass. It never provisions epochs, creates indexes or migrates volumes.
Studio D can surface the fixed `code` without leaking credentials or
inventing an activated model.

## Deterministic focused test

`python -m unittest skeleton.testing.test_compose_guarded_activation skeleton.testing.test_compose_guarded_service skeleton.testing.test_mongo_epoch_revocation skeleton.testing.test_compose_guarded_preflight skeleton.testing.test_reviewer_custody`

The fake Mongo unit tests prove state transitions and error handling only.
They do not substitute for real replica-set behavior, independent reviewer
administration, exact-head CI or a tested laptop install.

## Independent reviewer transport (operator-owned)

`SignedReviewerClient` supplies bounded HTTPS review and challenge calls
with a trusted-root hostname-validating TLS context. The review service must
sign its verdict and the activation challenge with the SAME separately held
Ed25519 key. Review responses bind a fresh nonce and exact untrusted text
digest. Redirects, ambient proxies, unsigned or oversized responses are
denied. Operators must separately deploy and audit the actual reviewer
service, its key custody, policy, mTLS, availability and isolation. This
client does not make default Compose consumer-ready.

Focused transport test: `python -m unittest skeleton.testing.test_signed_reviewer_client`.

## Explicit operator migration authorization

`MongoCanonicalSourceEpoch.provision_migration_epoch` now denies all calls
unless the trusted application root supplies an async `migration_authorizer`
that explicitly approves the tenant, actor, canonical logical database and
`quiescent-initial-epoch-v1` purpose. Only a literal `True` is accepted;
exceptions, timeouts, missing authority, and duplicates fail closed. This
is an authorization boundary, not a proof that external writers have stopped
or that a backup has been restored. The operator must independently verify
those conditions before approving. No Compose startup path provisions epochs.

Focused test: `python -m unittest skeleton.testing.test_mongo_epoch_migration_guard`.

Initial actor epoch provisioning also refuses standalone Mongo, a secondary,
or a malformed/failed primary probe before requesting operator approval.
This is a read-only probe and does not modify Compose or initialize a replica set.

## Opt-in real replica-set custody drills

`python -m unittest skeleton.testing.test_mongo_epoch_live_replica` requires
`SKL_TEST_MONGO_URI` pointing to an operator-provisioned authenticated
replica-set primary and `SKL_TEST_MONGO_ALLOW_DROP=1`. Tests create unique
`skeleton_ci_guard_*` logical databases and delete only those newly created
databases. They cover majority initial epoch, linearizable reads, writer
collision, WRITING quarantine across restart and terminal revocation.
Without explicit test authority, tests SKIP and cannot be counted as passes.
They do not deploy a replica set, migrate Compose, or certify consumers.

## Majority-CAS mutation deadlines (2026-11-03)

Every canonical epoch mutation (initial provisioning, writer admission,
writer completion and operator revocation) now has a bounded local wait.
A deadline is **not** proof that Mongo rolled the operation back: the server
may have committed just before the caller timed out. No timed-out operation
is retried automatically. A writer completion timeout leaves the actor
unavailable unless an independently audited operator reconciles the actual
majority-durable epoch and source writes. Admission and migration timeouts
also have ambiguous outcomes and must never be followed by blind replays.

Focused regression: `python -m unittest skeleton.testing.test_mongo_epoch_operation_deadlines`.
The simulated deadline tests do not prove real replica-set semantics.
