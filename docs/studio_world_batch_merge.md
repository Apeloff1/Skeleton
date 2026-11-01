# Jeeves source-leased append-only three-way workflow merge

The merge accepts one common typed world plan and two independently authored
forks. All three plans must replay against the current canonical source,
the same tool catalog and the same source project set. A fork can only append
steps; deleting, rewriting or reordering ancestor steps is rejected.

Concurrent append operations are deduplicated by complete canonical request
digest. Different requests addressing the same (tool, authored project)
semantic slot are treated as a conflict rather than choosing a winner.
Repeated appended steps and duplicate semantic slots fail closed. This
intentionally conservative policy is suitable for reviewed read-only tool
workflows, not arbitrary authoring or automatic conflict resolution.

Run the CLI with `--expected-catalog <digest> --merge-plans '<json>'`,
where JSON has exactly `baseline`, `left` and `right` plan objects.
`--html-sha256` adds the digest of an offline script-free review page.
The returned plan can be passed through the existing typed plan replay and
execution path after operator review. The merge itself writes no files,
executes no tools, and never certifies native gameplay, asset rights or release.

Source custody: every merge recompiles all three plans, then recompiles the
merged plan. A receipt is never accepted as proof by itself: use
`replay_world_batch_merge` with all three source plans to verify it.

Focused regression:
`python -m pytest -q tests/test_studio_world_batch_merge.py`
