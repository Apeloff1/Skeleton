# Deterministic accessible camera for the offline grid campaign

The original Lantern Harbor campaign now has a player-following camera
viewport and a screen-reader-oriented description. These are pure
presentation projections of the canonical source-bound simulation.

```sh
python -m scripts.game.offline_grid_campaign inspect \
  --view-width 5 --view-height 5 --accessible
python -m scripts.game.offline_grid_campaign play \
  --view-width 11 --view-height 9 --accessible
```

Viewport dimensions are bounded to 3..64 tiles and clamp to authored map
edges. The camera reports the player position, health, tile, ending and
visible NPCs, items and living enemies. Picked-up items and defeated
enemies are omitted. Accessibility output does not change movement,
collision, quests, inventory, combat, saves or deterministic replay.

The full `map` field remains in CLI JSON for backward compatibility;
the new `viewport` field is additive. This adapter does not claim native
3D, hardware rendering or on-device accessibility qualification.
