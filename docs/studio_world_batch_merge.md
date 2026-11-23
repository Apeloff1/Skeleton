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

The merge CLI also accepts `--editor-directory <private-dir>` to publish the
existing CSP-hashed offline editor for the merged typed plan. Export from that
editor and use `--import-plan <export> --baseline-plan <merged-plan>` to
recompile and execute the edited workflow against current canonical source.
`--publish <private-dir>` executes and verifies the merged typed plan before
using the existing no-overwrite, fsynced, private receipt publication path.
Publication is an operator-requested write, never a merge-side effect.

The editor and publication paths are opt-in. All execution and source leases
are checked again on the final plan; the merge receipt itself is not a
permission token, a gameplay certificate, or a release assertion.

The typed Jeeves router also exposes
`studio_original_world_batch_merge` through a reviewed static descriptor.
Its arguments are `schema`, `expected_catalog_digest`, `baseline`,
`left`, and `right`. It requires out-of-band operator authorization and
returns a canonical merge plan without executing, writing, or asserting release
readiness. The existing CLI is the separate explicit execution/publication
boundary. This adapter is deliberately excluded from the recursive read-only
world batch tool allowlist to prevent nested workflow execution.

## Both-fork causal ordering

A shared appended step is also an ordering constraint. The merge builds a
bounded directed acyclic graph of adjacent steps from both forks and uses a
stable topological ordering (left-first when steps are independent). Opposite
orders such as left `A → B` and right `B → A` are rejected rather than
silently rewriting one fork. A compatible right fork `B → A` with left
`A` produces `B → A`. The canonical receipt records `ordering_policy`
and `ordered_append_digest`; neither grants write authority or release
qualification.

Regression fixtures cover conflicting order, compatible reorder, exact
receipt replay, CLI no-publication on conflict and typed Jeeves refusal.
