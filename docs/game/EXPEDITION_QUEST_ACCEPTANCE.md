# Expedition quest end-to-end playable acceptance

`python -m skeleton game-vertical-accept demo --kind expedition_quest`
now exercises an original playable NPC/crafting/combat quest through the
existing acceptance contract, rather than treating chapter campaigns as the
only quest shape.

The run proves authored source normalization, real NPC decisions, earned
ingredients and crafting, camp-bound tactical combat, an earned alternate
ending, deterministic checkpoint split/replay, final save verification,
portable export/import and a replayable acceptance receipt.

The victory predicate is explicit: the quest must reach `finished` **and**
its embedded canonical combat expedition must reach `won`. A quest merely
declaring an ending without earned combat does not pass. Other acceptance
kinds (`forge`, `quest`) retain their original victory semantics and
portable record schemas.

This integrates the quest checkpoint, inventory conservation and decision
receipt workflows without duplicating their canonical runtime or granting
rewards. It is offline functional acceptance, not a release certificate,
device qualification, authorization or signed provenance.

Focused validation:

```sh
python -m pytest skeleton/testing/test_expedition_quest_acceptance.py -q
python -m pytest skeleton/testing/test_game_vertical_acceptance.py -q
python -m skeleton game-vertical-accept demo --kind expedition_quest
```
