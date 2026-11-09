# Original Scene and Quest Director: build guide

Generate a full editable blueprint:

```shell
python -m skeleton.ai.game_builder.quest_director_cli --mode template --project original_world --regions 16 --stages 3 --genres main_story,escort_leash,dungeoneering,infusion,timed_combat --trusted-local-operator --output original-world.json
```

Edit the original story bible, scene graph, cast, props, camera, lighting, weather, music, action affordances, timed cinematic cues, quest stages, required AND conditions, alternative OR solutions and optional goals. Import is exact-schema, bounded, human-reviewed and rejects foreign code fields.

Build the offline playable browser product:

```shell
python -m skeleton.ai.game_builder.quest_director_cli --mode build --blueprint original-world.json --human-reviewed --trusted-local-operator --output original-game
```

The product contains `index.html`, the full authoring JSON, main-story action replay, method comparisons, earned story ending receipts, adversarial mirror report, almanac measurements and an integrity manifest. The browser preview now renders simplified actor staging, camera movement, lighting and subtitle cinematic cues. It is not a completed 3D animation, sound or movie renderer.

The separate `quest_encounter_runtime.py` simulates physical escort following, leash-distance non-colliding characters, timed combat, rival fights, waves and defensive reinforcements. Its simulation is not yet connected to every director scene action or native game engine.

**Known accuracy gap:** The Python director's speed award for later quest stages uses an incorrect reference to earlier stage duration rather than the new stage start timestamp. First-stage timing and other bonuses have executable tests, but later-stage scoring must be corrected and verified before parity claims.

**Release state:** `review/consumer_gate.json` remains publication-blocked. The source preview is not a standalone native release. Independent rights, human playtests, hardware, accessibility, malware, localization and publisher approval are outstanding. Adversarial scheduling/calling cadence has not been modified.
