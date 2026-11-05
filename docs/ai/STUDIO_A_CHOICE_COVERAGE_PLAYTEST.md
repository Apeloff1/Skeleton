# Exact-source authored-choice playtest coverage

World-canon proves scene and ending reachability, but a reachable scene can
contain an individual choice whose required flags can never be earned. This
feature adds a distinct deterministic, bounded choice-coverage proof.

The prover explores canonical (scene, earned flags) states with sorted edges,
emits the shortest deterministic player trace for each executable choice,
replays every witness through the same player interpreter used by saved games,
and reports uncovered choice IDs rather than inventing coverage. Exhausted
state or artifact budgets fail closed; no device qualification is claimed.

Run `python -m skeleton world-playtest --store PRIVATE preview --world-id valley`
to inspect coverage. After reviewing the world source digest, run
`python -m skeleton world-playtest --store PRIVATE compile --world-id valley --expected-world-digest DIGEST`
to require full choice coverage and publish an exact-source playable HTML5
handoff plus a bounded JSON QA report. For deliberate partial coverage, the
operator must explicitly supply `--allow-uncovered`; the report retains the
uncovered IDs and `complete: false`.

Run `python -m skeleton world-playtest --store PRIVATE verify --world-id valley`
to recompute the full report and playable HTML under a source lock, compare
the receipt, and reject any tampering or source drift. The receipt is written
last and cannot authenticate a partially published pair of artifacts.
No network, script injection, implicit author approval or release claims.

The typed Jeeves `world.playtest_preview` tool is read-only and returns the
same source-bound proof. Publishing requires an operator CLI action.
