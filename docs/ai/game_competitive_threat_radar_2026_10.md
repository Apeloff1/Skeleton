# Adaptive Competitive Game Radar — October 2026

Status: implementable local subsystem in draft, stacked on #3643 and #3642.
No external titles have been scraped, classified or outperformed automatically.
Scores in unit tests are synthetic fixtures, not competitor research.

## Mission and safety boundary

Monitor how reviewed competing games converge on *planned original* game
experiences, highlight serious rivals as **ENEMY** internal benchmark
opportunities, and turn every substantiated gap into a disciplined delivery
target. Produce more original, better tested, more accessible, more polished
games. Do not create clone requests, harass developers, infringe third-party
IP, impersonate independent human reviews, claim actual store publication or
present unmeasured game strengths as commercial superiority.

"Enemy" is an internal issue-priority label, never a personal assessment.
Rival names/titles remain citations and benchmark identities only.

## Real runtime pipeline

1. The authorized crawler or operator collects official pages, legitimate
   gameplay research, video/article reviews and peer commentary. Each source
   enters the existing \`ReviewedKnowledgeStore\` with source revision SHA,
   exact reviewed claims, source age, publisher dependence group and licence.
   No source code/asset download or gameplay imitation is implicit.
2. The game-rights authority independently registers source digests and
   \`FACTS_IDEAS_REFERENCE\` permission. Wiki produces one
   \`KnowledgeBrief\` in \`design_reference\` scope. A named human authorizes
   \`clear_research_for_design\` and obtains one \`ClearedResearchPacket\`.
   Sources and rights snapshots must still match at evaluation time.
3. A \`PlannedOriginalTitle\` freezes the original game's design digest,
   supported platforms, audiences, genres, planned mechanics and at least
   three immutable **originality pillars**, distinct from common mechanics.
4. A \`CompetingTitle\` names an externally published title. An operator
   binds each source to exactly one competitor via \`RivalSourceLink\`.
   The reviewed source title must explicitly identify that competitor;
   future observations, source retractions and split-identity reuse fail.
5. \`inspect_competing_titles\` counts support statements only when each
   overlapping mechanic has at least two independent dependence groups with
   vetted confidence of at least 0.60. Repeated publisher posts or
   several copies of one review cannot boost overlap. Genres, target
   audiences and platforms are weighted context, never primary proof.
6. A competitor enters \`enemy\` at 6500/10000 overlap and exits below
   4800. At least two corroborated mechanics and two independent groups
   are required at entry. This hysteresis prevents flip-flopping; stale or
   unsupported evidence pauses escalation regardless of previous enemy status.
7. The watch recommends rechecks after 12 hours for enemy, 48 hours for
   watch, and 168 hours for weak or missing evidence. These are *adaptive
   scheduling suggestions*, not a running cron job, legal license to crawl or
   proof that new competitor information has been checked.
8. For each enemy, \`compare_competitive_delivery\` evaluates all core
   game-quality axes and emits a non-negotiable work demand whenever a
   comparison cannot prove a margin, has missing samples, mismatched protocol,
   insufficient independent witnesses or weak originality evidence.
9. \`compile_original_delivery_work\` merges simultaneous enemy demands into
   one priority backlog per axis, always keeping the highest previously
   locked target and each original identity pillar; all work is to be
   implemented from first-principles game design and replay evidence.
10. \`CompetitionWatchBook.record\` atomically logs the full reviewed snapshot,
    quality reports, parent digest, work-axis deltas, source evidence hash and
    next check. It rejects rollback in time, missing competitor scope,
    changed original design without explicit reset and evidence tampering.
    Historical opinion changes remain inspectable, not erased.
11. Only the normal reviewed production and consumer release authorities may
    promote a real playable game. Winning this comparison is not publication.

## Competitive scoring: source-backed evidence, not buzzword tags

Overlap is a weighted 0..10,000-basis-point score:

| Component | Weight | Admission |
|---|---:|---|
| Convergent confirmed mechanics | 65% | Each mechanic independently corroborated by at least two source groups |
| Shared player audiences | 15% | Operator supplied classification, not independently verified outcome |
| Shared genres | 10% | Operator supplied game-class context |
| Supported platforms | 10% | Planned/researched platform claims, not automatically hardware-tested |

Enemy **ENTRY** must also pass source freshness (180 days by default),
copyright/rights handoff, canonical source-citation binding, two confirmed
mechanics, and independent group thresholds. The evidence digest includes
Wiki and rights snapshots plus source revisions.

One celebrity review shared on many sites counts as one publisher-dependent
group. One fake video, a rival title absent from the cited article heading or
an impossible future publication date does not qualify. Stances marked
\`challenges\` and \`uncertain\` never count as confirmed rival features.
No unapproved source passage, video frame or copyrighted game artwork
is embedded into a proposed game.

## Outperform is an EVALUATION condition, not a motivational assertion

Every original title must be stronger on **all mandatory axes**, including:
player value, fun/engagement, originality, mechanical depth, clarity,
aesthetic coherence, technical correctness, performance, accessibility,
replayability and rights/provenance safety.

The optional axes of the main game forge remain available for project-specific
elevated standards: longform continuity, narrative coherence, emotions,
security, deterministic state, reproducibility, software maintenance,
testability, platform fit, evidence and so forth.

Every individual score must contain:

- Exactly bound original-or-rival subject, axis, platform and date;
- Predeclared identical test protocol, scenario and player population;
- At least ten actual samples and two distinct configured evaluator keys;
- A mean score and conservative lower/upper uncertainty interval;
- SHA-256 evidence receipt and HMAC SHA-256 over the entire measurement;
- Explicit freshness and an independently approved 256-bit-or-better key.

Judge *names* without operator-configured signing keys do not count.
HMAC proves secret possession, not that a person is independent in real
life, nor that the claimed original/review data was genuinely collected.
The production operator must verify sampling independence and evidentiary
custody externally. A fake leaderboard cannot be used as validation.

For each axis, a winning comparison needs:

    worst_lower_bound(original) >= worst_upper_bound(enemy) + margin

Default margin is 150 basis points. If that target is greater than 10,000,
the report declares the current metric unattainable and requires a revised
benchmark methodology; it does not forge a victory.

Unknown data is **not** the same as an actual quality score of 0. Missing
measurements produce actionable work but never a claim of superiority.

## Originality and legal hard stop

\`OriginalIdentityReview\` binds the exact original design digest, candidate
asset digest, all protected title-specific pillars, measured originality and
external plagiarism/similarity-risk evidence with a separate HMAC review
identity. Required original floor defaults to 8,000/10,000, upper allowed
similarity-risk threshold 1,800/10,000. The canonical \`RightsLedger\`
independently vetoes unresolved HIGH similarity issues for the candidate.

A 'new' title created simply by renaming rival characters, moving levels,
changing a soundtrack or painting a similar interface is NOT sufficient
originality. A competitor's advantage only sets the quality goal; original
human-led reasoning must propose entirely fresh mechanics, world rules,
narrative systems, animation, assets and user experiences using the title's
own design pillars. No competitor title is ever copied into work instructions.

This is a risk-management gate, not a definitive legal opinion.

## Adaptive response and quality ratchet

Every enemy creates tasks prioritized by conservative quality gap,
protected-axis severity and polish needs. For example:

- An accessibility shortfall requires original alternate interaction modes,
  controls, contrast, narration and measurable cross-device gameplay;
- An NPC-agency gap requires original witness-memory, quest scheduling,
  social rules and replay-based character behavior tests;
- Performance gaps require optimized scenes, asset budgets, NPC LOD,
  memory and platform-specific profiling without loss of original style;
- Replayability gaps call for original divergent story paths, new mechanics,
  world evolution and endgame systems, not cloned rival features;
- Originality risk freezes polishing that may increase resemblance, forcing
  independent redesign and legal re-review before further promotion.

A new competitor version or new player benchmark may raise the target. Later
targets **never decrease** while the same original plan remains active.
\`ratchet_superiority_standard\` rejects weaker margins, fewer independent
judges, fewer samples, longer tolerated staleness, weaker IP thresholds or
removal of previously mandatory axes.

## Operator integration

With a canonical local GameWorkspace, approved in-memory Wiki library, Rights
Ledger, a current KnowledgeBrief and ClearedResearchPacket, call:

\`\`\`python
from skeleton.ai.game_builder.competitive_watch_service import review_competitive_frontier
from skeleton.ai.game_builder.competitive_watch_book import CompetitionWatchBook

with CompetitionWatchBook(workspace_root) as journal:
    result = review_competitive_frontier(
        journal, planned_title, competing_titles, source_links,
        approved_brief, cleared_packet, wiki_store, rights_ledger,
        as_of="2026-10-11T12:00:00Z",
        measurements=measured_quality_by_rival,
        identity=signed_originality_review,
        trusted_identity_reviewer=originality_verifier,
        trusted_judges=benchmark_verifier_keys,
        authorized=True,
    )
    print(result.payload())
\`\`\`

Local visibility CLI:

\`\`\`sh
python -m skeleton.ai.game_builder.competitive_watch_cli status --root STUDIO \
  --original-id original_world --trusted-local-operator
python -m skeleton.ai.game_builder.competitive_watch_cli due --root STUDIO \
  --original-id original_world --trusted-local-operator --at 2026-10-12T12:00:00Z
python -m skeleton.ai.game_builder.competitive_watch_cli demands --root STUDIO \
  --original-id original_world --trusted-local-operator
\`\`\`

The CLI only reads previously accepted snapshots and cannot scrape sites,
launch an idle watcher, install OS startup jobs or deliver producer commits
by itself. The host crawler must supply freshly approved source revisions,
and an authenticated scheduler must invoke the service on each due tick.

## Adversarial test inventory

The Windows and Linux test suites exercise independent-source thresholds,
false enemy accusations, staleness, future time, changed source version,
revocation, duplicate source, changed originality pillar, forged benchmark
HMAC, unverifiable human originality review, changed cohort/protocol,
overlapping uncertainty, protected-axis regression, impossible targets,
multi-rival work prioritization, non-weakenable standards, offline watch
persistence, parent-hash corruption, rollback attempt, future scan mismatch,
untrusted scores and no-state-change on invalid integration input.

## Remaining scope for future milestones

1. Actual licensed public website/video/news sources into a hosted crawler
   with resource scheduling, rate limits, robots/terms controls, dedup,
   source-class and recrawl provenance; monitoring backend not shipped here.
2. Production-grade metric instrumentation in on-device original-game
   sessions; independent QA/playtester signers and defensible confidence
   interval estimators must not be supplanted by manually entered points.
3. Authenticated HOAG consumer dashboard, Jeeves original-design work
   planner and Dragon archive linkage; current typed pipeline exposes
   deterministic receipts for those actors but not full runtime UI.
4. End-to-end automatic branch implementation and verification of selected
   work orders, explicit human design approval and final publisher release.
5. Cross-platform game engine, genre, era and console-specific competitors
   to be researched from lawful sources; no current title corpus populated.

**No false quality or monitoring guarantees:** only actually ingested,
reviewed information will trigger an 'enemy' label or justify a claim of
outperformance. Production release remains independently governed.
