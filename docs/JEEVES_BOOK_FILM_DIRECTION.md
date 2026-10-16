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
