# Skeleton — full game-production gap atlas (source-based audit, 2026-10-16)

Status: cross-module evidence review, NOT a claim every executable file has
been individually compiled or tested. The **complete list of known workstreams**
below is a broad production-domain inventory; hidden defects may remain.
Every item includes a required closure receipt. The live GitHub PR checks and
target-hardware tests take precedence over this document.

## What is actually present today

- Canonical GameForge Godot source pipeline and headless boot, testable
  reference game mechanics and authored source receipts:
  skeleton/developer/game_cli.py, skeleton/forge/playtest.py,
  skeleton/context/pipeline.py. **Not a shipped completed longform game.**
- Signed source-level story bible, full-history reparse, plot bookmark,
  chapter/act/scene continuity, original voice/face/style fingerprints,
  cinematic shot-board validation, and chapter work orders:
  skeleton/ai/game_builder/story_canon_fabric.py,
  story_continuity_assurance.py, story_chapter_context.py,
  story_cinematic_review.py, story_workspace.py,
  jeeves_production_director.py. This verifies *source statements*,
  not measured film/directing enjoyment, actual acoustics or facial frames.
- Signed-source direction metrics and 14-dimension professional quality
  claims (new story_direction_quality.py) detect source-level dramatic
  deficiencies and produce non-mutating revision work orders.
  Independent expert reviews and rendered film quality still unverified.
- Original system editor fabric documents **43 editors / 215 typed controls**:
  docs/GAME_BUILDER_SYSTEM_EDITOR_FABRIC.md. Config surfaces are NOT
  full native implementations of 43 production-grade engines.
- Historical platform/port registry documents **524 candidate platforms**
  and **30 approximate presets**, not complete actual SDK/export coverage:
  docs/GAME_BUILDER_PLATFORM_PORTING.md.
- Separate hardware-emulator evidence dashboard documents **169 identities,
  99 declared libretro mappings, 70 unmapped targets and 137 generic
  controllers** as of its dated snapshot. These are declaration counts,
  not measured core boots or correctness:
  docs/game/EMULATOR_169_QUALIFICATION_GAP_MATRIX_2026-10-15.md.
- New developer workbench has original sprite sheet animation, source-led
  environment dressing, original audio DSP, true pixel compositing,
  2.5D/2.9D camera preview, top-tier market comparison and local
  evidence-first upscale priority queues. These do NOT constitute every
  era's genuine GPU renderer or general neural creative generator.
- Emulator continuation and large native input plans documented in
  docs/game/FULL_NATIVE_GAME_PLAYTHROUGH_2026-10-15.md. The document
  explicitly does not claim full actual game runs occurred.
- Original game studio document labels implementation as an
  **offline executable vertical slice**:
  docs/GAME_BUILDER_ORIGINAL_STUDIO.md.
- The canonical 100 chapters, 1,000 global acts, 9,999 scenes baseline
  is a signed source contract, not 9,999 rendered or playable scenes:
  docs/JEEVES_100_CHAPTER_1000_ACT_9999_SCENE_STUDIO_STANDARD.md.

## Status vocabulary

- **SOURCE-IMPLEMENTED / UNQUALIFIED**: code or schema exists, but
  real production output, subjective quality or native/hardware proof is absent.
- **REFERENCE ONLY**: deterministic emulation, frame or gameplay sample
  is not a finished installed game/runtime or publisher-level capability.
- **INTEGRATION GAP**: neighboring working modules lack a proven end-to-end
  connection and source/receipt chain.
- **MISSING ACCEPTANCE EVIDENCE**: a capability might work, but release
  cannot be certified without actual execution, measurements or review.
- **DESIGN / COVERAGE GAP**: catalogued plans or examples do not cover
  all requested historical eras, genres and hardware.

## Complete known gap register by production domain

Priority P0 = blocks a finished, high-quality original game.
P1 = blocks top-tier competitiveness or general cross-era coverage.
P2 = improvement/scale once working paths are qualified.

| # | Priority | Production domain | Actual gap / not-yet-proven acceptance | Required evidence / exit criteria |
|---|---|---|---|---|
| 01 | P0 | End-to-end product assembly | Game creator conversation → original authored game → full runtime → package → install has no verified single-path acceptance | Fresh-install human/operator journey and playable signed artifact |
| 02 | P0 | Jeeves real creative model | Provider-backed new draft capability exists but longform chapter-by-chapter production quality unqualified | Real checkpoint/provider dispatch, provenance, review and approved source integration |
| 03 | P0 | Canonical story continuity | Signed full-history source checks exist; end-to-end chapters/scenes not fully authored or rendered | Complete target history and repeated no-drift canon replay |
| 04 | P0 | Creative-writing quality | Source structure is not literary originality, prose voice, thematic subtlety or emotional power | Two or more independent qualified manuscript evaluations with actual cited passages |
| 05 | P0 | Film direction quality | Shot-board source grammar not achieved film acting, cinematography or editorial rhythm | Real rendered shots/edits, cinema/editor panel screening and timed critique |
| 06 | P0 | Narrative causality | Referential links alone do not show motivated payoff, dilemma or changing stakes | Source-linked setup/payoff ledger plus blind human comprehension test |
| 07 | P0 | Character dramatic arcs | Identity/state tracking does not prove believable desire, flaw, reversal and transformation | Motivation-to-choice-to-consequence arcs, source and audience review |
| 08 | P0 | Dialogue performance | Canon source/voice identity not natural speech, distinct subtext or timed delivery | Character blind voice identification, professional table read and acoustic review |
| 09 | P0 | Interactive player agency | Reference choices do not prove distinct playable consequences over a full game | Branch coverage, unique endings, state transition proofs and playthroughs |
| 10 | P0 | Full scene production | 9,999 scenes schema is not a completed game | Authored, signed, rendered and playtested stage/scene evidence where required |
| 11 | P0 | Book/film-to-game adaptation | Prose, shot boards, quests and playable scenes are not fully joined | Every canonical narrative beat maps to executable player action or qualified cutscene |
| 12 | P0 | World/cast memory | Canon retrieval exists, but no qualified long-horizon AI recall across full scale | Source-context retrieval coverage and no hallucinated cast/world recall |
| 13 | P0 | Professional reviewer/adversarial loop | Scores are operator claims, no independent critic film/novel quality certification | Real qualified reviewers, inter-rater disagreement handling, persisted critique |
| 14 | P0 | Author approvals and IP | Local SHA acknowledgement is not an external release or copyright clearance | Legal/source provenance, consent, original assets and protected creator approval |
| 15 | P0 | Complete quest and mission arcs | Quest/scene editor/reference engines not proven with whole-game failure/recovery | All critical and optional quests solvable with state/faction/ending evidence |
| 16 | P0 | Runnable engine integration | 43 editor control schemas do not imply 43 complete runtime implementations | Editor-to-scene-to-play-to-asset pipeline for every claimed supported system |
| 17 | P0 | Full game playthrough | Headless boot and bounded episodes do not prove narrative-to-ending completion | Automated and human start-to-end runs with saves, branches, input and receipts |
| 18 | P0 | Native rendering by console | Era reference renderer / emulator does not prove per-console production quality | Console-specific measured frames, color, animation, controller and export |
| 19 | P0 | Integrated audio engine | PCM remaster only; spatial, dynamic adaptive stems and mix delivery not proven | Executed timeline with real audio clips, spatial test and hearing QA |
| 20 | P0 | Actual finished release | Source zip is not signed store/install/update/recovery path | Native first-install boot, binary provenance, sign/notarize where applicable |
| 21 | P1 | Historical era coverage | Registered console names and approximate presets not complete render systems | Per-target source renderer, libraries, profiles, testing and export |
| 22 | P1 | Console SDK/toolchains | Proprietary platforms have unavailable or unqualified vendor SDK paths | Licensed toolchain access, legal SDK use and native binary tests |
| 23 | P1 | Emulator fidelity | 169 declared identities, 99 mapping candidates, no universal qualified emulation | Real core load, game input/frame/audio equality and save/rewind evidence |
| 24 | P1 | Controller accuracy | 137 generic panels in dated snapshot; no measured per-console layout complete | Genuine input descriptors, latency and correct labeled layouts |
| 25 | P1 | 2D upscale fidelity | Deterministic nearest/Scale2x not artistic redraw or full temporal source preservation | Asset-by-asset stylistic artist review and frame comparison |
| 26 | P1 | 2.5D/2.9D camera execution | Numeric matrices and image-plane projection do not rotate playable geometry | In-engine camera orbit, billboard correction, occlusion and collision proof |
| 27 | P1 | 3D geometry authoring | Triangle reference previews are not a full mesh/rig/model production stack | Sculpt/LOD/UV/topology pipeline with material and gameplay integration |
| 28 | P1 | PBR and material pipeline | Roughness, normals, GI, AO, transmission, SSS, raytracing unqualified | Material-specific golden image/temporal tests across quality tiers |
| 29 | P1 | 3D world scaling | Texture rescale cannot generate exquisite world-wide geometry detail | Collision-safe streaming assets, LODs, lightmaps and artists' approval |
| 30 | P1 | Animation suite | Procedural sprite strips not full skeletal, inverse kinematic or mocap | Rig/skeleton, skin, blend-tree, transitions and facial/body tests |
| 31 | P1 | Shadows and lighting | Simple contact shadows do not prove realistic era-appropriate lighting | Physical/stylized shadow implementations, illumination probes, native fps |
| 32 | P1 | Foliage/clutter richness | Procedural dressing JSON not automatically quality world art or navigation | Actual stage execution, density/readability comparisons and art review |
| 33 | P1 | Atmosphere/weather/particles | Vividness numeric metrics do not render cinematic environments | Live storms, particles, fog, day/night, audio link and effects verification |
| 34 | P1 | Parallax/CRT authenticity | Alpha composite is not exact CRT/LCD/analog output or shader stack | CRT/scanline/mask/aspect/lag source-device comparison |
| 35 | P1 | Cinematic editor | Source shot grammar and reference timeline not editable 3D film-quality timeline | Shotgraph, blocking, multi-angle, lens, camera moves, render output |
| 36 | P1 | Acting/lipsync/voices | Signed voice ID/face ID not generated speech or rendered lip-sync consistency | Consent-backed voice acoustics, timed phonemes, facial frame QC |
| 37 | P1 | Music score and orchestration | Source WAV DSP cannot write a film/game score, original motifs or adaptive cues | Original licensed multi-stem composition, adaptive engine, listening panel |
| 38 | P1 | Full NPC behavioral societies | Active prototype state scope not commercial multi-city social simulation | Population persistence, scheduling, factions, autonomy, traversal and memory |
| 39 | P1 | High-density game worlds | Scene/asset/world partition docs not qualified for millions of live assets | Streaming, origin shift, memory/CPU budgets and gameplay verification |
| 40 | P1 | Combat/physics/vehicles | Various editor controls/reference sims not one qualified production stack | Tuned collision/game feel/latency/physics accuracy for each engine genre |
| 41 | P1 | Genre completeness | 43 editor families do not prove production games across every genre | Genre-specific complete games, systems/assets/UI/QA for each family |
| 42 | P1 | Level designers and AI directors | Stage grid route checks not production-level encounter/mission pacing | Dynamic encounters, player proficiency and authored playtests |
| 43 | P1 | User interface and accessibility | Config surfaces are not universal readable/rendered accessible game UX | Real menus, HUD, navigation, assist modes, multi-input user tests |
| 44 | P1 | Localization and culture | Text schemas not validated book-grade localized dialogue, subtitles or voice | Native-review translation memory, font/UI overflow and cultural review |
| 45 | P1 | Networking/multiplayer | Editor declarations cannot prove authoritative netcode or synchronization | Deterministic rollback/server QoS/security and online soak tests |
| 46 | P1 | Save/load/modding | Native checkpoints and editors not per-game migration/rollback stability | Cross-version save round-trip, corruption and user recovery drills |
| 47 | P1 | Cross-platform packaging | Reference/Godot source not Windows/Linux/mobile/console release equivalence | Clean first-install matrix and signed binary builds |
| 48 | P1 | Performance and optimization | Static timing submissions not representative device frame/memory benchmarks | Sustained p99 timings, memory, thermals, low-spec and GPU captures |
| 49 | P1 | Game QA and fuzzing | Simulation/fuzz receipts not exhaustive real player state/action coverage | Branch/quest/state coverage, replay, rare deadlocks and long saves |
| 50 | P1 | Critic/sales evidence | Operator market stats not independently sourced and normalized for age/port | Publisher/audited units, review aggregation and independent corroboration |
| 51 | P1 | Book/film quality references | Commercial books and films cannot use console unit-sales comparison | Medium-specific verified cohorts, awards/editorial corpus, sales/box-office normalization |
| 52 | P1 | Model upscale training | Priority queue is not gradient descent or durable approved checkpoint improvement | Rights-cleared datasets, real checkpoint I/O, held-out gains and promotion |
| 53 | P1 | Adversarial critic model | Static rules vs separately trained rival narrative/art critic unproven | Independent reviewer model, disagreements, epistemic audit and upgrade gates |
| 54 | P1 | Retrieval/provenance | Large source crawler and almanac do not prove rights-cleared narrative weights | Full citation/provenance, licensing, corrections, freshness and retention |
| 55 | P1 | Studio orchestration | Resumable production slices require actual full cross-discipline conductor | Multi-role job graph, immutable revision dependencies, retries and conflict resolution |
| 56 | P1 | Experience feedback loop | Numeric QA is not actual market reception or playable game feel | Blind user study, player retention, emotional/narrative comprehension samples |
| 57 | P1 | Autonomous finances/resources | No unlimited free GPU/disk; long projects require capacity-aware scheduling | Accounted storage/compute, checkpoints and explicit budgets |
| 58 | P1 | Studio product UI | Academy/Galaxy Studio/Jeeves cockpit workflows not verified as one complete product | Full navigation and editor surfacing with actual projects and rollback |
| 59 | P1 | CI/release governance | Queued/cancelled/failed workflows are not exact-head green signoff | Full CI, architecture gates, security, provenance and clean installer |
| 60 | P2 | Data/scenario portfolio | Experimental comparator breadth not automatic real game production capability | Rights-cleared controls and actual benchmark/replay validation |
| 61 | P2 | Artistic variation | Infinite combinations are not curated quality games | Controlled originality/canon/player impact sampling |
| 62 | P2 | Studio analytics | Work ledgers not creator-ready executive dashboard or provenance decisions | Usable scorecards, per-asset evidence drilldowns and review history |
| 63 | P2 | Pipeline documentation | Draft/historical docs may contradict current branch or authoritative source | Release-matched machine-readable capabilities, documentation audit |
| 64 | P2 | Disaster/recovery | Local append-only histories not offsite backups or indefinite retention guarantee | Versioned backups, integrity restoration, controlled retention |
| 65 | P2 | Store/commercial lifecycle | Game-generator tools do not cover monetization, age rating, customer support | Legal/store certification, age ratings, telemetry privacy and post-release care |

## Professional story and Hollywood direction acceptance metrics

Use source-measurable indicators as **diagnostics**, never as a replacement
for professional judgment:

1. **Causal continuity**: signed event references, source-valid setups and
   payoffs, no contradictions, explicit consequences of important choices.
2. **Character transformation**: how goals, beliefs, loyalties, loss and
   consequence produce evidenced change rather than repeated dialogue.
3. **Dialogue voice distinctiveness**: identical utterance repeats,
   vocabulary distribution, speaker attribution, conversational intent,
   motivated subtext and scene-to-scene voice consistency.
4. **Dramatic pacing**: beat density, significant reversals, suspense
   delta, chapter openings/endings, quiet scenes vs crescendos.
5. **Screenplay grammar**: performed dialogue mapped to exact shot
   coverage, shot geography, axis continuity, cuts, gaze, camera, music
   and actor/costume/lighting continuity.
6. **Agency and player narrative**: choices genuinely changing playable
   quest/world state, endings and story; no cosmetic branches as if equal.
7. **Emotional/story reception**: actual qualified readers, editors,
   writers, directors and playtesters; blind comprehension and engagement
   evidence. Numerical readings alone are NOT art.
8. **Book-quality manuscript standards**: voice, interiority, causality,
   originality, vivid description, layered theme and prose rhythm.
9. **Film-level direction standards**: shot motivation, blocking,
   composition, performance, sonic design, editing rhythm, emotional
   continuity and playable transitions.
10. **Rights and historical original work**: independently documented
   originality, consent, protection against copied fictional settings
   or lifted movie/game/book text.

Jeeves story_direction_quality.py uses **14 qualitative dimensions**;
the requested excellence policy requires each independent expert score
to be >=90/100, with at least two distinct reviewers spanning literature
and film/game direction. Those are policy *targets*. Operator-submitted
scores are clearly marked unverified; no Hollywood level or publisher
acceptance is certified by a locally filled JSON field.

Story drafts use the existing canonical signed StoryCanon full-history
verifier. New --direction-source authoring opt-in transfers only bounded
aggregate metrics and revision targets, while binding the whole dossier
SHA to the generated proposal. Original accepted story files remain
owned by the canonical creator and approval pipeline.

## Recommended closure sequence

P0-A: Qualify an original full game from conversation through install,
save, branching ending, multiple real playthroughs and consumer UX.

P0-B: Complete one exceptional original 100-chapter canon story at
book/film/interactive professional creative quality, with signed full
history and independently verified critiques. Do not require all 9,999
scenes to be equally mandatory in games for which the author has not
selected that longform format.

P0-C: Wire the actual story, cast, scene/cutscene, assets, animation,
music and branching gameplay to the same signed production project and
live renderer, including rollback and reviewer dispute handling.

P1-D: Qualify a complete original production renderer for representative
2D, 2.5D, 3D and modern hardware targets, then expand one target at a
time with real source, controller, performance and native binary evidence.

P1-E: Perform rights-cleared actual model training, validate on unseen
games/scenes and promote only improvements that do not regress canon,
media style, playability or legal provenance.

P1-F: Harden CI and installer, studio UI integration, backup/resource
recovery, professional art and audio pipelines and commercial release
certification.

**Percent complete:** no global percentage is defensible from these
source and CI checks. Individual verified controls/target counts may be
reported only with exact supporting execution evidence. A registered
platform or a signed story schema is not a completed playable game.
