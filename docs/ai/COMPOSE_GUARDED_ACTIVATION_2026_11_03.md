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
   and an authoritative `TrustedSnapshotReader`. Review the reviewer's
   trust domain and isolation from the model. Bind actual loaded native
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

## Deterministic focused test

`python -m unittest skeleton.testing.test_compose_guarded_activation`

The fake Mongo unit tests prove state transitions and error handling only.
They do not substitute for real replica-set behavior, independent reviewer
administration, exact-head CI or a tested laptop install.
