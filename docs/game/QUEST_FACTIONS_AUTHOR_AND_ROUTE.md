# Transactional faction authoring and bounded ending search

`python -m skeleton quest-factions-author demo` edits the original Lantern
Harbor faction policy, replays a playable preview, and emits a source-digest
fenced receipt. The canonical quest source, authored NPC routes, crafting,
combat and original earned rewards remain authoritative.

## Authoring commands

`quest-factions-author edit --source-json JSON --operations-json JSON
--expected-digest DIGEST [--preview-actions-json JSON]` supports
`add_faction`, `remove_faction`, `set_members`, `set_aid_delta`,
`set_decline_delta`, `set_ending_requirements`, and
`set_quest_source`. A batch is atomic: invalid references, unsupported
fields, no-op edits, optimistic conflicts, or unplayable previews abort
without mutating the original source. `verify --receipt-json JSON`
reconstructs the entire edit and optional gameplay preview.
`compatibility --receipt-json JSON --session-json JSON` requires a verified
save and returns `restart_from_new_source` when source identity changed.
No implicit save migration is performed.

## Ending route commands

`quest-factions-route --source-json JSON --ending-id ID` searches legal
quest actions with a finite state/depth budget, checking faction standings
and original quest requirements in the real runtime. `--session-json JSON`
continues from a verified checkpoint. `--demo` uses the original source.
`--max-states` and `--max-depth` cap search. If the budget is exhausted,
status is `inconclusive`, never an invented impossible ending. A found
receipt contains an executable action witness, final state digest and
portable save checksum. `--verify-json JSON` recomputes the bounded search
and replays the complete witness; tampering fails closed.

Focused contracts:
`python -m pytest skeleton/testing/test_quest_factions_author.py
skeleton/testing/test_quest_factions_route.py -q`.

These are local, original offline gameplay tools. Exact-head CI, consumer
installation and device qualification remain separate release gates.
