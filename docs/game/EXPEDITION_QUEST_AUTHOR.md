# Offline quest authoring and deterministic previews

`python -m skeleton quest-author` is the builder-side typed editing surface
for the existing `skeleton.expedition_quest.v1` runtime. The editor changes
authored source, not an in-progress player's save. Every edit is fenced by
the canonical source digest. Multiple edits are atomic: the final source
must pass the full canonical quest normalizer, including cross-references,
reachable rooms, NPC schedules, crafting dependencies and ending conditions.

Supported typed operations: add/remove location, NPC, recipe or ending;
set authored location exits, NPC gift/route, recipe inputs/output, ending
choices/items/outcome, root start/camp/workshop location, and replace the
canonical expedition source. No arbitrary path operations or code execution.

```sh
python -m skeleton quest-author demo
python -m skeleton quest-author edit --source-json '<JSON>' --operations-json '<JSON>' --expected-digest '<SHA256>' --preview-actions-json '<JSON>'
python -m skeleton quest-author verify --receipt-json '<JSON>'
python -m skeleton quest-author compatibility --receipt-json '<JSON>' --session-json '<JSON>'
python -m pytest skeleton/testing/test_expedition_quest_author.py -q
```

A receipt records the exact normalized baseline, ordered operations, before
and after source digests, and optional playable preview reconstructed by the
canonical quest engine. Receipt verification replays all edits and preview
actions. A source-changing edit is incompatible with an old save unless the
digests still match; the compatibility command returns a restart decision,
never silently moves player progress to a different authored world. The
maximum transaction has 48 operations and bounded JSON sizes. Digests
protect integrity, **not author identity or asset licensing**. All operations
run offline with no provider, scripts or native rendering assumptions.
