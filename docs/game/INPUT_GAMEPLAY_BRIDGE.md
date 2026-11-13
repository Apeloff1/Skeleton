# Input-to-gameplay replay bridge

The existing keyboard/controller/touch input router produces semantic
commands but does not itself change game state. This bridge executes
those routed commands against the canonical offline grid game, so
movement and interaction now reach actual collision, inventory,
quest and save/replay logic.

```sh
python -m scripts.game.route_inputs \
  --profile skeleton/game/presentation/fixtures/original_campaign_controls.json \
  --events skeleton/testing/fixtures/input_bridge_moves.json \
  --game-source skeleton/game/gameplay/content/lantern_harbor.json
python -m pytest skeleton/testing/test_input_gameplay_bridge.py
```

`move` uses the real game engine, including wall and enemy collision.
`interact` contextually collects an item or speaks to an NPC only
when exactly one valid target is present. `confirm` requires a goal
tile and an unambiguous authored ending, or an explicitly selected
ending. `inventory` and `cancel` are read-only UI commands;
key releases do not generate extra gameplay steps.

The result includes source/profile digests, canonical input and game
snapshots, per-input receipts, gameplay transitions and checksum.
`verify_input_gameplay` replays both planes and rejects tampering.
No native device capture, external network, provider or arbitrary
script execution is claimed. It is a deterministic software input
adapter and does not qualify device-specific hardware.
