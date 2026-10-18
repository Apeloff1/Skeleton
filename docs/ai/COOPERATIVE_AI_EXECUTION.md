# Operate cooperative AI responses

**Review and refine** is an opt-in response workflow inside the existing
canonical AI execution runtime. It asks configured models to produce a public
plan, a draft, an advisory critique and a refined answer under one original
request, source snapshot and resource grant. It uses actual provider calls;
it does not create another provider service, grant tool authority or train
model weights.

For installation and model readiness, start with
[first install and AI activation](FIRST_INSTALL_AI_AND_CRAWLER.md). For
source editing, simulation and measured game acceptance, use the separate
[measured builder-quality workflow](STUDIO_MEASURED_QUALITY.md).
A model revising an answer does not establish that it built or played a game.

## Enable review for a response

The chat control is **off by default**. Enable **Review and refine** before
sending the request. The default preset uses one critique/refinement round,
a 512-token stage ceiling and the configured selected model. Open **Advanced**
to choose one to three rounds, a 64–4,096-token stage ceiling, and an exact
available model for each role. The inventory shows current model capacities.
Unavailable selections remain visible and block a new send until corrected.
Changing settings performs no inference and does not activate providers.

The feature requires model readiness, sufficient context and at least 256 total
answer tokens for that four-stage preset. If unavailable, inspect readiness or
turn review off before sending a normal request. The UI does not silently
replace an unavailable reviewed response with an ordinary answer.

The saved request preserves its review choice and identities when resumed.
Changing a control for a future message cannot rewrite an already admitted
operation's policy, budget or conversation context.

## Policy schema and stages

The optional request `cooperation` value uses this schema:

```json
{
  "schema_version": "skeleton.ai.cooperation.v1",
  "review_rounds": 1,
  "max_stage_output_tokens": 512,
  "roles": {}
}
```

Omit the policy or use `null` to retain ordinary execution. The policy does
not replace the normal authenticated request fields, selected-model controls,
conversation version, idempotency key or operation resource grant.

| Setting | Behavior |
| --- | --- |
| `review_rounds` | Integer 1–3; defaults to 1 |
| `max_stage_output_tokens` | Integer 64–4,096; defaults to 512; a ceiling rather than a new grant |
| `roles` | Optional overrides for `plan`, `draft`, `critique` and `refine`; defaults to an empty object |
| Role override | Exactly `provider_id` and `model_id`, resolved against the configured scoped model inventory |

Stage order is fixed and sequential:

| Rounds | Stages | Minimum aggregate output allowance |
| --- | --- | --- |
| 1 | `plan`, `draft`, `critique:1`, `refine:1` | 256 tokens for 4 stages |
| 2 | Above, then `critique:2`, `refine:2` | 384 tokens for 6 stages |
| 3 | Above, then `critique:3`, `refine:3` | 512 tokens for 8 stages |

Each later critique addresses the latest draft/refinement. A refinement receives
the original brief, current public plan/draft, applicable critique and artifact
lineage. These are untrusted task artifacts, not new instructions, permissions
or evidence that a tool ran. The workflow requests concise public work products;
it does not request or expose hidden chain-of-thought.

An override can select a configured critique model, for example:

```json
{
  "schema_version": "skeleton.ai.cooperation.v1",
  "review_rounds": 1,
  "max_stage_output_tokens": 512,
  "roles": {
    "critique": {
      "provider_id": "<configured-provider-id>",
      "model_id": "<configured-model-id>"
    }
  }
}
```

Copy both IDs from the available inventory; the placeholder pair is not a
runnable model. Unspecified roles retain the primary selection. An override
applies to that role in every configured round. The same model may perform all
four roles. Different names or models do not certify independent review,
accuracy or improved quality. A matching activated local model digest is also
refused for independent semantic verification; a different digest alone does
not establish universal weight independence. Unknown fields and incomplete role selections
are refused.

## One budget across generation and verification

`max_stage_output_tokens` never multiplies the original operation's total answer
allowance. For a remaining stage, the runtime bounds output by its share of
remaining aggregate tokens, the policy ceiling and the actual selected
adapter/model output limit. Input/context, provider attempts, model turns,
cost and deadline also remain within the parent operation's existing grant.

Four stages with a 512-token ceiling do not automatically receive 2,048 tokens.
A 256-token total allowance permits only the minimum four 64-token reservations,
subject to all other readiness and admission checks. Increasing the number of
rounds requires enough original attempt/turn credits and output for every
remaining stage. A configured ceiling is not a promise that every stage will
use it or that the final answer will have that many tokens.

Context compilation fits the immutable request to the selected role models,
using the smallest applicable context capacity and finite space for generated
review material. Incompatible context, unavailable roles or exhausted budgets
produce an explicit error. The host does not discard source constraints,
widen model-selection or privacy policy, increase grants or truncate policy to
force the loop through.

The runtime reserves resources durably before dispatch. Known canonical usage
settles that reservation. Missing or estimated token usage remains charged
conservatively at the reservation; it is not treated as free unused capacity.
Unknown monetary usage also retains the applicable reserved cost rather than
inventing a bill. All subsequent stages and any required semantic verifier use
the same remaining parent ledger.

Leave sufficient grant for required verification as well as drafting. Meeting
the four-stage minimum does not guarantee that a separate semantic-verification
round can fit afterward. A local zero-cost route still consumes its finite
input/output, attempt and time allowances.

## Coherence and visible progress

The admitted execution freezes the policy, original brief, authoritative
conversation history, context digest and source snapshot. Checkpoints bind those
values to the immutable request. Generated artifacts retain their stage ID,
output/request digests and canonical provider/model receipt. Repeated receipts,
changed lineage and an override/model mismatch are refused.

The application presents completed stages only from recorded provider receipts.
A timer, a pending dispatch, a configured round count or a model saying
"finished" cannot advance the completed-stage count. The expandable response
record shows the actual participating models and output identities; when all
roles used one model, it says so. Saved-turn and progress projections must match
the canonical operation and its receipt prefix.

**4/4 stages recorded means the generation stages completed.** Final response
verification and canonical conversation publication remain separate. A complete
cooperation record cannot turn a blocked, abstained or failed final result into
a verified successful answer. Plans and drafts do not become extra canonical
assistant messages or completed game-building actions.

## Final verification remains a separate gate

The final refinement is a candidate for the existing canonical **Stage-3
verification and finalization** boundary. The cooperation policy does not
weaken that boundary. Normal tool/evidence/postcondition rules still determine
the applicable claim and verification requirements.

Where policy requires semantic verification, the existing semantic verifier
runs through the canonical runtime under the parent's tenant, source context,
provider admission, deadline and resource ledger. It is not an unmetered child
operation with a fresh budget. Its own structured verdict, limited repair
rounds and evidence checks remain distinct from the advisory `critique` role.

The verifier's configured provider/model routes must not overlap the primary
generator or any participating cooperation-role route. The runtime refuses such
overlap rather than counting self-review as independent semantic verification.
Selecting a separate critique model alone neither configures nor satisfies this
verifier requirement. Route separation also does not establish independent
training data, human review, legal clearance or superior game quality.

The final verification result can block, qualify or abstain according to its
existing policy. Only the existing finalization owner can publish the canonical
result. A model's positive critique and `independent_review_certified: false`
progress record are never substitutes for that authority.

## Interruption, retry and recovery

Keep the saved turn's operation identity, request key and source context when
joining or resuming admitted work. Inspection or reconnecting is not a new
model-call authorization. Cancellation, expiry and exhausted grants do not
replenish credits or silently change the saved policy.

A durable dispatch reservation without an observed response has an **uncertain
physical outcome**: a provider may already have consumed work. Recovery refuses
to dispatch that same turn again automatically. Inspect the canonical state
before explicitly deciding whether to authorize a separate operation. An absent
response is not proof that nothing ran or that another attempt is free.

For semantic verification, an observed bounded response is stored with its
request binding, fingerprint and settled usage before its verdict is parsed.
When an admitted recovery can reuse that response, it checks the exact stored
request/response identities and reparses it without another provider call or a
second usage charge. Even an invalid verdict has consumed physical work and
remains accounted for. Corrupt, mismatched or missing durable material is an
explicit failure, not a reason to invent a successful review.

## Relation to the game studio and current evidence

This response loop improves the structure of a model-assisted attempt; it
cannot guarantee subjective answer or game quality. The
[measured builder-quality loop](STUDIO_MEASURED_QUALITY.md) separately edits and
executes actual game sources, freezes a reference workload, measures candidate
behavior and blocks observed regressions before packaging. Source proposals,
job receipts, approved Dragon references and training permissions retain their
existing owners.

The local workbench's
[deterministic triad](../JEEVES_APP_CAPABILITY_ATLAS.md#understand-triad-and-model-readiness)
is another distinct operation: role labels there do not mean these model calls
ran. None of these features silently activates external cloud inference,
changes installed transformer weights or promotes a training candidate.
Configured inference continues through the canonical engine/provider boundary
and its existing privacy, cost and authority policy.

This guide describes implemented contracts and operator behavior. It does not
assert that final release, multi-model, restart, semantic-verification or
long-duration operations passed. Consult source/model/budget-bound release
evidence for completed observations; retain new results separately when those
identities change.
