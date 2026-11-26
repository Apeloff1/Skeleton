# Source-bound offline story checkpoint merge

This Studio A vertical reconciles **two player-authored offline story forks** against an exact shared ancestor. It uses the canonical original catalog and Python quest replay, not browser assertions. The operation is available as a closed-schema Jeeves tool and a separate operator CLI. It does not certify a game, ending, native engine, asset right, or external evidence.

## Operator flow

Run the offline interactive HTML5 story and save three JSON checkpoints: a shared ancestor, the current branch, and the candidate branch. Place them as owner-private regular files in a directory you own with mode 0700. Then invoke:

```sh
python -m skeleton.ai.game_builder.studio_story_checkpoint_merge_cli \
  --project-id studio_arena_fighting_glacial_fjord \
  --quest-source-digest <64-hex-current-canonical-quest-digest> \
  --ancestor-file ancestor.json --current-file current.json \
  --candidate-file candidate.json --output-file merged.json \
  --trusted-local-operator
```

The CLI independently replays each receipt, verifies the source lease and common ancestor, detects contradictory choices or incompatible ordering, and replays the merged actions. It publishes a **new** 0600 checkpoint using exclusive creation and atomic hard-link publication, never overwriting any input or existing output. The resulting JSON is compatible with the existing offline story restore editor and canonical checkpoint review CLI. Output files are not created on validation failure. No network access is required.

Jeeves tool `studio_original_story_checkpoint_merge` accepts exact typed fields `schema`, `project_id`, `expected_quest_source_digest`, `ancestor_checkpoint`, `current_checkpoint`, and `candidate_checkpoint`. It returns an **unpersisted** merged checkpoint plus source-bound replay digests. Tool invocation requires out-of-band operator and authoring authorization.

## Safety and qualification

Input is limited to 65536 bytes per checkpoint, duplicate JSON keys and nonfinite values are rejected, all claimed release/evidence flags must be false, and all stage actions must be legal against current canonical source. The ancestor must be an exact prefix of both histories. Conflicting selections or incompatible branch ordering are refused, never resolved by silently preferring one fork. The output is round-trip replayed before publication. POSIX descriptor-anchored nofollow reads and owner-private directory checks prevent symlink and shared-directory custody failures. This feature remains source WIP until focused pytest and exact-head CI complete.

Focused tests: `python -m pytest -q tests/test_studio_story_checkpoint_merge.py`.
