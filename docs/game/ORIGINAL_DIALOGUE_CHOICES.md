# Offline dialogue sessions

Original authored dialogue is replayed from a bounded source and exact
choice history. Canonical FLGB DialogueNode, DialogueChoice, EventBus and
SaveableGameplayState contracts retain their existing authority.

The original fixture is
`skeleton/testing/fixtures/dialogue_original_lantern_harbor.json`.
It contains a beacon-repair pledge ending and an independent departure
ending, with observable flag, reputation and quest-trigger consequences.

```sh
python -m skeleton.app.dialogue_cli --source skeleton/testing/fixtures/dialogue_original_lantern_harbor.json
python -m skeleton.app.dialogue_cli --source skeleton/testing/fixtures/dialogue_original_lantern_harbor.json --choice listen --output /tmp/dialogue1.json
python -m skeleton.app.dialogue_cli --source skeleton/testing/fixtures/dialogue_original_lantern_harbor.json --save /tmp/dialogue1.json --choice promise-repair --output /tmp/dialogue2.json
python -m skeleton.app.dialogue_cli --source skeleton/testing/fixtures/dialogue_original_lantern_harbor.json --save /tmp/dialogue2.json --verify
```

The schema rejects unknown fields, duplicate graph IDs, missing targets,
invalid flags, unbounded reputation deltas and nonterminal dead ends.
At most 64 nodes, eight choices per node, 128 replay steps, 64 flags
and 64 quest IDs are admitted. Saved state, transcript, source and event
digests are all verified by recomputation before resuming.

Local input is a bounded no-follow regular file. New save output uses
exclusive create and owner-only permissions. No overwrite, network,
provider invocation, script evaluation or native game build occurs.

A quest trigger is an authored event, not a committed external quest
transaction. Integration with installed app CLI, Jeeves, NPC schedules,
world authoring, editor UI and native scene rendering remains open.
No consumer/device or release qualification is claimed.

Focused tests:
`python -m pytest -q skeleton/testing/test_dialogue_session.py`.
Architecture, provider and exact-head security gates remain mandatory.
L00-L13: FLGB ownership, typed source, explicit local authority,
bounded effects, deterministic receipts, restart-safe save verification,
adversarial tests, review and opt-in rollback without state migration.
