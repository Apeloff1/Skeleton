# Guarded local inference readiness — 2026-10-28

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

The current reviewer and tokenizer calls run synchronously on the event loop;
the protected route does not yet enforce an independent resource or time
limit around those calls. Multi-model catalog activation and its exact native
tokenizer bindings also require production qualification.

Existing checkpoints that only contain the older `local_provider_binding`, or
no provider binding, do not establish the newer route, verifier, cooperation
and tenant identities. Unfinished work that would need execution therefore
fails closed after upgrade rather than reconstructing an unverifiable binding.
Committed results remain readable, cancellation and deadline termination are
preserved when the configured provider is available, and an unresolved approval
can remain observable without executing its tool. Approval does not authorize
resuming unbound work. A staged but uncommitted result remains subject to the
provider binding check; it is not treated as an already committed result.
