# Interactive Chapter Campaign

`python -m skeleton quest-campaign-play --demo` launches the authored
multi-chapter campaign. Player verbs are `travel PLACE`, `talk NPC aid`,
`craft RECIPE`, `fight`, `buy ITEM`, `use ITEM`, `finish ENDING`,
`wait` and `advance`. Structured quest JSON actions are also supported.
Only the canonical quest runtime determines legal actions, rewards, chapter
unlocks and endings. `advance` is legal only after an earned chapter ending.

Each turn emits a bounded JSON prompt, legal actions and a digest. Accepted
moves emit canonical action receipts. The session emits replayable checkpoints
at `--checkpoint-every` intervals and on EOF, invalid-input exhaustion,
no legal move, turn-budget exhaustion or terminal completion. Resume with
`--resume-json` and optionally pin `--source-digest` to a trusted authored
source. A terminal bundle is verified by full replay and export/import. No
automatic grants, hidden teleport, silent source migration or recovery from
an incompatible save is allowed.
