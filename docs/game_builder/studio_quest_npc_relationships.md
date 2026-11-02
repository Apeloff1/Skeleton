# Original NPC relationship consequences — Studio A

A typed original-NPC relationship plan attaches explicit author-reviewed trust
effects to **existing canonical quest stage choices**. No NPC testimony,
emotional state, live simulation, external award, rights, or release evidence is
inferred. The same source digest, initial session digest and action history must
replay successfully before a downstream playable handoff.

## Authoring and playable workflow

1. Load a registered original quest project. Write a private (0600) JSON list
   of authored `[stage_id, choice]` pairs.
2. Propose a plan using `python -m scripts.studio_quest_npc_relationships_cli
   --project PROJECT --actor captain --actor healer --actions /private/actions.json
   --target-ending ENDING`. The returned `relationships.authoring` is a typed
   draft with no invented relationship effects.
3. Save the draft plan to a private JSON file. Edit actor names and initial
   trust, and add explicit `effects` rows with `stage_id`, `choice`,
   `actor_id`, signed `delta`, `reason`, and `reviewed` boolean. The browser
   `--editor-html` option can edit and export existing rows offline.
4. Recompile `--plan /private/npc-plan.json --handoff`. Every actor and effect
   must be reviewed, at least one effect must exist, the target ending must be
   canonically eligible, and no trust overflow may occur. The handoff carries
   replayed choices, exact source/session digests, applied deltas, and final
   bounded trust values. The downstream engine may consume this sandbox state
   but must independently validate its own native behavior.
5. `--publish /private/empty-dir` exclusively creates a 0600 receipt with
   descriptor-anchored publication. `--restore /private/dir` rejects stale
   source, tampered receipts, symlinked inputs and changed action history.

## Bounds and safety

At most 12 original actors, 128 unique authored effects, 64 replay actions,
256 KiB source, 128 KiB typed plan, and 192 KiB receipt. Actor IDs must be
unique slugs. Effects must refer to authored stage/choice pairs and an actor in
the roster. Delta is a nonzero integer between -25 and 25. Trust must stay
within [-100,100] without clamping. The offline HTML editor has CSP hash
pinning and no network access; its exported JSON is never accepted without
canonical CLI compilation. Review cannot create game-world facts or attest
native gameplay.
