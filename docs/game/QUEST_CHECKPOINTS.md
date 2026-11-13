# Quest checkpoints and replay-authoritative alternate play

`python -m skeleton quest-checkpoints demo` runs an original NPC/crafting/combat
quest and branches at tick zero to a genuinely different earned ending. The
command returns a replay-verifiable fork record, not a fabricated state.

`timeline --session-json JSON` verifies every source-bound journal event and
returns ordered save ancestry, NPC choices, inventory, crafted items, location,
earned currency, combat health and ending state.

`checkpoint --session-json JSON --tick N` exports a historical portable
quest bundle. Tick zero is the original source; terminal tick is included.

`fork --session-json JSON --tick N --actions-json JSON` replays a new action
sequence from that exact checkpoint and compares actual gameplay consequences.
`verify-fork --record-json JSON` replays the original, historical checkpoint,
new branch and both portable bundles before returning the ending.

`compare --session-json JSON --other-session-json JSON` compares two fully
verified saves only when their canonical source digests match. All commands
support `--source-digest SHA256` to bind results to a separately trusted
source. The digest is **not** a signature, permission or authorship proof.

There is no network, clock, filesystem mutation, arbitrary Python execution,
unearned item grant or bypass around canonical combat and quest rules. Source
and journal limits are inherited from the quest engine (96 actions); complete
fork records have an additional 8 MiB serialization budget. Invalid source,
wrong tick, corrupt save, modified journal, forged rewards, oversized record,
or divergent branch receipt fails closed. A failed action does not publish a
partial checkpoint.

Focused validation:

```sh
python -m pytest skeleton/testing/test_expedition_quest_checkpoints.py -q
python -m skeleton quest-checkpoints demo
```

This is offline replay integrity, not a trusted signature or consumer/device
qualification. Mandatory exact-head CI and review remain separate release gates.
