# Guarded local inference readiness — 2026-10-28

# Later status (2026-11-02)

The initial review covered the October 28 candidate. The current source
requires the local guard by default, but the default Compose engine startup does
not supply its trusted bootstrap dependencies. Local inference therefore fails
closed; the setup instructions cannot yet activate it. Production qualification
still needs trusted state authorities, a bounded independent reviewer and
tokenizer attestation tied to the activated GGUF backend.

## Default Compose integration gap

The current deployment cannot be activated by supplying only a guard object.
The backend's global `MongoConversationAuthority` is created without a source
epoch. The engine's `MongoMemoryRepository` is created separately. Compose
uses the backend core database selected by `DB_NAME` (default `tutolage`) and
the engine database selected by `SKL_MONGO_DATABASE` (`skeleton` in Compose).
The services therefore need an explicitly shared epoch collection and must
retain their existing data in their respective databases. Merely constructing
another epoch in the engine cannot fence the backend's live writers.

The known-writer verifier imports `core.conversations`, but the engine image's
`Dockerfile.dockerignore` includes only engine source and contracts, excluding
the backend module. Production composition needs a declared owner boundary and
an authenticated way to establish backend writer custody; copying the backend
into the engine or relying on a test-only import path does not establish that
boundary. The verifier checks known in-process entrypoints and cannot certify
other deployments or direct database writers.

An actionable migration must be designed and qualified in this order:

1. Declare the shared epoch authority and backend-to-engine custody interface in
   the canonical architecture. Bind both processes to the same verified Mongo
   deployment and epoch collection, independently of their source databases.
2. Inventory every conversation and memory writer, including old service
   versions and administrative clients. Enforce the epoch on each admitted
   mutation and restrict unregistered writers at the deployment boundary.
3. Under a verifiable quiescent maintenance window, inventory tenant/actor
   identities from both canonical stores, preserve existing data, and initialize
   missing epoch records through an auditable, restart-safe migration. Existing
   writing, malformed, or uncertain records must be quarantined for separate
   reconciliation; never reset them automatically. A read-only snapshot or a
   caller's assertion of quiescence is not proof that all writers are stopped.
4. Install an independently managed bounded reviewer, pinned instruction policy,
   authorized snapshot reader and tokenizer bound to the actual loaded backend.
   Wire the trusted bootstrap before provider activation, without any request or
   environment-controlled opt-out from the guard.
5. Qualify fresh install, upgrade, mixed-version exclusion, interruption and
   recovery, concurrent mutation, revocation, and restart behavior using real
   Mongo and both application processes before enabling the path by default.

No automatic epoch initialization, bulk repair, database migration or cross-
process writer enforcement is provided by the current Compose startup.

The local provider requires the sealed-context guard. Its trusted dependencies
are available only through explicit trusted application composition.
**Docker Compose and the Dockerfile do not supply the required trusted
bootstrap**, so the default local provider remains unavailable. Installing
weights or observing a healthy engine process does not qualify protected local
inference.

Guarded activation requires a pinned canonical instruction digest, canonical
Mongo conversation and memory owners sharing a majority-durable source epoch
with primary-bound linearizable reads,
an authorized per-execution snapshot reader, an independently administered
bounded reviewer, and a tokenizer tied to the exact activated native model.
The application owner must install these before engine startup via the trusted
bootstrap accepted by `skeleton.api.server.create_app`. The existing native
binding helpers do not themselves provision those independent authorities.
The registry and deployment activation paths also require integration of the
tokenizer binding with the same backend instance they create; a generic GGUF
CLI tokenizer cannot be assumed to satisfy this identity requirement.

The guard fails closed when its trusted components are missing. Production
composition still needs end-to-end qualification. The default standalone Mongo
service cannot provide the linearizable epoch reader; there is no fallback to a
potentially stale majority snapshot. Moving to a replica set requires a separate
qualified migration that preserves existing source data and writer custody.

Generic transfer-policy and admission decision identifiers can be present for
legacy local inference. They are not evidence of a sealed-context review or a
native execution receipt.

Asynchronous guarded generation bounds the independent reviewer and native
verification/preparation callbacks with separate single daemon-worker slots per
guard. Each has a five-second default timeout capped by the caller deadline.
A timed-out or cancelled worker keeps its slot until the underlying call
returns; Python cannot forcibly stop it or safely reuse its occupied capacity.
The initial, pre-dispatch and final source reads use same-task asynchronous
timeouts, preserving the authority owner's task identity. Source reads and
delivery checks still do not constitute an atomic cross-process revocation
fence. Multi-model catalog activation and exact native tokenizer bindings
require production qualification. Native child-process failure messages no
longer expose raw stderr that may contain prompt text.

Existing checkpoints that only contain the older `local_provider_binding`, or
no provider binding, do not establish the newer route, verifier, cooperation
and tenant identities. Unfinished work that would need execution therefore
fails closed after upgrade rather than reconstructing an unverifiable binding.
Committed results remain readable. Cancellation, deadlines and unresolved
approvals can be recovered without an available provider; approved tool work
and staged results remain retained until the original provider can be checked.
A staged result is never treated as an already committed result. If admission
completion fails after a terminal result commits, current maintenance scans
nonterminal executions and does not independently retry completion; a durable
completion outbox or equivalent reconciliation remains required.


## Candidate guarded Mongo observation (2026-11-16)

For an already running, operator-provisioned replica set and an explicitly chosen
existing shared epoch database, each deployed service can perform a read-only
observation using its own existing credentials. Keep the backend's application
database and the engine's memory database separate; this command does not rename,
move, copy, initialize or modify either. It does not establish writer fencing.

Supply a private UTF-8 JSON file outside the repository containing exactly
"tenant_id", "actor_id", and "context_id" string fields (at most 4096 bytes).
Use the same intended actor scope and existing epoch database in each command.
For example, from the repository root on a configured Docker host:

    docker compose exec -T backend python -m skeleton.app.compose_guarded_preflight --source backend --shared-epoch-database canonical_witness --scope-stdin --summary < /private/actor-scope.json
    docker compose exec -T skeleton python -m skeleton.app.compose_guarded_preflight --source engine --shared-epoch-database canonical_witness --scope-stdin --summary < /private/actor-scope.json

Replace the illustrative witness database name and file path with the actual
operator-provisioned ones. The app CLI also exposes the same command as
"python -m skeleton app mongo-preflight". There is no credential in argv, no
automatic provisioning, and no raw Mongo response or actor identity in output.
An independently observed single-source stable epoch is not evidence that the
two services share the same physical cluster, writer authority or policy. Both
commands deliberately return 2 even when an observation is complete; they are
not an activation or service-readiness check. Existing database backup,
authenticated replica configuration, quiescent migration, independent reviewer,
pinned policy and exact active model/tokenizer custody remain mandatory.
