# Jeeves delivery assurance: comparative, objective, copyright, rewrite

The release gate is host-controlled. It is not a legal opinion, a blanket
copyright clearance, or a claim that unconfigured external scanners ran.

## Ordered steps

1. Keep the original user request and authoritative evidence. Compact scoped
   negative searches into retained working notes with hash-linked serials.
2. Perform two independent context/claim verifiers and challenge both with a
   separate adversarial reviewer.
3. For code and games, require a verified-clean release from syntax compilation,
   lint, code review, error searches, tests, modularity, efficiency, performance,
   cleanliness, maintainability, and machine-friendly code reviews.
   Game deliveries also require independent gameplay, asset, and performance
   checks. Corrections trigger repeated complete checks until two clean,
   stable passes. Exhausted/blocked work is explicitly reported, never released.
4. Comparative review: each quality axis compares the candidate to a grounded,
   identified benchmark using the same units, method and direction, with source
   references for both sides, sample counts and explicit regression tolerance.
   A pairwise score is not an industry-wide ranking.
5. Objective review: each axis must meet a sourced minimum threshold. If the
   measured target is not met, the release is blocked even if the candidate is
   better than the prior version.
6. Copyright and provenance review: cover every delivered source/artifact and
   the precise final user-facing answer. Capture origin, current source hash,
   rights/permission evidence, license/attribution conditions and the actual
   checker scope. Unknown origin, uncovered sources or rights uncertainty block
   the clean label. A failed corpus lookup does not prove universal originality.
7. Creative-rewrite review, LAST: an independent reviewer checks substantive
   transformation rather than surface-level synonym substitution, protected
   expression similarity, consistency with signed GDD/canon and the user's
   voice, asset/dialogue coherence, original creative contribution, permissions
   and license/attribution requirements. Rewriting alone never grants rights.

Steps 4-7 have hash-linked sequential serials named
JVR-000001-P000001 through JVR-000004-P000004. The final two checks execute
in the fixed order copyright then creative_rewrite.

## Host integration

AdaptiveJeevesRuntime.register_delivery_quality attaches code/game source
readers, actual checker callbacks and optional authorized repair adapters.

AdaptiveJeevesRuntime.register_final_review attaches the exact source and
user-visible answer reader, measured criteria reader, provenance reader,
independent copyright checker and independent creative rewrite checker. Source
readers must include the exact final answer under
delivery/jeeves_final_answer.md; they must include all code assets covered by
the previous quality stage. For code and games both registrations are mandatory.
Creative writing requires the latter final review stage.

The final reviewers must return ContentReviewResult with bound source hash,
all reviewed paths, checker identity, evidence ref, scoped search description
and typed pass/fail with findings. Copyright and rewrite checkers must be
different callbacks with different evidence and checker identities.

A separate verifier-of-final-reviewers attacks source digests, provenance,
objective metrics, checker decisions and serialized receipt order. All
mutations must be rejected before a verified clean delivery is authorized.

## Evidence boundaries

The host must wire real syntax/lint/test tools, performance benchmarks,
licensed-source catalogs, source-similarity checks and canon review. Merely
registering a callback is not proof that external data was reviewed.
Attribution for legitimate licensed assets must be preserved. Rights and legal
questions needing human judgement remain clearly unresolved rather than
being overstated as either infringement or clearance.

Use the existing Backend Quality CI gate for syntax and the four focused
regression suites: working context, adversarial verifiers, code delivery
quality and final copyright/creative release. This adds no standalone gate.
