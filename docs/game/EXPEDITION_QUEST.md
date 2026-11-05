# Offline expedition quest: authored choices, NPCs, crafting and endings

The canonical CLI is `python -m skeleton quest-expedition`. Run `demo` to
complete the original Lantern Harbor beacon patrol entirely offline. The
`simulate` command accepts a bounded JSON source and action list; `resume`
accepts a verified saved session plus further actions. `verify` reconstructs
every step, including the nested canonical tactical expedition, before
accepting a save. `export` and `import` round-trip a portable checksum bundle.

The versioned `skeleton.expedition_quest.v1` source includes a connected
directed location graph, authored NPC cyclic schedules, one-time dialogue
decisions, earned ingredients, one-time recipes, explicit victory/loss/draw
endings and an existing canonical expedition source. All IDs are validated.
NPC location is determined by the current action tick and authored route.
Talking to an NPC records `aid` or `decline`; only aid grants its gift.
Crafting requires both the workshop location and earned ingredients. Combat
requires the camp location and delegates its result to the actual expedition
engine; the quest layer cannot inject currency or forged combat outcomes.
Ending requirements enforce the replayed combat outcome, decisions and items.

```sh
python -m skeleton quest-expedition demo
python -m skeleton quest-expedition simulate --source-json '<JSON>' --actions-json '<JSON>'
python -m skeleton quest-expedition resume --session-json '<JSON>' --actions-json '<JSON>'
python -m skeleton quest-expedition verify --session-json '<JSON>'
python -m skeleton quest-expedition export --session-json '<JSON>'
python -m skeleton quest-expedition import --bundle-json '<JSON>'
python -m pytest skeleton/testing/test_expedition_quest.py -q
```

All actions are bounded to 96 and the serialized save/bundle to 2 MiB.
The replay includes source/state digests, event receipts and parent save
lineage. These checks detect accidental or adversarial modification of a
presented save, but are **not digital signatures** and cannot authenticate the
original author. External asset/license authorization remains the caller's
responsibility. No network, provider inference, audio or native 3D capability
is implied. Old expedition saves remain valid through their original CLI and
schema; this quest is an additive adapter, not a migration that silently
changes their meaning.
