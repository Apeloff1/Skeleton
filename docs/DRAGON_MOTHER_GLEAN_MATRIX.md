# Mother Dragon Glean Matrix — evidence first (2026-10-12 UTC)

**Status:** branch-level implementation and targeted regression tests. This is
not a production crawler, not an independent fact oracle, not automated AI
training, not an authorization to use third-party content, and not a deployment
claim.

## Existing canonical graph

```text
Existing research producer (owner-scoped, human-reviewed source evidence)
  ├─ Ember: articles ──┐
  ├─ Flicker: videos ──┼─ verified Dragon Family revisions
  └─ Scout: recrawls ──┘          │
                                  ▼
                          Mother Glean Matrix
                                  │
                 ┌────────────────┼────────────────┐
                 ▼                ▼                ▼
             corroborated     contested         solitary
             2+ sources       disagreement      one group
                 │                │                │
                 ▼                ▼                ▼
          independent Wiki    recrawl brief      seek separate
          proposition review  (not a fetch)     evidence group
                 │
                 ▼
          Wiki-reviewed individual source revisions (Almanakk)
                 │
                 ▼
          shadow candidate *queue*, never weights
                 │
                 ▼
          separate sandbox holdout > model-owner signed promotion workflow
```

## Implemented features

- **23 bounded domain lenses**: game mechanics, game AI, narrative, world
  design, level design, balancing, accessibility, user experience, retention,
  portability, native hardware, performance, reliability, security,
  provenance, copyright, licensing, economics, production, testing,
  adversarial reasoning, competitive insights, and adjacent transfer.
- **Claim and citation custody**: every `LensObservation` requires the
  latest canonical content SHA-256, a proposition SHA-256, a quote/timecoded
  anchor SHA-256, a source ID, an independent publisher/group identity,
  a supporting/challenging stance, confidence bound, UTC observation, and a
  bounded reviewer explanation. Neither topic tags nor LLM text alone produce
  a fact. Both the source evidence review and the independent proposition/
  anchor callback are rechecked before SQLite commit.
- **Novelty and triangulation**: duplicate evidence anchors cannot be farmed;
  different anchors on the same source cannot create two independent source
  votes; separate sources owned by the same independence group are not
  sufficient corroboration. The caller's independent reviewer is responsible
  for confirming group independence rather than accepting a user-provided
  group string at face value.
- **Source freshness**: when a source revision changes or canonical consent
  is revoked, the original glean is removed from active correlation without
  erasing its history. Previously queued shadow candidates become stale and
  require new Wiki review.
- **Conflict detection**: a current challenge prevents promotion even when
  two independent sources support the proposition. The UI shows a contested
  hypothesis and a reason to search for counterexamples.
- **Cross-media gleaning**: article and video evidence can corroborate or
  contradict a common proposition without allowing one child to forge the
  contributions of another.
- **Rule matrix**: IF/AND/OR/BUT research briefs distinguish (a) conflicting
  evidence, (b) independent Wiki candidates and (c) missing independent
  sources. Each brief carries source IDs, evidence fingerprint, lens, role
  suggestions, review requirement and explicit `permits_network=False` /
  `permits_weight_promotion=False`.
- **Shadow preparation without promotion**: a queued proposition requires
  two distinct reviewed sources, two independent groups, no opposing
  evidence, individual Wiki-verified source revisions in Almanakk, plus a
  separate independent Wiki proposition reviewer. Queue entries are version
  bound, replay-idempotent and automatically stale on source changes.
  A shadow proposal is not evidence of measured performance gain.
- **Reviewable historical ledger**: immutable source observations,
  hash-chained review events, UTC timestamps, owner fencing, event budgets
  and parenthesized `(gleaned: ...)` explanations. Tampered history fails
  verification rather than silently displaying fictional discoveries.
- **Product exposure**: the authenticated Dragon Academy status response
  includes a bounded read-only `family.glean` projection; the actual
  Jeeves Dragon Family nest displays hypothesis counts, disagreement,
  evidence lenses, last observation, provenance freshness, and verified
  source-group counts. A UI or HTTP caller cannot submit a glean, award XP,
  create new model weights, or trigger a crawler.

## Producer integration

```python
from skeleton.ai.webcrawler.dragon_family_custody_bridge import DragonFamilyCustodyBridge
from skeleton.ai.webcrawler.dragon_family_glean_matrix import LensObservation

bridge=DragonFamilyCustodyBridge(canonical_sqlite_connection,authenticated_owner)
mother=bridge.glean_matrix(finding_verify=independent_review_of_exact_claim_and_anchor)

# Exact source revision must already exist in the canonical reviewed ledger;
# source_id, content_digest and anchor_digest come from the actual source.
mother.record(authenticated_owner,reviewed_lens_observation,authorized=True)

# Pure research intent. A separate policy-bound crawler planner decides if
# any actual work is permitted, and only during trusted device idle.
briefs=mother.research_briefs(authenticated_owner,authorized=True,limit=20)

# No client or single LLM's approval may sign the Wiki decision.
candidate=mother.queue_shadow_candidate(
    authenticated_owner,"game_mechanics",proposition_digest,
    authorized=True,at=current_epoch,
    wiki_claim_verify=independent_wiki_proposition_review,
)

# Neither of these does a model update:
queue=mother.shadow_queue(authenticated_owner,authorized=True)
view=mother.projection(authenticated_owner,authorized=True)
```

## Operator-gated completion remaining

1. Implement and independently validate real claim/anchor verifiers over
   captured article spans and timecoded video observations (the module
   rejects admission without this callback). Include publisher-independent
   evidence lineage and adverse-source checks.
2. Feed conditional research briefs through the existing mission scheduler
   with live host policy and crawler budgets; never auto-fetch in UI/read
   routes. Keep robots, redirect DNS, SSRF, terms, rights, consent, and
   device-idle rules at each actual dispatch.
3. Wire actual human or institutionally independent Wiki proposition review,
   and then a separate held-out model-performance evaluator on real game
   building projects, followed by a signed model-owner promotion gate.
4. Verify and qualify precision/recall/false-corroboration rates against
   adversarial holdouts, including cloned publications, mirrors, stale video
   transcripts, timestamp rollback, permission revocation and source
   disagreement.
5. Recheck existing App Assembly AI shell-tree mirror failures and remaining
   unrelated Dragon regression failures separately; no branch merge until
   required gates are green.

## Verification

```bash
pytest -q tests/test_ai_webcrawler_dragon_family_glean_matrix.py
pytest -q tests/test_ai_webcrawler_dragon_family_custody_bridge.py
cd frontend && node scripts/test-dragon-progression.cjs && ./node_modules/.bin/tsc --noEmit
```

Regression coverage asserts that an empty system has no synthetic insights,
independent sources outrank duplicate documents, challenges force scrutiny,
revoked evidence disappears from active hypotheses, a new content revision
invalidates an older observation, unapproved anchors are refused, wrong-tenant
access fails, shadow proposals require Wiki review and become stale, and
tampered audit records are detected. CI results must be checked at the exact
current commit; these instructions are not themselves evidence of tests passed.
