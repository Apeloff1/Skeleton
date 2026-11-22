# First-install guarded authority diagnosis

This review-only candidate recovers the protected inference composition and
Mongo epoch source boundaries. It does not make a standalone Mongo instance
authoritative or activate any model. The normal setup and application doctor
remain independent of this operator-only diagnostic.

## Read-only operator command

From an already configured, trusted backend process environment:

```sh
python -m skeleton app guard-preflight
```

The command uses the existing process environment only: MONGO_URL, DB_NAME,
SKL_CANONICAL_MONGO_DATABASE and explicit SKL_CANONICAL_TENANT_ID,
SKL_CANONICAL_ACTOR_ID, SKL_CANONICAL_CONTEXT_ID. Do not paste secrets in shell
commands, logs or issue reports. No default scope, database-name substitution,
credential acquisition, automatic Mongo migration or provider launch occurs.
Run it only from the intended trusted environment with those variables already
provisioned; the existing Compose defaults are insufficient.

It returns a bounded JSON observation with fixed reason codes and always exits
2, including for a completed stable epoch observation. It does not authorize
activation. For detailed raw bounded observations, the existing module
`python -m skeleton.app.compose_guarded_preflight` remains available with the
same nonzero exit behavior.

## Interpret blockers before proceeding

- `operator_actor_scope_required`: explicitly select an existing scoped actor
  and context; do not manufacture data or borrow another identity.
- `canonical_engine_database_identity_required` /
  `canonical_database_identity_mismatch`: inspect both actual configured
  authorities. Name equality is not cluster or writer identity.
- `mongo_replica_set_primary_required`: a standalone or ambiguous topology
  cannot provide linearizable reads. Do not edit existing volumes blindly.
- `mongo_authenticated_session_required`: authenticate the intended authority;
  never weaken Mongo protection or retry using an anonymous principal.
- `canonical_actor_epoch_unavailable` / epoch changed errors: preserve source,
  reconcile outstanding writes through audited authority recovery.
- `mongo_epoch_observed_only`: bounded observation completed. All activation
  flags deliberately stay false.

## Remaining deployment obligations

Independently qualify authenticated replica-set provisioning and migration,
writer fencing at every canonical source owner, pinned independent reviewer
service, actual native model/tokenizer binding, trusted server bootstrap,
clean Docker composition, Windows/WSL2 installation and real GGUF inference.
The review-only source tests do not establish any of those physical results.
Do not set AI_LOCAL_GUARD_REQUIRED=0 to satisfy a local inference test.
