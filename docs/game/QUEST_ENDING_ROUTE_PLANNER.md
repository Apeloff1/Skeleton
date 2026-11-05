# Offline quest ending choice planner

Use the installed `skeleton quest solve` command to find a shortest sequence
of legitimate authored quest choices leading to an ending:

```sh
python -m skeleton quest solve \
  --plan docs/game/fixtures/lantern_harbor_quests.json \
  --goal-ending safe_harbor
```

Every transition uses the canonical `QuestEngine`; completion rewards are
earned only by satisfying dependencies and matching source-bound event
contracts. A solved witness contains exact events and a portable save that
`QuestEngine.restore` can verify. The solver does not execute outside actions,
mint currency, mutate existing saves or call an AI provider.

`--max-search-nodes` (1..4096, default 1024) and
`--max-search-depth` (1..64, default 24) bound computation. A budget cutoff
returns `inconclusive` rather than falsely claiming an ending unreachable.
Terminal endings prevent further quest events. No device or release
qualification is implied by the route witness.
