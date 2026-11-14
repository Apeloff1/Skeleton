# Cinder Ridge earned rescue championship acceptance

Run a complete, original two-entrant offline championship without creating
synthetic player scores or bypassing gameplay:

```bash
python -m skeleton.game.gameplay.ridge_rescue.league_acceptance
python -m skeleton.game.gameplay.ridge_rescue.league_acceptance --output /tmp/ridge-championship.json
python -m skeleton.game.gameplay.ridge_rescue.league_cli verify-export --bundle /tmp/ridge-championship.json
```

The runner plays the actual first-evacuation world twice: once crafting and
activating the signal beacon for the protected ending, once evacuating for the
salvage ending. Both game histories are independently replayed by the league,
then ranked by replay-derived outcomes. The final portable league export
replays the world, actions, earned endings, score and ranking. Recomputed
digests do not make forged scores acceptable because all values are derived
from the game engine. User handles are labels, not authenticated identities.

The acceptance script and tests have to be **executed** before claiming
successful qualification. GitHub exact-head CI, security and device release
gates remain separate.
