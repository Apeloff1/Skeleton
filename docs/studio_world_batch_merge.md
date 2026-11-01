# Studio A — canonical world workflow merge ordering

The three-way merge accepts only source-replayed, catalog-leased append-only
world workflow plans. Shared appended steps have a **causal ordering**: their
position relative to other appended steps in either fork must be preserved.

## Merge algorithm

1. Replay the ancestor and both forks from canonical authored sources.
2. Reject ancestor edits, duplicate steps and conflicting semantic slots.
3. Form a bounded dependency DAG from adjacent appended steps in each fork.
4. Stable-topologically sort the DAG, preferring left-first encounter order
   for steps that are otherwise independent.
5. Reject cycles as explicit concurrent authoring conflicts. Never silently
   pick a fork's order or drop a step to make the merge succeed.
6. Compile and replay the resulting typed plan before execution or publication.

For example, left `A → B` and right `B → A` are incompatible. Left `A`
and right `B → A` merge to `B → A`, not `A → B`. Two forks appending the
same request once still deduplicate the shared step, preserving both orders.

The receipt includes `ordering_policy` and `ordered_append_digest` for
deterministic replay. It does **not** grant write authority, native runtime
qualification, or release certification. CLI publication and offline editing
remain separate operator-authorized actions; failures must occur before any
publication side effect.

## Regression fixtures

`tests/test_studio_world_batch_merge.py` covers reversed common-step
order, compatible right-before-shared order, exact replay digest, CLI
publication refusal on conflict and typed Jeeves tool refusal on conflict.
Run the focused tests on the exact branch head, then required exact-head CI.
No test or release claim is implied merely by committing these fixtures.
