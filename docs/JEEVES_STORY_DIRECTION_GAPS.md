# Jeeves literary story, Hollywood direction and full standalone-game gaps

Scope: source/metrics/evidence layer over the canonical Skeleton GameBuilder story
owner, not a second narrative system, model service, editor, animation engine or
film renderer. These checks can block weak / unreviewed work; cannot turn a
numerical rubric or commercial rank into objectively exceptional art.

## Production bar

Jeeves is to pursue **publishable-novel-level prose and dramatic character
work plus film-quality direction**, while retaining consequential playable
branches. Requirements across a full project:

- Original voice, memorable characterization, subtext and theme; no imitation
  of copyrighted passages, directors' exact shots or recognizable franchise IP.
- A signed canonical narrative bible, world laws, cast identities, approved
  region design and actor voice/face locks before any final scene sign-off.
- Real causal setup/reversal/payoff arcs; meaningfully authored character
  transformation; dialogue and emotional stakes tracked across all chapters.
- Critical player decisions cause concrete world-state and future dialogue
  changes. All required routes and endings need actual playable evidence.
- Cinematic shots with authored motivations, screenplay timing, blocking,
  lighting/palette, sound direction, 180-degree continuity, performed lines,
  language/localization and rendering/actor checks.
- Every scene in the accepted story must possess an approved shotboard; one
  global style must be maintained without losing individual scene craft.

The machine-checked dramatic source remains governed by:
- skeleton/ai/game_builder/story_canon_fabric.py
- skeleton/ai/game_builder/story_continuity_assurance.py
- skeleton/ai/game_builder/story_chapter_context.py
- skeleton/ai/game_builder/story_direction_quality.py
- skeleton/ai/game_builder/story_cinematic_review.py

**Objective measures** include scene/act/chapter count, signed source and
full-history replays, beats, cast presence, dialogue lines, exact repeated
lines and vocabulary diversity, causal references, character state changes,
unresolved highlighted plot points, scene shotboard coverage, every line
spoken exactly once, camera variety, shot durations and screen-direction
validity. The viewer/reader's emotional response, prestige, narrative craft,
acting and originality cannot be established from those counts alone.

**Subjective acceptance** uses at least three reviewer identities and the
following 14 separate metrics: originality, prose_and_voice,
character_psychology, character_arcs, dialogue_and_subtext,
causality_and_payoff, pacing_and_tension, theme_and_symbolism,
world_and_canon, branching_and_agency, cinematography_and_blocking,
performance_direction, sound_and_music_direction, emotional_resonance.

Every reviewer must score every dimension at least **90/100** for a panel's
internal "claimed top-tier" result. Each review supplies identity, role,
method, substantive criticism, and inspectable evidence IDs. Duplicate
reviewers and incomplete scores fail. Scores are **operator-entered claims**,
not verified external judges: no release-quality proof is granted until
reviewer identities, the work reviewed, blind panel methodology and actual
scene/game results are independently authenticated.

Sales, ratings and genre/era benchmarks from the existing
JEEVES_ERA_SALES_QUALITY.md are an independent comparator: market popularity
does not mechanically establish narrative quality and never allows copying
books, screenplay dialogue, game IP or protected media.

## Inputs and commands

Place a typed source pointer manifest at
design/direction_manifest.json:

    {
      "schema":"skeleton.jeeves.story_direction.v1",
      "bible":"design/bible.json",
      "contract":"design/continuity_contract.json",
      "scenes":["design/scene_000001.json"],
      "shotboards":[
        {"sequence":1,"path":"design/shot_000001.json"}
      ],
      "panel":"design/editorial_panel.json"
    }

These are pointers to **existing canonical signed** bible, continuity
contract, and scene sources, not a replacement schema. The accepted scene
source is verified with the original story owner; the continuity contract
uses the original production-history validator. A shotboard contains the
exact original scene_digest and list of canonical cinematic shots.
Pointers cannot escape project design/, symlinks are rejected, missing
or forged signatures fail. The entire listed scene history is replayed
in order; it may contain up to the canonical 9999-scene story envelope.

    python -m skeleton dev game jeeves direction-audit --project .
    python -m skeleton dev game jeeves direction-workorder --project .
    python -m skeleton dev game jeeves production-gap-matrix --project .

The scorecard reports verified pre-render text/canon properties and
submitted panel results separately. Workorders preserve the 90/100 floor,
prioritize missing sections, incomplete character arcs, weak causal hooks,
unperformed lines and incomplete shotboards; no text or old accepted canon
is silently overwritten. A complete game also requires full cinematic
render and actual branching playthroughs before any publication verdict.

Story review rows can be paged and revisited in the existing 9999-scene
canonical history; the developer transport does not lower a quality
threshold when scenes or ratings fail.

## Gap inventory

The code-owned production-gap matrix is in
skeleton/developer/jeeves_game_production_gaps.py.

It enumerates **69 release-evidence gaps in 12 workstreams**. These are
*missing end-to-end release qualifications*, not an unsupported claim that
all 69 features are absent as code. Some have functioning source tools,
others are plans or reference simulations. Actual native app and game
operation is the acceptance criterion.

### 1. Production / application completeness (7)

Full project-to-playable-game path; durable recovery; automatic fail/repair/
recheck; parallel work dependency graph; signed installers; reproducible
release builds; complete end-to-end gameplay from fresh install to ending.

### 2. Literary and narrative production (8)

Finished longform source and all endings; psychology and character arcs;
publishable prose and distinct voices; all plot setups/payoffs; causal
player choice outcomes; every quest solvable through authored variants;
dialogue/subtext originality; identity locks in actual voice/video output.

### 3. Hollywood / cinematic direction (7)

Shotboard coverage; scene blocking and actual moving cameras; real acting
performance; rendered lighting/grade; observed emotional audience response;
interactive cinematic runtime; lip-sync, speech and music synchronized to
actual shots.

### 4. Game mechanics / playability (7)

Living NPC behavior; all genre-specific mechanics; nonlinear path systems;
balanced difficulty; divergent endings verified; all console-controller
layouts; safe durable saves and migration.

### 5. Asset/render/world production (10)

All asset provenance; exact retro pixel identity; complete animated art;
skeletal rigs and stable shadows; fully vivid executable levels; PBR and
materials; detailed 3D mesh/LOD; global illumination; weather/water/foliage;
actual geometry-aware 2.5D–3D cameras and occlusion.

### 6. Music and audio production (4)

Original professional music composition; adaptive score transitions; spatial
sound and Foley; full legal voice performance/localization. PCM remaster
does NOT count as composing a Hollywood-quality score.

### 7. Console, GPU and deployment (7)

All requested native console renderer families; true emulator/port fidelity;
retro-to-HD style validation; native SDK and signing; high-end GPU/3D;
offline low-resource/mobile parity; sustained real performance/thermal QA.

### 8. Editors and user experience (4)

Surface all game editors in Academy/Galaxy/Snowball/Jeeves; accessibility
and player controls; real user-playtester satisfaction; internationalization.

### 9. Evidence and market comparison (4)

Independent historical sales data; independent critic-score normalization;
rights for every asset and learning source; active anti-plagiarism checks.

### 10. Jeeves AI and training systems (6)

Access to trained production checkpoints; challenger/adversarial model gains;
upscale model improvements verified on held-out work; legally sourced
multimedia training; multispectral saturation training; dataset governance.

### 11. Assurance / full releases (5)

Professional per-asset/per-scene QA; all CI and E2E receipts; game/mod
runtime security; real release rollback; actual business/user outcome metrics.

Totals: 7+8+7+7+10+4+7+4+4+6+5 = **69 gaps across 11 workstreams**
(the matrix itself is authoritative; groups are computed from code).
Each is blocked until the *real proof* named in the gap row is obtained.
Do not turn a stub, test fixture, graph, design note or static evidence hash
into proof of release or model training.

## Validation

    python -m pytest -q --noconftest skeleton/testing/test_jeeves_game_direction.py
    python -m pytest -q --noconftest skeleton/testing/test_jeeves_game_multidomain_upscale.py
    python scripts/check_ai_file_tree.py
    python scripts/check_architecture_map.py
    python scripts/check_ai_app_construction.py
    python scripts/check_capability_interfaces.py
    python scripts/check_provider_bootstrap.py

Any failing exact-head GitHub gate, local file-tree mirror drift, unavailable
native renderer, unverified panel, failed source replay or missing full
playthrough keeps production qualification OPEN. No invented signoff or
completion percentages are derived from source-file counts.
