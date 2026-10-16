# Jeeves original storytelling — professional novel / screenplay / film direction gates

**Implemented:** signed-source literary/film-story metrics, deterministic
reparse, actionable revision queue, opt-in governed AI authoring context,
and the story-continuity production retry gate.

**Not certified:** actual professional manuscript reception, Oscar/BAFTA/
major-publisher artistic quality, rendered performance, music/voice/lipsync,
playtested full game arcs, completed film or model-weight improvement. A
Hollywood-quality claim needs real independent critics and media evidence;
the numerical policy alone cannot establish artistic brilliance.

## Canonical owners

- Story bible and approved scene chain:
  skeleton/ai/game_builder/story_canon_fabric.py
- Full source continuity, voice/face/wardrobe/region:
  skeleton/ai/game_builder/story_continuity_assurance.py
- 100 chapters / 1,000 acts / 9,999 scene dramaturgy:
  skeleton/ai/game_builder/story_chapter_context.py
- Film shot continuity / coverage:
  skeleton/ai/game_builder/story_cinematic_review.py
- Scene-by-scene approved source:
  skeleton/ai/game_builder/story_workspace.py
- New **review lens, not authoritative scene writer**:
  skeleton/ai/game_builder/story_direction_quality.py
- New developer-only, read-only dossier adapter:
  skeleton/developer/jeeves_game_direction_cli.py

No parallel creative canon and no model provider SDK are introduced.

## Professional creative direction rubric

Every dimension remains a hard **90/100 quality target**, where 90 is a
claimed ordinal expert grading scale, not a mathematically certified
definition of literary or Hollywood excellence:

1. original_voice — memorable, original literary and screenplay style
2. character_motivation — credible desire, flaw, contradiction, stakes
3. character_transformation — justified choices and earned internal arcs
4. cause_and_effect — setup/reversal/consequence/payoff, no arbitrary jumps
5. thematic_coherence — recurring motifs embodied in decisions
6. world_consistency — laws, factions, setting, original historical feel
7. dialogue_subtext — distinct voices, silence, implication, tension
8. pacing_and_reversal — scene-to-scene dramatic rise and contrast
9. emotional_resonance — earned investment, grief, wonder and transformation
10. player_agency — genuine branch impact, not cosmetic dialogue choices
11. visual_storytelling — actor blocking, camera motive, art and composition
12. sound_and_performance — score, silence, voice, editing and expression
13. accessibility_and_localization — inclusive, comprehensible storytelling
14. ending_payoff — causal setups repaid with meaningful closure or choices

Review must include at least two distinct qualified reviewers spanning
novel/screenwriting and film/game direction. Each score must cover all 14
dimensions. Duplicate identities, unknown roles and invalid scores fail
closed. Such provided scores are still clearly labeled **operator supplied
not externally corroborated**, never verified critic responses.

A blind reader/audience test, professional screenplay coverage,
independent story editing and actual timed film/media samples are needed
to qualify the subjective domain. Do not lower thresholds when a scene
fails. Require revision, full canonical reparse, and new review.

## Observed, source-proven metrics

Current deterministic scans actually count:
- reviewed signed scenes and stable source SHA-256 identities;
- original author/story bible and canonical cross-scene references;
- authored beats and explicit character state transitions;
- repeating dialogue lines per speaker and lexical diversity;
- causal event references and interactions;
- missing transformation or repeated dialogue as revision triggers.

These metrics are **diagnostics**, not a book sale predictor, box office
forecast, or direct measure of prose beauty, subtext, score composition or
rendered acting.

The editor can separately attach its existing cinematic shot board for
shot-to-dialogue coverage, timeline continuity, visual identity, geography,
lighting/cuts/sound and validated actor look IDs. A complete film/audio
timeline with rendered pixels still needs real validation. Current direction
audit reports film quality as **unproven** rather than using story-source
shot counts to fabricate achieved director-grade cinematography.

## Reviewing source-bound story history

Prepare a local project design/story_direction_packet.json as follows:

    {
      "schema": "skeleton.jeeves.direction_dossier.v1",
      "bible": "<canonical signed story bible object>",
      "scenes": [
        "<canonical signed and consecutively linked scene objects>"
      ],
      "expert_reviews": []
    }

The placeholders above are explanatory strings; use actual validated
objects produced via the existing StoryCanon authoring workflow, NOT
fabricated JSON or unsigned drafts. Each scene retains the author
review/consent and rights provenance required by the canonical verifier.

    python -m skeleton dev game jeeves direction-audit --project ./game --source design/story_direction_packet.json --passes 8
    python -m skeleton dev game jeeves direction-revision --project ./game --source design/story_direction_packet.json --passes 8

A direction audit revalidates the **entire provided source chain** with
the existing signer, then audits dialogue/cause/character construction.
Chapter v2 sources additionally use canonical chapter dramaturgy checks.
Repeated scrutiny compares the same source and must never be claimed as
eight independent reviewers. A revision does not overwrite, unsign, or
auto-approve human story sources.

## Source-grounded real model generation

The operator may opt into transferring **aggregate** current story metrics
and revision categories to the real governed Jeeves provider:

    python -m skeleton dev game jeeves propose --project ./game --kind scene --brief "Original dramatic reversal" --direction-source design/story_direction_packet.json

Without --direction-source the original v2 proposal path remains
unchanged. With an explicit dossier the envelope becomes proposal v3 and
binds the source SHA-256, so a source change during model inference or
between draft/review/apply blocks acceptance. The provider receives a
bounded structured summary, not unrequested original manuscript bodies.
Successful inference creates only an immutable pending proposal; the
local operator must still explicitly review/approve its digest to create
a new Markdown DRAFT. Actual canonical story scene integration continues
to require the creator-signed source workflow. No story is auto-published,
executed, nor inserted into model training.

## Full-game story completion retry loop

The existing production-cycle automated gate now evaluates
story_continuity using the canonical sourced dossier. Missing/corrupt
continuity evidence is FAILED. Signed source with actual scenes is
BLOCKED awaiting independent professional narrative/film/player evidence.
It does not falsely mark studio release qualified. Each bounded retry
appends its own hash-linked observation, preserving the quality floor
and full project history.

    python -m skeleton dev game jeeves production-cycle --project ./game --gate story_continuity --passes 8

## Professional book / Hollywood and market comparisons

Commercial acclaim must be investigated with lawful, timestamped,
same-medium data. Copies sold in a specific edition, film gross adjusted
for release year/market, reviews, audience completions, independent juried
awards and production budgets are DIFFERENT signals. Never rank film
dollars directly against game units, confuse box office with profit or
assert that sales equal great art. Source count, review count, region,
release period, audience cohort, translations and re-release effects
matter. Unknown evidence must remain unknown. Avoid reproducing
copyrighted novels/scripts/film clips in training without proper rights.

A game with professional-level literature, film direction and music
also must be PLAYABLE: every authored scene's motives and choices must
change actual state. This is evaluated by game/quest/scene runtime receipts
and full walkthroughs, not a storyboard's subjective score.

## Work still required for true professional parity

- Live longform original story production with grounded canon retrieval,
  scene-by-scene approvals and 9,999-scene stress execution.
- Independent book editing, director/actor workshops, objective review
  methodology, critic/audience study and disagreement resolution.
- Story/quest causality mapped into actual game choices, not a static
  scene dossier.
- Professional film timeline, camera/character animation, cinematography,
  lip-sync, lighting, environment, music/VO and render evaluation.
- Real player engagement/branch readability measurements, original
  prose in translation, rights audit and accessible subtitle/voice UX.
- Governed real checkpoint training, held-out novel/story/cinematic
  benchmarks and a qualified adversarial creative director.
- Evidence of complete playable games with exceptional reception.
- See GAME_PRODUCTION_GAP_ATLAS_2026-10-16.md for the detailed 65-item
  domain-by-domain closure register.

Run:
    python -m pytest -q --noconftest tests/test_game_builder_story_direction_quality.py
    python scripts/check_architecture_map.py
    python scripts/check_ai_app_construction.py
    python scripts/check_capability_interfaces.py
    python scripts/check_provider_bootstrap.py


## Medium-specific benchmark comparison (new source-only gate)

Book success, film success, television audience measurements and game
unit sales cannot be pooled. The read-only direction-benchmark checks
exact SAME-medium, genre, release decade, territory and commercial
measurement unit cohorts. Its quality axis uses original source-reported
professional critic scores (0–100) with an explicit review-count floor,
and commercial reach uses a single unit appropriate to its medium:

- novel: audited_print_copies, at least five professional critical reviews;
- film: ticket_admissions, at least fifteen professional critical reviews;
- television: audited_viewer_hours, at least fifteen critical reviews;
- interactive_game: reported_units, at least seven critical reviews.

Each cohort needs five to 512 distinct works, three or more distinct values
per axis, matching historical release years, and separate HTTPS sources
for commercial and critic numbers. A work qualifies only if top quartile
on both commercially comparable reach and professional rating with
critic score at least 85. Zero qualifying references is an evidence gap,
not permission to change categories or ease the target.

Importantly the underlying issuer numbers are not fetched or
independently certified by this tool. Film admissions aren't box-office
dollars, and print-book POS records are not global lifetime print+
ebook+audio totals. For example, Circana states that its BookScan
covers roughly 85% of U.S. trade-print sales, not all formats:
https://www.circana.com/industries/books
Metacritic describes weighted professional critic aggregation, with
individual title review counts rather than self-reported audience ratings:
https://www.metacritic.com/movie/?page=1

Dossier location: design/story_reference_cohorts.json.
Required schema: skeleton.jeeves.story_media_benchmark.v1.
Required exact top-level fields: schema, cohorts.
Every cohort: medium, genre, period, territory, commercial_unit, works.
Every work: id, release_year, commercial_quantity, professional_score,
professional_reviews, commercial_source, review_source.
Every source: url, issuer, published, kind.
Commercial source kinds: publisher_or_studio_disclosure or
audited_industry_measurement. Review source kinds:
independent_critic_aggregate or professional_review_archive.

    python -m skeleton dev game jeeves direction-benchmark --project . --source design/story_reference_cohorts.json

This returns qualified original reference lists and sources but
**does not train Jeeves, import scripts or license their characters**.
Literary/film grade work remains an original production objective
requiring independently witnessed read-throughs and audience/film reviews.


## Measured cinematic production direction (implemented shot pipeline)

A signed source dossier may also contain BOTH production_contract and
shot_boards. Supplying only one fails closed; the literary audit no longer
silently ignores submitted film-source evidence. Each board is:

    {"scene_sequence": 1, "shots": [ ... approved original cinematic shots ... ]}

The canonical production contract is the existing signed
story_continuity_assurance object, with original actors/voice IDs,
face geometry and regional color/lighting authority. The shots list
uses the existing story_cinematic_review.verify_cinematic_shots grammar,
not an invented parallel camera engine.

    python -m skeleton dev game jeeves direction-shots --project . --source design/story_direction_packet.json --passes 8
    python -m skeleton dev game jeeves direction-audit --project . --source design/story_direction_packet.json --passes 8
    python -m skeleton dev game jeeves direction-revision --project . --source design/story_direction_packet.json --passes 8

The cinematic evaluator measures each signed scene's source-validated
shot count, timeline duration, individual shot duration distribution,
camera angles and movements, editing cuts, actor screen time and exact
once-in-order coverage of authored dialogue. Source identities,
eye-line/screen-axis changes, cut chronology, voice and face IDs,
original palette and regional lighting remain governed by the existing
canonical film verifier.

Multiple scrutiny passes rerun source and contract checks; they do NOT
create independent production reviews or assert that actors performed
the scene. The unified direction audit now reports a bounded
cinematic_direction summary; revision work orders include individual
shot-level editorial prompts, each linked to its canonical receipt
digest. Missing/altered source, forged actor face or voice, unmotivated
axis flips and uncovered dialogue fail closed.

**Still unverified:** rendered cinema pixels, actor performance,
actual soundtrack and voice acoustics, lip-sync, audience emotional
impact, screenplay coverage quality, motion continuity and full
interactive game playthrough. Deterministic shot metadata is pre-render
production evidence, not a Hollywood-level final-film certificate.


## Executed story-to-gameplay consequence bridge (new)

The project can now demonstrate that a signed scene's authored event
actually leads to an executable original quest result, not just an
unimplemented story beat. Use the existing canonical quest-scene Director
runtime; there is no second simulation or source signing authority.

Create design/story_gameplay_dossier.json with exactly these fields:

    {
      "schema": "skeleton.jeeves.story_gameplay_dossier.v1",
      "bible": "<actual signed original StoryCanon bible object>",
      "scenes": ["<actual signed original StoryCanon scenes>"],
      "director_world": "<actual original DirectorWorld.payload() object>",
      "author_review_acknowledged": true,
      "replays": [
        {"name":"hero_takes_first_route",
         "actions":[{"kind":"use","key":"action_00_00_0","scene":"scene_00"}]},
        {"name":"hero_takes_other_route",
         "actions":[{"kind":"use","key":"action_00_00_1","scene":"scene_00"}]}
      ],
      "bindings": [
        {"scene_sequence":1,"source_anchor":"visit_1",
         "replay":"hero_takes_first_route",
         "quest":"quest_00","stage":"stage_00",
         "approach":"method_0","consequence":"quest_00_outcome_example"},
        {"scene_sequence":1,"source_anchor":"visit_1",
         "replay":"hero_takes_other_route",
         "quest":"quest_00","stage":"stage_00",
         "approach":"method_1","consequence":"quest_00_outcome_other"}
      ],
      "require_distinct_choices": true
    }

The quoted object placeholders and example outcome flags are explanatory:
use actual canonical signed source and DirectorWorld payloads. Actual
outcome flags MUST come from replayed world stages and cannot be invented.

    python -m skeleton dev game jeeves direction-gameplay --project . --source design/story_gameplay_dossier.json --passes 8

The verifier replays every declared Director action through
director_play/director_verify, rejects unavailable actions, enforces
source/Director project identity, checks exact signed scene anchors, and
requires the specified quest/stage, executed approach and material
consequence to match its replay. A requested two-choice standard requires
at least two distinct observed approach/consequence pairs for a stage;
duplicating the same outcome cannot qualify. Each bound action gets a
source and executed replay digest.

The audit reports unbound signed scenes, never-played quest stages and
played stages lacking story binding. Repeat passes re-execute the actual
quest runtime, but only within a finite and resumable per-call budget,
without imposing a lifetime limit on game development or scrutiny.

Human review acknowledgement of the blueprint is **local input**, not
externally authenticated copyright/licensing or high-impact approval.
Neither a completed Director stage nor signed story source proves a
fully installed commercial game, end-to-end story branch playthrough,
professional actor direction or book/film audience reception.
Canonical source approval and real platform/hardware validation remain
separate mandatory acceptance requirements.

### Signed story pacing and edit-rhythm diagnostics

The cinematic review now counts approximate source-dialogue words and identifies
shots whose signed dialogue requires more than 210 words/minute even when all
shot duration is assumed to be speaking. Shots below 750 ms are listed for
editorial rhythm inspection, with motivated rapid-cut sequences flagged.
These are advisory heuristics, not downgraded quality gates. No recorded
acting, acoustics, lip-sync, accessibility or actual film is certified.
Jeeves model prompts receive only aggregate verified counts and warnings;
unrequested original dialogue text is never added to the cinematic brief.


## Played dramatic payoff assurance (additional milestone)

When a direction dossier contains BOTH dramatic_threads and gameplay_source,
the producer now joins canonical literary causality with actual Director
action replay evidence. The original StoryCanon signer and Director replay
owner remain the ONLY source authorities. The join requires a resolved
thread's exact signed payoff scene and node ID to appear in a replayed,
executed quest result. A solved, unrelated quest can never qualify that
literary promise. Open threads remain unresolved, even if other quests
were won.

An optional explicit direction-dossier property:

    "payoff_alternatives_required": true

requires each original dramatic payoff to be associated with TWO OR MORE
genuinely different approach/consequence pairs for the SAME quest stage
and the SAME signed payoff anchor. The flag cannot be supplied without
both original signed dramatic threads and real replayed quest evidence.
False claims, mismatch of story histories, duplicate replays, and
unplayed payoffs stay blocked, not promoted to a completed game.

    python -m skeleton dev game jeeves direction-audit --project . --source design/story_direction_packet.json --passes 8
    python -m skeleton dev game jeeves direction-revision --project . --source design/story_direction_packet.json --passes 8

The audit adds playable_payoffs, showing actual played consequences,
unresolved original threads and source-plus-replay SHA-256 fingerprints.
A revision creates P0 work items for individually unplayed payoffs and
does not edit the manuscript. Every complete score still requires
professional literary/film creative review, real native game runtime
execution, human playtest comprehension and actual platform release.
A matched source node and replayed choice does NOT independently prove
that the consequence's narrative meaning makes sense to an audience.

### Transitive model-proposal source integrity

When a direction packet references a gameplay_source, Jeeves' v3 model
proposal now pins TWO separately measured source hashes: the direction
packet SHA-256 and its linked playable quest replay dossier SHA-256.
A change to either source while inference runs or between proposal,
review and application blocks acceptance without lowering the quality
floor. Existing v3 proposals with only an original direction dossier,
and pre-direction v2 proposals, remain backward compatible. This is
referential integrity, not an IP clearance or independent approval.
The model receives only bounded original evidence metrics and statuses,
including source-verified payoff/branch counts, never the full quest
action history or authored manuscript text without explicit request.
