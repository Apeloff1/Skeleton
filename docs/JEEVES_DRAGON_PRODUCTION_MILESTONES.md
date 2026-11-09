# Jeeves + Dragon: original game production milestones

This is a **runnable Director logic** workflow over the existing original-game
workspace. It uses existing Director-world typed compilation, campaign action
replay, saved campaign reopening, approved Dragon research handoffs, and Jeeves
source verification. It does not claim to build or playtest native Godot scenes,
train weights, prove quality, or replace the operator's authorship.

## Milestone 1: create a complete, reproducible Director campaign

First initialize an original game workspace with
`python -m skeleton dev game init original_game --vision "Restore the floating city"`.

```bash
python -m skeleton dev game jeeves director-draft \
  --project ./original_game --seed 19 \
  --regions harbor,market,observatory,catacombs \
  --quest-types main_story,investigation,crafting \
  --stages 3 --goal "Restore the floating city"
```

This creates an immutable **review candidate** in
`design/director_candidate_<digest>.json`, reporting its *full* receipt
(`candidate_sha256`). The compiler emits actual typed scenes, affordances,
cutscene cues, interconnected paths and multi-stage quests. The baseline uses
an explicitly local deterministic scaffold, **not the real LLM**. Story,
character, environmental, interaction and narrative qualities require editing.

When a reviewed Dragon handoff exists, pass `--dragon-digest <SHA256>` to
`director-draft` to bind the candidate to its current study. It does not
automatically grant originality or implement observed mechanics.

## Milestone 2: revise narrative, cast, sets, quests and cinematography

Create a JSON file `design/director_revisions.json`:

```json
{
  "schema": "skeleton.jeeves.director_revision.v1",
  "project": "original_game",
  "base_candidate_sha256": "<candidate_sha256>",
  "edits": [
    {
      "target": "bible",
      "field": "theme",
      "value": "Hope survives in a divided floating city"
    },
    {
      "target": "scene",
      "key": "scene_00",
      "field": "setting",
      "value": "An original lantern market over a submerged canal"
    },
    {
      "target": "quest",
      "key": "quest_00",
      "field": "consequences",
      "value": "Every restored district changes what the player can trust"
    },
    {
      "target": "stage",
      "quest": "quest_00",
      "key": "stage_00",
      "field": "lore",
      "value": "Recover the original map before the tide covers the observatory"
    }
  ]
}
```

Then:

```bash
python -m skeleton dev game jeeves director-revise \
  --project ./original_game --source design/director_candidate_<digest>.json \
  --revision design/director_revisions.json
```

The revision returns a **new candidate digest**; the base is unchanged.
Use the new candidate in subsequent operations. Supports typed updates of
bible/canon and endings, scene and cast/props/links, quest/stage text and
prerequisites, cutscene skip/trigger, and individual timeline cue fields.
Patch operations cannot execute scripts. The compiler rejects severed
connections, invalid stage solution affordances, and corrupt story identities.
Each revision retains source SHA-256 lineage and requires reinspection if any
ancestor changes. Revision files are direct children of `design/`.

## Milestone 3: execute branching logic, then explicitly approve

```bash
python -m skeleton dev game jeeves director-examine \
  --project ./original_game --source design/director_candidate_<digest>.json \
  --routes 3
python -m skeleton dev game jeeves director-promote \
  --project ./original_game --source design/director_candidate_<digest>.json \
  --routes 3 --approve <candidate_sha256>
python -m skeleton dev game jeeves direction-campaign \
  --project ./original_game --source design/director_campaign_source.json \
  --passes 3 --output campaign_story
python -m skeleton dev game jeeves direction-campaign-reopen \
  --project ./original_game --source design/director_campaign_source.json \
  --output campaign_story_0
```

Promotion checks the exact approved candidate and three complete logic replays
before creating the canonical campaign source in `design/`. It cannot
silently overwrite a previously reviewed source. Existing campaign operations
execute alternate quest methods, record action segments, write create-only
replay-backed saves and reconstruct state by replay. These are **Director logic
actions**, not real installed-game player inputs.

## Milestone 4: measure production and create real workorders

```bash
python -m skeleton dev game jeeves director-board \
  --project ./original_game --source design/director_campaign_source.json \
  --routes 3
```

The read-only workboard enumerates every authored scene and quest stage,
typed mechanics and dialogue/cinematics dependencies, action counts,
reproducible state receipts and divergences between simulated endings.
It also independently checks whether a Forge source manifest exists; it
**never** substitutes manifest presence for an interactive playthrough.
An optional `--dragon-digest` appends player-reviewed mechanic workorders.
Release, asset, sound, creative, native integration and real human gameplay
acceptance remain separate, explicitly unverified milestones.

## Milestone 5: prepare Dragon's replay-grounded learning queue

```bash
python -m skeleton dev game jeeves director-prepare-training \
  --project ./original_game --source design/director_campaign_source.json \
  --routes 3

# Review the returned candidate and then explicitly record:
python -m skeleton dev game jeeves director-prepare-training \
  --project ./original_game --source design/director_campaign_source.json \
  --routes 3 --approve <candidate_sha256>
```

The candidate binds exact execution receipts to concrete follow-up questions
for *real* gameplay observation. The approved candidate is create-only under
`.jeeves/dragon_replay_candidates/`. It contains **no invented player
preferences**, no scraped copyrighted assets, and does not change model weights.
Run dedicated checkpoint training and empirical evaluation separately once
real datasets, rights clearance, model access and optimizer infrastructure are
available.

## Specialized validation

```bash
python -m unittest tests.test_jeeves_director_production
python -m unittest tests.test_jeeves_dragon_game_handoff
```

No new global CI workflow or compulsory merge gate is introduced. Source
compilation, end-to-end game runtime, trained model inference and first-install
checks are still necessary to claim production readiness.
