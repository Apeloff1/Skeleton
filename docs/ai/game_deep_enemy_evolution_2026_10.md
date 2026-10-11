# Deep Enemy & Genre Evolution Intelligence — 2026-10

Implementation branch: feat/game-competitive-threat-radar-20261011,
stacked on PR #3644. The word **enemy** is strictly an *internal benchmark
category* for lawful competition between products, not against people.
No game has been copied, attacked, reverse-engineered around a protection
barrier, or declared inferior without independently signed observations.

## 1. Deeper than titles, tags and superficial similarities

For every genuinely verified enemy, the system builds a **complete 51-facet
analysis script plan**, split across four gameplay production domains. Each
script has a controlled positive stimulus, adversarial/negative control,
target platform and player cohort, typed observable, a benchmark protocol
digest and an original-game source-ownership commitment.

| Area | Facets | Specific evaluated dimensions |
|---|---:|---|
| Gameplay | 14 | Input latency, control precision, combat clarity, tactical depth, progression, encounter variety, difficulty fairness, exploration payoff, world persistence, NPC agency, quest consequence, replayability, tutorial friction, accessible controls |
| Graphics | 12 | Independent art direction, silhouettes, animation weight, lighting legibility, scene composition, motion comfort, texture readability, color language, FX budget, LOD/pop-in, UI hierarchy, actual platform fidelity |
| Sound | 11 | Spatial placement/occlusion, mixing, original music identity, state-responsive music, action feedback, dialogue delivery, dynamic range, audio latency, silence, hearing accessibility, target-hardware audio |
| Storyline | 14 | Causality, player agency, character consistency, pacing, lore, subtext, witnessed incidents as quests, branch completeness, long-term consequence memory, mystery fairness, theme expression, endless/postgame mode, emotional payoff, localization |

Total: **51** controlled probes, no first-N truncation. Each contains eight
ordered analysis steps: freeze build and cohort, obtain authorized gameplay
observation, execute seeded nominal replay, execute fault permutation, collect
time-aligned evidence, blind same-protocol scoring, seek counterexamples, and
verify title originality/accessibility/rights constraints. Human-reviewed
source notes are *hypotheses*; the runtime marks them
\`grounded_hypothesis\` only after two distinct independent publisher groups.
Source articles without gameplay measurement cannot become rival weak spots.

## 2. Per-enemy genre evolution / historical comparable work

\`competitive_evolution_chain.py\` represents a dated graph of game titles
with release year, era, hardware targets, genres and reviewed mechanic groups.
A graph edge is either:

- \`genre_comparable\` — two titles constitute an independently corroborated
  comparison. **Does not assert that one copied or directly influenced the
  other**.
- \`documented_influence\` — the reviewed source must support a direct
  influence claim with evidence explicitly identifying both games.

Each edge requires at least two independently sourced, rights-reviewed Wiki
notes. Time travels forward, games stay in connected genres and mechanics,
cycles and duplicate edges are rejected, and only predecessors on a verified
path to the current competitor enter its chain. Unconnected titles are
research leads, not forged ancestors.

A default **three-generation** chain must exist before a lineage is labeled
complete; incomplete chains return explicit sourcing gaps instead of hiding
the omissions. A signed/hashed historic research revision can become
invalid when retracted or when the rights ledger changes.

## 3. Adversarial objective weak-spot scoring

\`score_deep_scripts\` requires gameplay/player measurements for original and
rival titles using the **same precise script digest**. Each observation binds
the evaluator, replay receipt, participant count, date, signed score and
confidence interval. Unknown evaluators, tampered results, identical repeat
judges, future dates and stale outcomes fail closed.

**Do not use an arbitrary external floor or a blog opinion as proof of an
industry standard.** A rival receives the
\`verified_weakspot\` label only when an additional, independently signed,
same-script \`industry_cohort\` control establishes:

\`\`\`text
conservative_upper_bound(rival) + predeclared_margin
    <= conservative_lower_bound(industry_control)
\`\`\`

The industry cohort is a *locally measured reference cohort*, not an official
certification of any third-party standard. Each script requires independent
judges and at least ten repeated measurements per evaluator; without evidence
its status is \`insufficient_evidence\`, not "competitor flaw". Verified
superiority also needs the original game's conservative lower bound to exceed
the rival upper bound plus margin.

Missing audio, graphics or story studies remain visible and produce controlled
research/analysis scripts. The system never fills gaps with invented numbers.

## 4. Real original-game telemetry aggregation

\`competitive_probe_runner.py\` consumes *recorded trial telemetry* for one
game build and script, with explicit consent and independently reviewed
capture/source evidence. The implementation enforces:

- At least ten distinct participant/session digests, default twenty total,
  with at least five unique sessions in each nominal and adversarial condition;
- No mixed game builds, stale or future observations, untrusted evaluator or
  title, repeated session/player ID, or mismatched script IDs;
- Matched nominal and fault-control result calculations;
- Deterministic sample mean and 1.96 x standard-error 95% normal-approximation
  interval for each condition;
- Worst-condition central score and conservative enveloped lower/upper
  intervals rather than hiding failure behind an excellent normal-case score;
- SHA-256 provenance root across all actual input trial records and HMAC
  SHA-256 keyed evaluator signature over the resulting score report.

This is a numerical scoring engine, **not** a screen recorder, automatic image
analyzer or proof that supplied telemetry was collected honestly. The source
collector, game/hardware evaluator, and legal/consent owner must vouch for
the raw evidence and calibrated rubric before this adapter is run. Small or
highly correlated cohorts invalidate real-world CI assumptions; production
evaluation must account for those issues separately.

## 5. Outwork current enemy AND its strongest predecessors

\`competitive_ancestry_frontier.py\` measures every reviewed predecessor
against exactly the same facet analysis script, with signed independent game
measurements. A "win against the enemy's ancestors" is valid only when:

\`\`\`text
original_game_conservative_lower_bound
    >= max(current_enemy_upper, every_ancestor_upper) + margin
\`\`\`

A missing predecessor, missing signed measurement, divergent scoring protocol,
incomplete genre chain or metric that cannot support the margin blocks
the claim. The frontier calculates one independent 51-facet record
per enemy, never picking only its weakest era. It preserves enemy/source
identity without copying reference gameplay data into training weights.

## 6. Distinct original counterproposals and implementation scripts

\`competitive_counterproposals.py\` makes an original work order for each
unmet facet. Every order contains the exact analysis/evolution digests,
winning quality floor, weakness and evidence blockers, original genre-era
comparators, **all immutable original title identity pillars**, native
engine development instructions, adversarial case requirements, and
cross-domain safety gates.

- **Gameplay:** stateful original interaction loops, NPC witnessed memory,
  player-controlled quest/decision forks, deterministic replay, novice/expert
  combat and navigation challenges.
- **Graphics:** authored distinct silhouette/palette rules, scene composition,
  animation/LOD/FX budgets, readability under color and HDR variations,
  real platform profiling.
- **Sound:** *newly composed* motifs, adaptive sound states, dialogue clarity,
  accessibility cues, spatialized audio and latency benchmarks.
- **Storyline:** authored new characters, lore and causal event chains,
  NPC evidence→quest agency, divergent story branches, paradox detection,
  ending/endless/postgame and localization tests.

No competitor character, map, melody, art, dialogue, code or literal
level-design expression is included in an implementation script. A problem
shared by many genre ancestors is a *design opportunity*, not a license to
appropriate a historical mechanic's unique expressive implementation.

Outclassing claims now also require `SignedImplementationReview`: a
separately configured HMAC signer binds the exact original new game build
digest, the exact post-implementation facet verdict digest, the associated
counterproposal identity and explicit protected-quality and originality QA
decisions. Absent credentials or modified verdicts cannot be called delivered.
This verifies configured key possession and data integrity, not real-world
reviewer independence or publisher approval.

Until evaluated, each counterproposal is still only an authored plan. The
\`evaluate_original_counterproposal\` function demands a new original
replayed build digest, nonregressing protected checks, an originality-review
decision, a measurable lower-bound improvement and the target outperform
margin. This is **not** a publisher release or independent legal clearance;
the existing canonical consumer release assurance remains the gatekeeper.

## 7. Integration and evidence custody

\`competitive_deep_service.examine_enemy_genre_portfolio\` consumes an earlier
successful and rights-cleared \`CompetitionRun\` from the current rival radar,
and a **separate** corroborated history-analysis Wiki brief with exact
rights-clearance receipts. Separation is important: public-market title
discovery is not, by itself, evidence of visual/narrative/audio performance
or proven historical influence.

Each enemy obtains:
- 51 per-facet scripts and measured verdicts;
- historical title graph, verified/comparable edge evidence, remaining gaps;
- 51-facet strongest-predecessor frontier;
- original design counterproposals for every unmet measured standard;
- comprehensive missing-evidence agenda.

The system remains host-triggered: it does not invent a crawling daemon,
installed game enhancements, real consumer market scores, competitor
weaknesses, or independently verified source identities. Existing Dragon
recrawl planning from #3644 can identify authorized public sources to
review again; actual source ingestion still requires explicit collection
and Wiki/rights admission.

## 8. Versioned deep almanacs and operator visibility

\`competitive_deep_archive.py\` stores a complete 51-facet + ancestry
\`DeepCompetitorPortfolio\` under the real local \`GameWorkspace\`, bound
to the exact original competitor watch event, current reviewed Wiki state,
legally cleared source revisions and the original-design source root.

Atomic SQLite WAL events store canonical JSON and SHA-256 parent chains.
Revisions must strictly advance in UTC time and carry their exact parent
digest. Re-recording earlier knowledge, omitting an enemy, truncating a
facet family, losing an ancestor or changing rights without refreshing the
reviewed brief fails closed. History checks parse each revision, validate
canonical content, verify parent identity and reject duplicate JSON keys.
This is durable local custody, not externally notarized immutable storage.

Operators can examine each saved analysis from the existing watch CLI:

\`\`\`sh
python -m skeleton.ai.game_builder.competitive_watch_cli deep --root STUDIO \
  --original-id original_world --trusted-local-operator
\`\`\`

The command displays real recorded script counts by gameplay/graphics/sound/
storyline, confirmed weakspots only, source-evidence gaps, lineage-generation
counts, ancestry outclassing status and outstanding original proposal counts.
No claims are invented for unknown games; missing archives return an explicit
error. It never modifies the game or downloads a rival's assets.

## 8. Testing, rollout and standards

\`tests/test_game_builder_competitive_deep.py\` validates the entire 51-script
catalog, 3-generation corroborated graph, disconnected predecessor handling,
future/forged measurements, actual signed industry-cohort weakness,
prototype priorities, originality preservation, gains after replays and
end-to-end portfolio composition. \`test_game_builder_competitive_probe_runner\`
replays real typed score sequences through the deterministic scorer.

Exact-head Ubuntu 24.04 and Windows 2022 jobs use Python 3.11 with sparse,
no-credentials checkout. **CI green only qualifies deterministic control and
fixtures**, not live commercial outperformance, scientific cohort validity
or publisher/IP determinations.

Next system milestone is to attach actual permitted game telemetry, player
QA tools, blind audio/visual/narrative review, verified signed game builds
and original studio editor changes. No extra closed-source game files or
protected third-party material are needed.
