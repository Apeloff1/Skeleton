# Guarded local inference readiness — 2026-10-28

# Later status (2026-10-31)

The historical findings below describe the October 28 candidate. Current main
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

The sealed-context guard is available only through explicit trusted application
composition. The normal local provider path does not enable this protection by
default. **Docker Compose and the Dockerfile do not supply the required trusted
bootstrap**, so this deployment must not be described as protected local
inference or certified as satisfying the sealed-context guard contract.

Guarded activation requires a pinned canonical instruction digest, canonical
Mongo conversation and memory owners sharing a majority-durable source epoch,
an authorized per-execution snapshot reader, an independently administered
bounded reviewer, and a tokenizer tied to the exact activated native model.
The application owner must install these before engine startup via the trusted
bootstrap accepted by `skeleton.api.server.create_app`. The existing native
binding helpers do not themselves provision those independent authorities.
The registry and deployment activation paths also require integration of the
tokenizer binding with the same backend instance they create; a generic GGUF
CLI tokenizer cannot be assumed to satisfy this identity requirement.

An explicitly required guard fails closed when its trusted components are
missing. That behavior and the opt-in protected path do not prove the default
installation is protected. Enabling the guard by default before the real
authorities are configured would disable local inference, not complete the
security integration. The existing regression expecting mandatory default-on
remains a release blocker until the production composition is implemented and
verified end to end.

Generic transfer-policy and admission decision identifiers can be present for
legacy local inference. They are not evidence of a sealed-context review or a
native execution receipt.

Guarded generation now bounds the independent reviewer to one daemon worker
per guard, with a five-second default timeout capped by the caller deadline.
A timed-out worker keeps its slot until the underlying call returns; Python
cannot forcibly cancel it. The canonical service re-reads its source before
dispatch and again before delivering output. Those reads do not provide an
atomic cross-process revocation fence. Tokenizer and renderer calls remain
synchronous and unbounded; multi-model catalog activation and exact native
tokenizer bindings also require production qualification.

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
