# Jeeves Director Interactive Runtime + Dragon Training Inputs

> **October 16 live-runtime extension:** The scene atlas now also exports a
> source-bound Godot quest UI that can execute canonical Director logic through
> an explicit local Python server. New exports use a `-live-v2` directory
> suffix without replacing older atlas files. See
> [Live Godot + Dragon research lab](JEEVES_GODOT_LIVE_DRAGON_LAB.md).
> This still does not establish native engine acceptance or released assets.


This milestone slice closes part of the gap between scripted Director
campaigns and game-development production. The canonical Python Director
runtime (not a simulated chat response) now accepts **individual operator
choices**, checks each choice against the current quest state, persists
append-only replayed journal entries, and measures how sessions diverge.

This is a prototype development workflow. It does **not** certify an installed
game, full visual game world, audio playback, professional narrative quality,
model training, or real native platform playtests.

## A. Interactive, durable gameplay-logic sessions

Work within an existing original game workspace with an explicitly reviewed
Director campaign at `design/director_campaign_source.json`:

```bash
python -m skeleton dev game jeeves director-session-begin \
  --project ./original_game --source design/director_campaign_source.json --session hero_a
python -m skeleton dev game jeeves director-session-status \
  --project ./original_game --session hero_a
python -m skeleton dev game jeeves director-session-step \
  --project ./original_game --session hero_a --choice wait:wait
# Use an exact "choice" value returned in the prior response.
python -m skeleton dev game jeeves director-session-step \
  --project ./original_game --session hero_a --choice travel:scene_01
python -m skeleton dev game jeeves director-session-begin \
  --project ./original_game --source design/director_campaign_source.json --session hero_b
python -m skeleton dev game jeeves director-session-compare \
  --project ./original_game --session hero_a --other-session hero_b
```

Each move must be in `available_director_actions`. An invalid scene,
unavailable quest action or stale campaign is rejected. Journals use
`.jeeves/director_sessions/<session>/00000000.json` for immutable genesis
and consecutively named, create-only signed action receipts. Every session
status replays the full action chain through `director_step`, checking
the before/after state and source identities. A local exclusive writer lock
prevents concurrent steps. Interrupted locks are not silently stolen; inspect
the project before manually recovering from a stale `.lock` file. Runtime
recording does not impose a game-time expiry; per-file and sequence bounds
exist for resource safety. Unlike scripted multi-route generation, these
actions are chosen by the CLI operator one turn at a time.

## B. Native Godot 4 scene/cast/cinematic preview

```bash
python -m skeleton dev game jeeves director-atlas-export \
  --project ./original_game --source design/director_campaign_source.json --dry-run
python -m skeleton dev game jeeves director-atlas-export \
  --project ./original_game --source design/director_campaign_source.json
python -m skeleton dev game jeeves director-atlas-verify \
  --project ./original_game --source design/director_campaign_source.json
```

The exporter writes a deterministic, create-only Godot 4 project below
`build/director_atlases/<world-sha-prefix>/`. Its Godot scene has navigable
location buttons, story setup, cast and props, camera/light/weather/audio
*descriptions*, declared gameplay affordances, quest stage mapping, and
cinematic timeline inspection. Authored text stays inside `director_world.json`,
not generated GDScript statements; the script is static. The source-hash
verifier is read-only and rejects changed generated files while allowing
Godot's normal `.godot` cache directory. This scene atlas is a **visual and
navigational preview**: canonical quest completion remains in Python and
Godot parsing/runtime still needs actual execution to be certified.

## C. Typed game-engine event bindings

```bash
python -m skeleton dev game jeeves director-bindings \
  --project ./original_game --source design/director_campaign_source.json
python -m skeleton dev game jeeves director-bindings-publish \
  --project ./original_game --source design/director_campaign_source.json \
  --approve <candidate_sha256>
python -m skeleton dev game jeeves director-bindings-check \
  --project ./original_game --source design/director_campaign_source.json \
  --digest <candidate_sha256>
```

Scene-by-scene contracts define the canonical `travel`, `use`, and `wait`
actions, target affordances, quest-stage dependencies, cast/props, scene
links, camera/audio/lighting contracts, and typed cinematic cue timelines.
Published bindings are exact-source, no-overwrite JSON in `design/`.
Every later engine adapter should re-evaluate the actual Director action set
at interaction time rather than treating static bindings as permission to
complete quests. Declared bindings are an integration contract; they do not
prove the native UI is yet wired to the Python logic runtime.

## D. Dragon learns from *real CLI choice receipts*

```bash
python -m skeleton dev game jeeves dragon-session-lesson \
  --project ./original_game --session hero_a
python -m skeleton dev game jeeves dragon-session-lesson \
  --project ./original_game --session hero_a --approve <candidate_sha256>
```

The research candidate replays the local journal and extracts actual selected
actions: route sequence, visited scene counts, interaction type frequencies,
quest results and final state SHA-256. It includes focused questions for
subsequent actual game playthroughs. Admission produces a create-only record
under `.jeeves/dragon_replay_candidates/interactive_<digest>.json`.

The journal does **not** prove a human preferred or enjoyed an interaction,
that footage was captured, that a licensed training set was built, or that
production checkpoint weights changed. The user's earlier Dragon-reviewed
observation intake is a separate consent-controlled subsystem.

## E. Dedicated verification

```bash
python -m unittest tests.test_jeeves_director_interactive
python -m unittest tests.test_jeeves_director_production
python -m unittest tests.test_jeeves_dragon_game_handoff
```

New tests cover session replay, the write lock, forged receipts, changed
source, valid/invalid choices, divergent session comparison, Godot atlas
source integrity and tampering, Dragon candidate explicit admission and
binding contract drift. This work introduces **no global CI workflow** and
no new compulsory merge gate. Until executed on the real repository/runtime,
these are committed regression specifications, not proof of passing tests.

## Next engineering frontier

Wire a native game-runtime provider to the Director event contract, load
approved textures/audio/animation, implement full interactive scene action
completion and reversible save/load inside the engine, and perform actual
fresh-install multi-branch player journeys. Only then can visual, accessibility,
performance, replay parity and model-learning quality be measured against
real-world acceptance criteria.
