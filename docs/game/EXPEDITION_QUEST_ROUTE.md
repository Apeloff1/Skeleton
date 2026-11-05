# Bounded quest route solver

Use `python -m skeleton quest-expedition-route --demo --ending-id beacon_lit`
to search the original NPC, crafting and combat quest. For a saved game,
pass the full canonical session with `--session-json`. An explicit
`--max-states` (1..2048) and `--max-depth` (1..32) limit work.

The solver expands only authored legal actions, applies each through the
canonical quest state machine, and verifies any earned ending by portable
export/import. A found route includes the source and state digests,
exact action witness and portable checksum. Use `--verify-json` to
recompute the bounded search and replay the witness from the same source
or checkpoint. Different sources or forged rewards fail closed.

An exhausted search is reported as inconclusive, not as proof that an
authored ending cannot be reached. A completed checkpoint can only
certify its actual earned ending. The digest is not an author signature.

Focused validation:
`python -m pytest skeleton/testing/test_expedition_quest_route.py skeleton/testing/test_expedition_quest_interactive.py -q`.
Final-head CI is required before release.
