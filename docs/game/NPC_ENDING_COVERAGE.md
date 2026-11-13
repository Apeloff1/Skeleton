# Offline NPC ending coverage and deterministic playable witnesses

The canonical NPC schedule runtime and route planner already support
individual endings. The coverage auditor runs the same canonical
planner for **every authored ending**, then replays each solved route
and restores its save before reporting a playable result.

```sh
python scripts/npc_schedule_cli.py \
  --schedule skeleton/testing/fixtures/lantern_harbor_npc_schedule.json \
  --audit-endings --max-search-nodes 1024 --max-search-depth 24
python -m pytest skeleton/testing/test_npc_ending_coverage.py
```

Reports contain source and original-canon digests, policy-independent
player identity, bounded search limits, per-ending priorities and fact
conditions, real ordered interaction commands, restored state digests,
and an overall checksum. The verifier recomputes every route and
replays its save. This is integrity evidence, **not** a signature or
permission to trust unverified content.

`solved` means an actual legal NPC interaction sequence reaches the
specified authored ending. `unreachable` means the finite explored
state space was exhausted. `inconclusive` means the search budget
was hit; it is never interpreted as a confirmed narrative defect.
`coverage_complete` is false whenever any ending is inconclusive,
and `all_endings_playable` is true only when every ending has a
canonical replay witness.

This tool does not mutate the schedule or save, grant facts, execute
scripts, access a provider or make network requests. It is intended
for original-world authoring acceptance before gameplay export.
