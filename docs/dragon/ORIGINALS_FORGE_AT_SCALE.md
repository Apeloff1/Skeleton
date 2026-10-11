# Dragon Originals Forge — executable originality at scale

**Status: implementation committed; latest-branch CI and release validation are separate.**

This is a source-first original game prototype generator, not a numbering
scheme pretending that billions of finished copyrighted entertainment
products exist.

## The problem being solved

A procedural forge that generates billions of seeds but only one actual
style of game has not produced billions of original games. A new tile color
or terrain noise seed is not enough.

Dragon's Originals Forge defines independent **executable game-rule
programs**, generates actual gameplay choices and consequences, combines
them with original living-world lifecycle/terrain designs, and can retain
independently replayable source prototypes in a database.

The system must prove the difference between two original candidates from
what a player **can actually do**, not from a marketing identifier.

## Exact capacity, with truth labels

| Dimension | Exact address capacity | What is demonstrated |
|---|---:|---|
| Original mechanical roots | 32 authored verbs | Every enabled root has an action, cost, reward, changed world position or state and exact replay |
| Per-root implementations | 4 settings: absent, basic, advanced, intensive | Missing action vs real cost/reward/mastery differences |
| First 24 roots, binary | 16,777,216 | Distinct available action sets; a selected pair can be separated by an actual gameplay witness |
| Full 32 roots, binary | 4,294,967,296 | Distinct available action sets spanning postgame, endings, survival and eras |
| All 32 roots, four levels | **18,446,744,073,709,551,616** | Reversible base-4 rule programs; each differing level has a causal difference in its primary mechanic |
| Directional two-mechanic interactions | 1,024 | Executable earned cross-domain actions, not 1,024 physics engines |
| Journey strategy families | 16 | Player actions and independent replay; measured sequence differences, never fabricated claims of global originality |
| Existing World Codex | 128 axes, 256 levels per axis | Separately defined executable codex simulation; all 128 values can influence linked Original mechanics' cost, reward and movement |
| Independently published games from index arithmetic | **0** | A mathematical address is not a cleared game release |

The four-level mechanic program space exceeds **18 quintillion**.
Environmental Codex and game rules are independent composition layers;
multiply these capacities only as theoretical addresses, not as audited
unique human experiences.

## Why there really are millions of different executable rules

For any two distinct binary mechanic masks, there is at least one mechanic
whose enabled bit differs. That mechanic's action is present in one program
and unavailable in the other. This is a constructive separating witness.

For any two distinct four-level programs, there is at least one mechanic
whose level differs. Its action is either unavailable in one program or
has different resource requirements and observable mastery/evolution
effects in the others.

Each difference can be verified by the actual state-transition simulator
(`distinguish`). No need to enumerate billions of designs
to prove this injective **rule behavior** property.

**Limits of this proof:** It is not a claim that every combination
corresponds to an aesthetically different game, independently meaningful
play loop, legally clear original story, finished title, or subjectively
enjoyable challenge. Context and balance can diminish differences, so
human playtesting and originality review remain essential.

## Active root mechanic families

The 32 authored roots have their own gameplay verbs:

1. Terraced trails
2. River navigation
3. Aerial thermals
4. Tidal passages
5. Storm shelters
6. Snow bridges
7. Rotating corridors
8. Doubleback caches
9. Scenic detours
10. Secret keycraft
11. Portal alignment
12. Rail timelines
13. Open seas
14. Orbital transfer
15. Ecology succession
16. Creature migration
17. Settlement growth
18. Salvage economy
19. Artisan crafting
20. Seasonal farming
21. Merchant convoys
22. Faction diplomacy
23. Social memory
24. Branching chronicles
25. Alternate conclusions
26. Postgame repair
27. Survival foraging
28. Hardcore perils
29. Archaeology
30. Research laboratories
31. Terrain terraforming
32. World era cycles

Each root operates on a player economy, position, world history,
technology/research, progression or story variables. The four levels
change actual effects, not just their names.

The original rules may be linked to a parent
`dragon_world_codex` design. Four of the existing
128 environmental values are assigned to each mechanic: environmental
requirements, rewards and independent X/Y movement factors. The Codex
does not get replaced by a dummy address or solely hashed into a seed.

## 1,024 emergent directed interactions

For roots \(A\) and \(B\), interaction
`fusion_A_B` is distinct from
`fusion_B_A`:

- Both mechanics must exist in the rule program.
- Both must actually be practiced to reach the required mastery.
- Self-specialization needs the same root to be practiced twice.
- The fusion spends player energy and awards specific resources.
- The directed pair changes the character's location, world era,
  learned skill progression and its persistent game-state digest.
- The second direction has a different spatial/result projection.
- Unimplemented or not-yet-earned routes remain locked.

A creator can request a page of 1–64 out of 1,024 interactions rather
than dumping a huge control list into the player interface.

These are game-state interaction primitives, not 1,024 simulated
vehicles or handcrafted character quests.

## Original prototype materialization

A **full-width 32-bit binary nucleus** selects an exact original
action rule set, including optional endings, hardcore risk, ecology,
realms, postgame work and world-era changes.

`dragon_original_prototype_factory.materialize(nucleus)` creates:

- The original 32-mechanic game program with an exact source digest
- A rule-selected compatible living-world style and end-state lifecycle
- A deterministic original premise and named candidate title
- Real independently replayed mechanics-game journeys
- A separate actual replayed living-world route and ending status
- Biome/environment context and a reproducible world fingerprint
- Gameplay diversity measurements for the *sample actually executed*
- Separate, still-open release blockers for original art, audio, characters,
  independent literary review, human playtesting, platform builds,
  copyright/trademark and other rights evaluation

The two game layers have independently verified gameplay receipts.
**They are not yet seamlessly fused into a full realtime AAA runtime.**

The API offers a single prototype, a small bounded batch, and a
pairwise game-behavior difference witness. The Expo Originals Forge can
edit all 32 mechanics or inspect a full 32-bit candidate nucleus.

## Production of millions of candidate records, without pretending

The exact 4.29 billion design addresses are not materialized at startup.

`dragon_original_candidate_spool.py` provides an actual
SQLite persistence lane with:

- At most 128 materialized playable source-game candidates per transaction
- One stable integer primary key per original rulebook nucleus
- Real source-game and living-world fingerprints
- JSON replay evidence and a SHA-256 checksum for each candidate
- Atomic transaction rollback on conflict
- Idempotent resumption only after independently re-materializing and
  comparing already-saved game proofs
- Fail-closed behavior for altered records or changed source/world outcomes
- No "published" or "compiled" claim, even for successfully verified
  gameplay candidates

Example for an operator-approved **local** source-only batch:

    python -m skeleton.ai.webcrawler.dragon_original_candidate_spool \
      --authorized-local \
      --db ./dragon-originals.sqlite \
      --start 0 --count 32 \
      --routes 2 --steps 12 --seed 1977 --verify

A million candidates require many deliberately scheduled bounded jobs,
significant CPU/storage and ongoing auditing. This session has **not**
run one million candidate generations. The implementation makes
reproducible multi-batch generation *possible*, rather than reporting
fictional completed work.

Do not execute this on untrusted users' inputs or exhaust consumer
hardware with unlimited simultaneous workers.

## Interface and API

Product routes:

- `/dragon-originals-forge` — editable 32-root game
  design, exact decimal 64-bit program index, optional parent World Codex,
  causal gameplay proofs, interactive player actions, paged earned
  fusions, 16 sample playstyles, and full-width original candidate preview
- `/dragon-living-world` — lifecycle/ending, large
  original worlds, changing mazes, save/restore and postgame
- `/dragon-world-codex` — 128-axis authored environment
  and progress system

The authenticated backend paths include:

    GET  /api/dragon-academy/native/production/worlds/originals/catalog
    POST /api/dragon-academy/native/production/worlds/originals/preview
    POST /api/dragon-academy/native/production/worlds/originals/play
    POST /api/dragon-academy/native/production/worlds/originals/interactions
    POST /api/dragon-academy/native/production/worlds/originals/compare
    POST /api/dragon-academy/native/production/worlds/originals/nucleus
    POST /api/dragon-academy/native/production/worlds/originals/campaign
    POST /api/dragon-academy/native/production/worlds/originals/campaigns
    POST /api/dragon-academy/native/production/worlds/originals/prototype
    POST /api/dragon-academy/native/production/worlds/originals/prototypes
    POST /api/dragon-academy/native/production/worlds/originals/prototypes/compare

All expensive generation, editing, cross-mechanic analysis and batch
playback paths require authenticated creator/editor permission. Invalid
indices, invalid module settings, unsafe action histories and impossible
mastery shortcuts fail closed.

## CI validation and release standard

The Dragon Native ROM Build workflow has a dedicated Originals Forge
gate for rule rank/unrank, 32 independent modules × three active levels,
causal distinguishing witnesses, 1,024 directed fusions, 16 sampled
journey strategies, individual candidate composition, durability,
idempotence and tamper rejection.

Locally:

    python -m compileall -q \
      skeleton/ai/webcrawler/dragon_original_mechanic_forge.py \
      skeleton/ai/webcrawler/dragon_original_campaign_forge.py \
      skeleton/ai/webcrawler/dragon_original_prototype_factory.py \
      skeleton/ai/webcrawler/dragon_original_candidate_spool.py

    python -m pytest -q \
      tests/test_ai_dragon_original_mechanic_forge.py \
      tests/test_ai_dragon_original_mechanic_fusions.py \
      tests/test_ai_dragon_original_campaign_forge.py \
      tests/test_ai_dragon_original_prototype_factory.py \
      tests/test_ai_dragon_original_candidate_spool.py

    python -m pytest -q \
      backend/tests/test_dragon_original_mechanics_routes.py \
      backend/tests/test_dragon_original_prototype_routes.py

A complete original game release still requires actual authored visual/audio
materials, creative narrative diversity, external rights verification,
human-centered balance and accessibility playtests, multiple real route
solvers when relevant, platform-native executable builds and verified
runtime/device behavior. The 64-bit combinatorics and 32-bit binary
mechanics are **design infrastructure**, not substitutes for this work.

## Next engineering depth

The obvious next milestones are much larger than adding more arbitrary
genome axes:

- Joint real-time runtime that fuses rulebook, environmental Codex, player
  survival, complex world geometry and story flags without inconsistent state
- Procedural original sprite, material, animation, sound and music generators
  with stronger creative expression and rights checks
- Causal simulation of AI ecological agents, economies and faction societies
  rather than scalar counters alone
- Persistent multi-world streaming, map editing, environmental hazards and
  genre-native movement physics, with rigorous completion policies chosen per
  game style
- Rich player-facing native editors, accessible controls, long play sessions
  and optional endings that cause lasting world transformations
- Human feedback-based variety/fun evaluation, near-duplicate rejection
  and actual completed native-game release certification

The implementation's source evidence is a foundation for those real
production systems. No copyrighted commercial game title is imported or
reproduced by these mechanics.
