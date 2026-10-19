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


## Continuous release evidence journal (October 2026 milestone extension)

A host-side release journal joins the already existing source-verification
planes into one content-addressed, replayable delivery handoff. It is produced
only after the live runtime obtains verified host results; registering checkers
or preparing a design does **not** constitute release evidence.

The journal enforces these milestones as executable contracts:

1. A unique run identifier, unchanged user goal and policy metadata.
2. Complete, scoped tool observations rather than model-generated evidence.
3. Independent context integrity verification and source-scope verification.
4. An adversarial mutation reviewer for both context verifiers.
5. Required code/game quality receipts and requested additional requirements.
6. An independent quality receipt adversary and exact source continuity.
7. Evidence-based baseline comparison and absolute objective thresholds.
8. Copyright/origin and independent creative rewrite checks for exact assets
   and the final answer text.
9. A final reviewer adversary, after the final two content reviewers.
10. An ordered, hash-linked release handoff that can be independently replayed.

Stages use JEL- base36 counters and sequential page numbers. The final digest
binds run ID, pinned goal, exact answer digest, reviewed source digest, and the
last hash-chain receipt. Host run tracing and evidence ledger receive compact
receipt IDs, not source text. Explicit run API
AdaptiveJeevesRuntime.release_evidence_journal(run_id) reads the sealed record.

A restored journal is **not** accepted solely because its hashes look
well-formed: verify_release_evidence_journal requires the original observations,
goal, source and host reviewer receipts and deterministically regenerates the
journal. Missing checkers, stale source, changed answer, review-stage omissions,
changed objectives or adversarial proof failures block release.

The code audit reviewer, copyright reviewer and creative rewrite reviewer remain
separate independent host responsibilities. This receipt chain does not grant
copyright clearance or turn fixture review into production measurements.


## The 100-capability acceptance target

The typed catalog in delivery_assurance_milestones.py contains exactly 100
specific acceptance targets across context, verifier scrutiny, code quality,
game quality, objective measurement, rights, creative continuity, receipts,
operations and release admission. Codes M001–M100 are source-defined stable
identities; each block of ten is scoped to one domain. The runtime exposes
AdaptiveJeevesRuntime.assurance_milestone_catalog() for the user interface
and milestone consoles.

The MilestoneBoard deliberately begins at **0/100** on a pinned commit. A
checklist is not completion evidence. Each pass requires (a) a real source
commit, (b) artifact fingerprint, (c) named scope, (d) separate checker
identities and distinct evidence references, and (e) prerequisite passes
within the domain. Blocked results are recorded separately, never counted
as complete. Duplicate records are idempotent only if bit-for-bit identical.
An amended checkpoint requires a fresh source-bound board; previous source
bytes and historical evidence cannot silently be certified for a new commit.
The full receipt chain is replay-validated and its summary reports passed,
blocked and unverified separately.

The host remains responsible for making real checks and retaining their
actual outputs. Two claimed checker identities are necessary metadata,
**not** proof of institutional independence or of a completed check. Release
journal stage receipts and milestone-board passes serve different purposes:
the former seals an individual verified delivery; the latter tracks the
hundred longer-horizon capability targets without pretending that an
implemented type or a proposed integration proves E2E completion.


## Milestone workbench: executable 100/100 acceptance contracts

The milestone workbench implements exactly one hundred **distinct measured
acceptance criteria**, ten per domain, with unique metric names, units,
comparison direction, numeric target, minimum observed sample count and allowed
independent-measurement disagreement. It is not a "100% completed" claim:
the workbench starts at zero completed milestones until authorized hosts return
real, scoped evidence from the exact source commit and artifact digest.

- Two independently registered host measurement callbacks must separately
  inspect the same metric, method, scope and source bytes. Same checker ID,
  duplicate evidence reference, stale source hash, incompatible unit, missing
  sample, nonfinite result or disagreement beyond policy blocks the candidate.
- Both actual measurements must satisfy the objective threshold: neither
  optimistic self-scores nor a single passing reviewer are release evidence.
- The batch runner executes each domain's prerequisite chain, tracks deferred
  candidates, prevents duplicate promotion, supports idempotent resumed runs
  and produces a content-free hash receipt.
- AdaptiveJeevesRuntime.assurance_acceptance_criteria() surfaces all 100
  named acceptance rules. advance_assurance_milestones() explicitly accepts
  bound host checkers and a pinned commit; assurance_milestone_board() exposes
  the actual pass/blocked/unverified tally.
- Existing Backend Quality now compiles and runs deterministic positive and
  negative tests for every acceptance rule. Fixture-green tests demonstrate
  the workbench contract; they do not substitute for real game playthrough,
  compiler/toolchain, installer, hardware measurement or rights review.

An absence of live adapters yields **0 verified of 100**, not an automatic
perfect score. Production stage admission is a separate decision.
