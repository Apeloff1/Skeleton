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


## Real milestone queue, no unattended actions

delivery_milestone_queue.py provides a deterministic in-memory scheduler for the
100 acceptance checks. Each item has bounded attempts, a stable ID, priority,
explicit state, prerequisite and retry clock. Only the host can claim work and
supply the clock or source-bound measurement callbacks. Typed leases prevent
double completion and reject expired, foreign or stale tokens. Lease expiration
recovers an abandoned unit of work; exhausted retries mark it failed rather
than spinning forever. Completed results must carry the workbench's two
independent source-bound attestations.

Queue snapshots and event chains are content-addressed, serial and
replay-checked. Source commit and artifact digest must match on restore.
Queue state and milestone-board state are checked for consistency.

The adaptive runtime exposes begin_assurance_work_queue(),
claim_assurance_work(), settle_assurance_work(), recover_assurance_work()
and assurance_work_queue() as host-side entry points. It disallows mixing the
direct milestone batch API with an active lease-managed queue for the same
run, and uses an optimistic source-state check to reject concurrent settlement.
External durable persistence, cross-process locking, server-side scheduling,
actual CI/Godot execution and independent copyright review still require
their real host services; the queue does not claim those exist.

The hundred objectives must be supported by independently captured
measurements before the board can mark them passed. Running fixture tests,
creating a milestone definition or queuing work is not certification.


## Original major-milestone execution: MDM-001 through MDM-100

The original masterplan has 100 milestones covering 421 canonical volumes.
These differ from the M001-M100 assurance-rule IDs.

scripts/execute_ai_100_large_milestones.py resolves real acceptance tests
from the original source-pinned roadmap, checks their paths, hashes exact test
source bytes and executes the approved Python tests using bounded subprocesses.
Every result is a hash-linked test receipt, preserving failure diagnostics as
a status and output fingerprint without leaking raw logs in the summary.

Use these commands from a clean checkout:

    python scripts/execute_ai_100_large_milestones.py --milestone MDM-001
    python scripts/execute_ai_100_large_milestones.py --milestone MDM-001 --execute --report milestone-001.json
    python scripts/execute_ai_100_large_milestones.py --all

The manual-only GitHub workflow AI 100 Milestone Real Execution can invoke
one milestone without adding mandatory CI fanout. Preview is the default;
actual execution requires the explicit execute flag.

A successful run proves only the selected tests on the pinned commit.
It does not implement missing features, grant signoff, or clear the mandatory
independent review, security, rollback and exact-head requirements.


## Durable milestone work queue checkpointing

The optional SQLiteMilestoneQueueStore binds each Jeeves run to a durable
source commit and artifact digest. Queue snapshots are stored with exact
canonical JSON hashes, sequential generations, optimistic compare-and-swap
updates, SQLite transactions and independent typed hash-chain replay.
A resumed agent can restore the previous claim/lease history, explicitly
expire abandoned leases, and continue without fabricating milestone progress.
A changed source snapshot, duplicate serialization keys, nonfinite values,
malformed records, broken receipt chain, duplicate writers or a closed storage
adapter are rejected. Existing memory is only updated after the durable
checkpoint write succeeds.

The API uses bind_assurance_checkpoint_store(run_id, store,
source_commit=..., artifact_digest=...) to attach explicit host storage.
The ordinary no-store path is *ephemeral*, not crash-safe. SQLite durability
is conditional on the host's actual filesystem lifecycle and storage policy.
Hashes detect corruption, not tampering by an attacker with write access to
the database. These are system-level implementation milestones, not
production-certified completion of any of the original 421 volumes.


### Tamper-evident generation history

SQLite milestone checkpoint writes now also append a transactionally linked
history entry for each new generation. Replay verifies sequence continuity,
the previous receipt, content and queue digests, and the latest committed
snapshot before loading or overwriting it. Exports contain only digest records
and generation numbers, not project or game source. Idempotent replays do not
create redundant generations. Truncation, rollback to an earlier current
snapshot, missing history, modified receipt, and cross-process stale writers
all block checkpoint trust.

This history is a same-database integrity mechanism, not an external
anchoring/signature service. An attacker who can rewrite the complete SQLite
database could recompute both history and state; higher-assurance deployment
requires a trusted off-database audit sink and independently verified anchors.


## Bounded durable host execution cycles

The source-bound scheduler executes actual host-provided reviewer callbacks
in bounded cycles through the delivery_milestone_driver module. It loads an
already-initialized SQLite queue, expires abandoned leases, requires separately
registered independent host checkers, persists each lease before invoking
reviewers, and commits every verified settlement before reporting completion.

Each cycle sets a claim budget, duration limit and operator stop hook. Host
exceptions, lease expiry and time-budget overrun leave the in-flight lease
recorded until explicit recovery, rather than silently replaying an
unknown outcome. Cross-process optimistic checkpoint conflicts fail closed.
The journal binds run identity, pinned source, prior/final queue digests,
generation history and accepted verdicts. The scheduler never invents
measurement values, checker independence or production signoff.

Finite resource budgets keep each cycle controllable, while long-running game
production may continue through a succession of durable cycles. Regression
tests drive all 100 criteria through several checkpointed cycles, but do not
certify any original MDM-001..MDM-100 masterplan milestone as complete.


## Durable operator intervention and cancellation races

The same source-bound SQLite authority now stores operator control states:
running, paused or terminally cancelled. A host must explicitly authorize the
operator identity and reason reference before calling the runtime's
set_assurance_operator_control() or the underlying store. Controls are
versioned with compare-and-swap generations, scoped to the exact queue source,
checked against their canonical receipts, and survive process restarts.

Pause prevents *new* work claims, but permits an already claimed reviewer to
settle. Cancellation blocks any further queue-state changes. The store checks
operator control in the same SQLite write transaction as queue settlement,
preventing a race where the driver reads "running", an operator cancels, and
a later worker publishes a result. A cancelled queue cannot be silently
resumed. An interrupted host execution remains durably leased and must not be
reported as successfully verified. Operator controls are independent from
the ordinary user's authored game data and are never inferred from AI output.

The durable work driver checks controls before recovery, before each claim
and after external reviewers. Test fixtures exercise pause/resume/cancel,
interleaved processes, stale generations, failed direct queue bypass attempts,
tampered control receipts, and runtime integration.
