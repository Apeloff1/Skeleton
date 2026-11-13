# Lantern Quay replay-verified route navigation

A saved game can now request a shortest legal route to an authored walkable
coordinate. The bounded navigator simulates each move and wait through the
canonical game engine, including dynamic NPC collision. It never teleports,
mutates the input checkpoint, invents inventory, or treats a digest as proof.

Export a checkpoint with `play` or `checkpoint`, then run:

```sh
python -m scripts.game.harbor_crafting route-plan --bundle save.json --goal 2,1 --expected-terminal-digest <verified-terminal-digest> > route.json
python -m scripts.game.harbor_crafting route-verify --route route.json
```

The route is a portable JSON replay artifact containing the verified original
source and save, ordered legal actions, the resumed save and a deterministic
integrity digest. Verification re-searches the route and replays every action.
This digest is an integrity check, **not** a signature or authorization token.

Search is limited to 64 additional ticks and 8192 visited states; exhausting
the search or encountering an unreachable/blocked target fails closed. Goal
coordinates are `x,y` in the authored tile grid. The player cannot navigate
after an earned ending. No GPU, external services or network access required.
