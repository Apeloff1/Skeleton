# Dragon crawler, companion and game-review implementation

Base inspected: `79fe3870e331563f5da85471976f53aaf10c240d`.
Branch: `feat/dragon-wisdom-review-20261010`.

This round connects the existing game-research and two-rival systems with a
Dragon advisory reviewer. It does not declare the complete Dragon product,
arbitrary-engine control, every platform build, or global legal clearance.

## Repository parse before implementation

The tracked-text scan examined 58,619 tracked files and selected 13,943 files
using game/dragon/crawler/emulator/homebrew/engine/story/port terms. Selected
Python files were parsed with AST and inventoried for top-level symbols and
imports; none failed syntax parsing. There were 7,871 runtime-path matches,
730 test-path matches, 276 authority/documentation matches and 5,066 historical
snapshot matches. Broad text matches include incidental words; these counts
are inventory counts, not working-capability counts.

`machine/dragon_game_repository_audit_20261010.json` retains the base revision,
scan counts, full-inventory hash and 283 canonical crawler/game-builder/pet
surface records. Reproduce the full inventory with:

```bash
python scripts/audit_dragon_game_repository.py --out /tmp/dragon-game-audit.json
```

Focused semantic review traced these owners:

| Surface | Existing responsibility | Change in this round |
| --- | --- | --- |
| `skeleton/ai/webcrawler` | Acquisition, custody, research, temporal visual analysis, practice, native source emission | Bounded visual player and an actual original-grid-game RGB adapter |
| `skeleton/ai/game_builder/dual_rival_forge.py` | Ordered, rotating proposer/challenger cycles and promotion receipts | Preserved; Dragon observes pending rivals or completed champion |
| `skeleton/ai/game_builder/control_plane.py` | Independent panel, budgets and quality debt | Calls the Dragon evidence projection through `dragon_review` |
| `skeleton/ai/game_builder/rights.py` | Source rights, similarity findings and incorporation decisions | Release gate rejects receipts not issued by its own ledger |
| `skeleton/ai/game_builder/knowledge_rights_bridge.py` | Independently cleared, freshness-checked research packets | Dragon reuses the existing clearance and source custody checks |
| Native target catalog and emitters | Separate catalog, emitted-source, build and gameplay states | NES marked as implemented native source; no new compiled-console claim |
| Companion panel | Existing animations, academy, preferences and progression | Accepts a validated final four-square review |

## Proposer, adversary and Dragon

The two rivals continue to produce and challenge candidates through the
canonical forge. Dragon does not become a third producer, impersonate a
routine judge, alter promotion history, or replace the gold-master tribunal.
The caller supplies independent panel evidence and canonical rights decisions.
Dragon reviews either rival while the round is pending, suggests improvements
to both identities, and presents a terminal card only after the configured
100/1,000/10,000-round budget completes for the final champion.

The four squares cover all 21 existing quality axes:

| Square | Meaning | Aggregation |
| --- | --- | --- |
| Play & depth | Player value, engagement, mechanics, replayability, readability | Weakest measured dimension |
| Story & craft | Originality, narrative coherence, continuity, emotional impact, aesthetics | Weakest measured dimension |
| Technical delivery | Correctness, performance, accessibility, platform fit, state, replay, maintainability, testability | Weakest measured dimension |
| Rights & evidence | Rights provenance, security/privacy, source evidence | Weakest measured dimension; blockers override status |

Industry comparison requires a declared comparator product, identical workload
digest, every quality axis, evaluator output evidence and a current measurement
interval. Duplicate products cannot inflate comparison. Nonmatching, stale or
future measurements are excluded; missing evidence renders an unknown industry
grade. Median peer measurements provide the baseline. A displayed grade is an
advisory projection, not proof of market superiority or release authorization.

The companion UI displays completed-cycle counts, the four squares, measured
peer deltas, blocking issues and prioritized improvement instructions. It
rejects incomplete cycles, malformed cards and invented industry deltas.
A trusted forge worker can publish a completed `SquareReview` through
`DragonReviewStore` into the existing Academy SQLite database, using a dedicated
`SKL_DRAGON_REVIEW_SIGNING_KEY_HEX` of at least 32 random bytes. Publication
requires a bounded owner, exact completion budget and expiry within one day.
The worker must choose an earlier expiry where underlying legal or empirical
evidence requires it. No browser endpoint can publish a review.

The existing authenticated `/api/dragon-academy/status` route serves only the
current owner's MAC-verified snapshot. Missing configuration means no card;
corrupt configuration or evidence fails closed. The Academy hook parses the
card, clears it at expiry and clears it on authentication failure. A real
FastAPI HTTP test covers authenticated delivery, tenant isolation, expiry,
wrong-signing-key rejection, anonymous rejection and absence of browser writes.
This is an executable product boundary, not a deployed live forge-worker
integration or a claim that two actual model executions have completed.

## Public research and narrative digestion

Existing crawler acquisition and reviewed-knowledge custody remain authoritative.
The new reviewer can consume an already cleared research packet, rechecking
its project/artifact identity, knowledge root, rights snapshot and exact notes.
It neither fetches arbitrary URLs nor converts a public page into permission
to copy, train on or distribute its contents.

`story_digest.py` verifies registered source content and reference rights before
analyzing bounded text into abstract motifs. A transparent lexical baseline
reports heuristic motif counts; it does not claim deep semantic comprehension.
New premises compose independently authored protagonist, community, conflict,
resolution, era and mechanics. Reference story prose is not exported in the
motif observation or used by the premise composer.

Lexical overlap and protected-term checks flag obvious reuse for review. They
cannot rule out similar character relationships, plot structures, visual art,
music, trade dress or other protected expression. Changing names or historical
settings is not a clearance mechanism. Renaming copied work is not a supported
mode of legal-risk avoidance.

Profit ranking accepts independently sourced decimal profit observations and
preserves losses. Comparisons require matching currency, reporting period and
accounting basis. Revenue, sales units, estimates and absent profit data are
not silently substituted for profit. No commercial profit dataset was acquired
or verified in this round.

## Original homebrew and cross-era ports

`dragon_porting.py` creates explicit plans from the actual native catalog and
per-style emitter coverage. A port preserves declared style anchors while
allowing original desktop enhancements to exceed historical memory constraints.
Historical destinations must fit a declared memory estimate; unsupported styles
and licensed SDK destinations retain concrete blockers. Mechanic infusions are
abstract rules plus independently authored implementation goals. They remain
design-only until a real game implementation and build demonstrate them.

Example: an original Renaissance canal adventure can use interchangeable
navigation lenses that change traversal abilities, with readable tile art,
responsive input and enhanced desktop lighting/accessibility. This draws on
general design concepts; it does not import Zelda characters, names, narrative,
maps, dialogue, art, music, ROM content or source code.

Every destination has an artifact/target/jurisdiction review matrix covering
copyright, trademark, patents, SDK terms, distribution, anti-circumvention,
privacy, moral rights, publicity, database rights, consumer protection, age
ratings, accessibility and open-source obligations. Missing, ambiguous,
blocked, stale, future-dated, duplicate or wrong-artifact evidence fails closed.
These feature receipts are accepted only at a trusted application boundary;
matching hashes and reviewer method names are not cryptographic authentication.

The matrix supports technical enforcement of reviewed policy, not automated
legal judgment. Human legal review remains separate from source acquisition.
`dragon_legal_updates.py` consumes custodied, scoped primary-source snapshots.
It detects changed, newly added, missing and stale sources, invalidates affected
legal-review cells and emits due recrawl work for the existing crawler. A
source's URL, jurisdiction and area mapping cannot be silently rebound. Source
change means re-review; it is not a judgment about binding law. The Dragon
review root commits to those observations and reviewer provenance.

Live recurring case-law acquisition, jurisdiction-specific interpretation and
authenticated legal-reviewer-service integration remain open.

Primary background material inspected on 2026-10-10:

- [U.S. Copyright Office: Games](https://www.copyright.gov/register/tx-games.html): game ideas and methods are distinguished from protectable expression.
- [Copyright Circular 33](https://www.copyright.gov/circs/circ33.pdf): ideas, methods and systems are excluded from copyright protection under U.S. law.
- [Copyright Circular 14](https://www.copyright.gov/circs/circ14.pdf): adaptations involving protected underlying expression may require authorization.
- [EU software directive 2009/24/EC](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024): a software-specific authority to review alongside other applicable law.

This is a limited source check, not a current global case-law digest. The
Norwegian statutory source was unavailable through the lookup and remains
unverified in this round. None of these sources is a blanket clearance for a
specific game, trademark, patented mechanic, platform access method or release.

## Visual play that actually executes

`DragonVisualPlayer` reads RGB frames from a supplied trusted game adapter,
asks a visual policy for allowlisted controls, advances the game and records a
hash-linked action/frame trace. It checks owner/session/artifact binding,
revocable consent, expiry, finite time/step budgets, target rebinding and frame
replay around each external call. Inputs are released even after policy errors.

`ReferenceGameVisualAdapter` renders the existing original playable-grid
simulator to RGB. Its policy plans from rendered pixels, not the simulator's
private state or stored safe solution. Five seeded two-level worlds were
completed through this path. This verifies one known visual vocabulary and
one actual game simulation. It is not arbitrary-game perception, global engine
support, desktop keyboard control, or emulator execution.

Adapters and policies must themselves enforce per-call timeouts in trusted
workers. Synchronous Python callbacks cannot be forcibly interrupted by this
loop. Grant durability and concurrent one-time consumption belong to the
authenticated session owner; the local player instance is single-use.

The existing native puzzle builder also produced a Linux ELF executable and
passed all four authored stages using its compiled `--selftest`. Binary SHA-256:
`e86f93125d9ebd207f06b62c5d61d49dd7234b0cc7870c3fe7c8cf8383cd4371`.
That demonstrates actual compilation and scripted native puzzle rules, not
visual native control, player enjoyment, Windows/macOS output or legal clearance.

## L00–L13 construction and qualification

| Level | Implementation / evidence | Remaining qualification |
| --- | --- | --- |
| L00 Ownership | Existing crawler, forge, rights and companion owners retained | No new production authority is claimed |
| L01 Dependencies | Declared under existing dual-rival machine authority | Full product route/provider assembly remains open |
| L02 Contracts | Typed evidence inputs and versioned deterministic review/trace payloads | Signed owner-scoped advisory storage implemented; independent legal authority authentication open |
| L03 Admission | Candidate binding, rights provenance, current legal matrix, scoped visual grant | Durable consent and concurrent grant consumption |
| L04 Control flow | Pending-rival advice and completed-champion terminal review | Live two-model review/improvement orchestration |
| L05 State | Read-only derived reviews and hash-linked bounded play traces | Bounded expiring signed review persistence implemented; live worker publication open |
| L06 Security | Forged ledger receipts, stale reviews, malformed UI and forbidden controls tested | Independent threat review of real engine adapters |
| L07 Recovery | Failures release controls; rerunning a local player is rejected | Worker timeout isolation and resumable live play sessions |
| L08 Observability | Review roots, candidate/artifact identity, frame/action chain and stop reasons | Production telemetry and operator incident journey |
| L09 Economics | Fixed comparator, reference, frame, step and text budgets | Measured tails, throughput and consumer-hardware profiling |
| L10 Verification | Real seeded RGB gameplay, governance cycles, native selftest, focused regressions | Broad end-to-end application and engine acceptance |
| L11 Deployment | Existing CI expanded for review/visual/companion changes | Exact-head hosted CI and reviewed landing |
| L12 Operators | Supplied adapters, review time, release jurisdictions, budgets and revocation callback | Product configuration UI and reviewer integration |
| L13 Closure | Scoped executable evidence, no whole-volume completion signature | Full VOL-073/VOL-088 enterprise closure remains open |

## Outstanding product acceptance gates

- [ ] Deployed forge worker publishes to the authenticated companion snapshot flow (hermetic HTTP delivery passes).
- [ ] Two real isolated AI executions complete proposer/adversarial refinement using canonical provider runtime.
- [ ] Dragon's advice changes subsequent candidate artifacts and measurable quality.
- [ ] Public acquisition feeds newly reviewed game knowledge into that live cycle.
- [ ] Trusted isolated visual adapters execute real native games and supported engines.
- [ ] SDK/compiler/emulator acceptance is demonstrated per target/style combination.
- [ ] Original cross-era mechanic infusions execute in generated games.
- [ ] Story originality receives structural, character, audiovisual and independent legal review.
- [ ] Live primary-source case-law recrawls invalidate affected clearance and re-enter authenticated review (offline change triage passes).
- [ ] Independently sourced comparable profit observations are acquired.
- [ ] Windows/macOS builds, installer, controller/accessibility and consumer-hardware journeys pass.
- [ ] Reproducible release, security, legal review, rollback and user acceptance receipts exist.

These twelve gates are open. Source code or a green unrelated test does not
close them. This document signs the scope and evidence of this implementation
round only; it does not retroactively sign an entire masterplan volume.


## Verification and baseline repairs

The untouched base reproduces **43 failed, 874 passed, 19 skipped** in the full
Dragon suite. This round repairs the Game Boy assembly enrichment/sound anchors,
integer-to-SQLite-REAL evidence hashing in three journals, control characters in
interest tags, small-capacity query defaults, ROM compiler/target diagnostics,
and revised-content quotation triage. Historical integer-time hashes remain
valid only when their exact original digest matches; other tampering still
fails. Quotation relocation remains a request for human review.

Stale tests were aligned with current contracts: typed calibrated scores,
named feature-frame fields, stronger rejection wording, observed extraction
state, actual depth-buffer indexing and curriculum priority. A causal claim
still requires a verified protocol and sufficient samples in both arms;
client-supplied randomization labels do not qualify. Project notes are tested
as inert manifest data, never executable C or build-command text. Optional
native SDL probes skip when their required `pkg-config` is absent.

Validated locally:

- Full existing Dragon suite: **920 passed, 17 skipped**. Skips are unavailable
  toolchains/runtime dependencies, not successful platform certifications.
- Isolated canonical forge, overengineering, governance and knowledge-rights suites:
  **102 passed, 2 subtests passed**; reviewed knowledge **24 passed, 6 subtests passed**.
  Three baseline knowledge tests were corrected for earlier span rejection, query-specific
  relevance and stronger integrity rejection; no custody check was weakened.
- New wisdom and visual-play integration: **25 passed**, including 100 complete
  governed forge rounds and real RGB-only play of original seeded worlds.
- Historical timestamp evidence compatibility: **3 passed**.
- Authenticated Academy route tests: **16 passed**, including HTTP review delivery.
- Native C99 Linux executable: four-stage compiled selftest passed.
- Frontend companion, canonical wire, progression and final wisdom contract tests passed.
  Syntax transpilation includes the Academy hook; full-app TypeScript acceptance
  remains the hosted CI check, not a locally verified claim.
- Architecture map, AI construction, capability interfaces, provider bootstrap
  and enterprise-superiority validators passed; the 500-level builder validator passed.
- The required implementation-notes validator fails on both untouched base and
  this branch: `VOL-000.existing_evidence is stale versus masterplan`. A read-only
  scan finds 947 stale summary fields across the existing dossiers. This round
  does not rewrite all 421 dossiers or claim enterprise qualification.

Operator rollback: remove the optional review signing-key configuration to
stop serving cards; restore the previous application build. Review rows remain
an advisory derived table, and old releases do not consume it. Do not share its
key with build-signing or legal-review credentials. This key authenticates the
publishing worker, not legal clearance or industry success.

Scoped evidence sign-off: 2026-10-10. Product acceptance and exact-head hosted CI
remain separate from this implementation record.
