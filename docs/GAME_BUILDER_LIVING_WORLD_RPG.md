# Living World RPG — original game-creation production lane

**Status:** This module now implements a second, actually playable genre in
Skeleton. It is not a proposed game-design menu: it has a deterministic
Python gameplay state machine, complete browser controls, an original Godot 4
scene/script, offline packaging, authored source ingress, trace verification,
and 12 executable adversarial test families. It ships alongside the existing
playable puzzle title and independently playable companion practice games.

## Supported worlds and original game mechanics

- **World graph:** 4–12 real connected regions with cyclic roads and, for
  suitable layouts, bidirectional long-distance ferry shortcuts. Movement
  travels along legal links and advances the turn; no teleport command.
- **Living population:** 6–128 unique persistent citizens, with original
  names, roles, temperaments, factions, home locations, workplaces and
  lookout/social areas. Every action advances a 12-turn repeating day;
  morning, work, evening and home/night each last three turns. NPCs are
  actually located according to that schedule for conversations and quests.
- **Meaningful professions and relationships:** citizens have persistent
  home/faction/occupation identity, offer original location-specific
  dialogue, can be introduced once per session and serve as quest givers.
  Party membership, complex individual motives and learned dialogue models
  are *not* claimed as implemented.
- **Faction and narrative systems:** three factions (gardeners, wayfinders,
  makers) support 3–24 independent authored or procedural quest arcs.
  Every arc has a unique NPC giver, collectible item, source region,
  localized objective, and bounded economy reward. Completing a quest
  affects reputation and score and consumes its resource.
- **Persistent player decisions:** actions are typed and bounded: wait,
  travel, talk, gather, resolve and choose a narrative ending. The
  replay-proof engine enforces encounter timing, item ownership, legal
  travel, quest prerequisites, reward accounting, and world identity.
- **Three contrasting narrative outcomes:** stewardship, discovery,
  independence, accessible after a configurable 1–24 real quest
  completions, no more than the number of authored arcs. These choices
  are recorded in irreversible replay history rather than randomized.
  They are **not interchangeable labels**: stewardship requires a completed
  gardeners quest, discovery requires wayfinders support, and independence
  requires makers support. Those requirements are checked identically by
  the Python, browser and native Godot action engines; choosing an
  unsupported outcome is an invalid player action.
- **World styles:** campaign (completes at an ending), postgame (keeps
  playing in an epilogue), and sandbox (remains open regardless of
  narrative progress). Postgame and sandbox are *actually* tested by
  executing an additional action after the ending, not just metadata.
- **Proof and replay:** every deliverable is built only after the Python
  simulator has executed a complete real-time-wait + region-travel +
  NPC-talk + artifact-retrieval + quest resolution + ending trace.
  Each action is hash-chained to the exact original world digest. The
  Godot native project independently replays those actions and compares
  faction trust, inventory, known quests, discussed NPCs, score, ending,
  location and turn count.
- **Adversarial assessment:** at least 128 real story-specific attacks
  in the normal studio pipeline, including forged reputation,
  unauthorized actions, script-injection-shaped commands, teleportation,
  fake quest resources, modified source manifests, tampered replay
  receipts, invented endings and post-completion logic.

NPC fidelity is currently deterministic rule simulation, **not** a
generative social agent or personal-memory neural model. NPCs use a
constant-cost day-phase schedule plus world-state-gated interactions.
That gives reproducibility and scales to consumer-grade hardware, but
does not establish advanced game AI, dynamic faction diplomacy,
or graphics fidelity appropriate for AAA.

## Make an original procedural living world

The original-studio CLI makes the existing proven puzzle game plus the new
narrative game and any companion practice games as one offline source pack:

```shell
python -m skeleton.ai.game_builder.original_game_studio_cli \
  --intent original-intent.json \
  --output /tmp/my-original-two-genre-game \
  --living-world-npcs 64 \
  --living-world-regions 9 \
  --living-world-arcs 18 \
  --living-world-quests 6 \
  --living-world-mode postgame \
  --living-world-ending discovery \
  --companion-practice 2 \
  --mirror-attempts 128 \
  --trusted-local-operator
```

The output has a separate actual playable RPG at
`living_story/index.html`, an editable Godot game in
`living_story/godot/`, its `world.json`, exact
`proof.json`, `release.json`, and
`studio/living_story_mirror.json` + `studio/living_story_almanac.json`.
Every file is covered by the top-level and its nested SHA-256 manifest.
Scripts are handwritten original project code; no crawling or unreviewed
third-party game art is embedded in executable output.

## Human-authored original NPCs and quest storylines

A **custom** game is as important as a generated one. Create an editable,
schema-constrained original blueprint directly from the exact source intent
that the final game will use:

```shell
python -m skeleton.ai.game_builder.living_story_blueprint_cli \
  --intent original-intent.json \
  --output custom-living-world.json \
  --npcs 64 --regions 9 --arcs 18 --quests 6 \
  --mode postgame --trusted-local-operator
```

Edit `custom-living-world.json` with any offline JSON editor. Customize
original region names and atmosphere, the bidirectional region graph,
NPC names/roles/temperaments, home/work/lookout scheduling regions, the
three original faction assignments, quest names/premises, unique objective
locations, and bounded reward values. Preserve exact project/region/NPC/
quest/item identities, and keep at least one path between every region.
Do not add custom executable scripts, arbitrary object types, external
images, remote URLs, plugin calls or unsupported JSON fields; these are
intentionally not deserialized by the importer.

After a separate human originality and playability review, build it:

```shell
python -m skeleton.ai.game_builder.original_game_studio_cli \
  --intent original-intent.json \
  --output /tmp/my-custom-original-game \
  --living-world-npcs 64 --living-world-regions 9 \
  --living-world-arcs 18 --living-world-quests 6 \
  --living-world-mode postgame \
  --living-world-blueprint custom-living-world.json \
  --living-world-human-reviewed \
  --companion-practice 2 --mirror-attempts 128 \
  --trusted-local-operator
```

The source file is bounded to 180 KB, must be a regular non-symlink UTF-8
JSON file, and has rejection for duplicate keys, strange numbers, unknown
fields, excessive text, foreign cross-references, disconnected graphs
and unplayable quest chains. The importer binds exact source SHA-256
and a real winning replay to `studio/living_story_authoring.json`.
Human review is not a substitute for license, trademark or platform
distribution clearance.

## Consumer native game delivery and controls

The Godot 4 source project is a real native game with menu buttons for
NPC interactions, travel, waiting, gathering resources, completing quests,
and selecting an outcome, plus current NPCs, score, faction data, inventory,
objectives, undo, restart and draw-based environment UI.

```shell
godot --headless --path living_story/godot --import
godot --headless --path living_story/godot -- --verify-story
godot --headless --path living_story/godot --export-release Linux living-world.x86_64
godot --headless --path living_story/godot --export-release "Windows Desktop" living-world.exe
```

CI on actual Linux and Windows runners must execute the *exported binaries*,
not merely verify that source scripts were generated. The native validation
requires a `STORY_NATIVE_REPLAY_OK` witness and nonzero exit on divergence.
The main puzzle and companion games have their own separate native witnesses.

**Release distinction:** a runnable unsigned .exe/source project is a
consumer-testable game, but not an automatically commercially approved
consumer product. Hardware compatibility, accessibility, human playtesting,
localization, malware tests, intellectual-property clearance, signing,
platform permissions and publication credentials remain independently
verified by the existing nine-gate consumer assurance subsystem.

## How Jeeves, Dragon, Companion, Wiki and Mirror cooperate

The new capabilities are real registry/execution IDs: `story.generate`,
`story.simulate`, `story.native`, and `story.mirror`. Jeeves approves
the bounded plan; Dragon runs world/narrative generation and compiles the
browser+native source; the mirror exercises 12 adversarial families on
the same proof and package. The companion builds independent practice
titles, and the almanac stores measured simulator evidence and provenance.
A reviewed knowledge/rights integration for external story inputs requires
its **own** explicit provenance and rights approval. References to a
Jeeves model, crawler, wiki, provider API or Dragon-trained network in this
description are not claims those systems have acquired live external
permissions or been trained by this patch.

## Substantial future systems, not claimed as implemented

Actual emergent citizens require bounded persistent agent memories,
multi-party relationships, emotion and need states, companion agents,
faction diplomacy, local economics and dialogue/quest generation with
tool-aware content safety. Worlds need navigable 2D/3D scenes, physics,
animation, sprite and asset pipelines, audio, accessibility and tested
hardware-specific population schedulers. These are distinct engineering
milestones requiring executable gameplay, proof and user testing, not
pre-generated variations or inflated LOC counts.
