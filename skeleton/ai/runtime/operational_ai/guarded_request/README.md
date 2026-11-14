# Guarded request and native capacity integration (AI-only)

This additive package is a security and capacity ingress for Skeleton's
actual local OfflineAIService, not a model, training pipeline, game engine,
or hosted-provider fallback.

## Operational order

1. Bind tenant, user, session and model digest before accepting requests.
2. Verify supplied model and tokenizer digests; never download implicitly.
3. Validate strict JSON, resource pressure and bounded input/output budgets.
4. Admit into an in-process tenant-fair queue. The existing native engine,
   OfflineChatStore, process fence and journal remain authoritative.
5. Require explicit caller grants for read-only tools; model text cannot grant.
6. Attach source digests and exact byte offsets to retrieved evidence.
7. Fence streaming output and durable external-effect intents.
8. Run the 384-case acceptance matrix before separate device and CI review.

## Invocation

Construct GuardedDispatcher(existing_offline_ai_service) only after the
actual local checkpoint is activated and the existing service is bound
to the tenant/user/model. Submit NativeRequest(Scope(...), request_id,
question) with a freshly measured Pressure sample. Call drain_one()
to invoke actual OfflineAIService.turn and return its real durable receipt.
No stubbed model is available on this production path.

Run: python -m skeleton.ai.runtime.operational_ai.guarded_request.cli

FairQueue is in-process only; authoritative session fencing is elsewhere.
Effect receipt reconciliation must use independently verified effects.
Credential redaction is not a complete DLP guarantee. Context byte limits
are not substitutes for native tokenizer checks. Actual 1.9 GB licensed
model bundle, clean-install, real generation, exact-head security CI and
independent release qualification remain held.
