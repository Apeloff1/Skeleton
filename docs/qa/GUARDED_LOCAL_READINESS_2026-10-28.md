# Guarded local inference readiness — 2026-10-28

# Later status (2026-10-31)

The historical findings below describe the October 28 candidate. Current main
requires the local guard by default, but the default Compose engine startup does
not supply its trusted bootstrap dependencies. Local inference therefore fails
closed; the setup instructions cannot yet activate it. Production qualification
still needs trusted state authorities, a bounded independent reviewer and
tokenizer attestation tied to the activated GGUF backend.

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
