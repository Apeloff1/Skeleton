# Atomic scene world authoring with real gameplay preview

`python -m skeleton scene-author` edits original scene travel source data
without changing the production game engine or executing authored code.

## Workflow

```sh
python -m skeleton scene-author demo
python -m skeleton scene-author edit --world-json '<canonical world JSON>' --edits-json '[{"kind":"set_step_limit","step_limit":24}]'
python -m skeleton scene-author verify --report-json '<complete author report JSON>'
python -m pytest skeleton/testing/test_scene_world_author.py
```

The editor supports `add_scene`, `remove_scene`, `set_start`,
`set_step_limit`, `set_ending`, `add_exit`, `remove_exit`,
`add_pickup` and `remove_pickup`. Each edit uses exact fields.
A batch is applied to a deep copy; the entire resulting topology is
validated through `normalize_world` only after the complete batch.
This permits atomic retarget-and-remove migrations while preventing
partially published, invalid worlds. A no-op is rejected.

The result contains the complete normalized before/after source, source
digests, original edit commands, command digest, deterministic route
playtest, state/depth budgets and checksum. Verification reapplies the
commands and recomputes the canonical playtest. It is an integrity
receipt, not an authenticity signature; callers must separately
authorize authors and source ownership.

The route preview executes `scene_route_solver.plan_victory`, which
in turn executes the canonical scene transitions. Its `found` status
contains actual replayable actions and final state digest. A truncated
search is `inconclusive`, never falsely classified as unwinnable.

Source input is limited to 128 KiB; edit batches to 64 commands and
128 KiB; report to 2 MiB. Search budgets are 1..4096 states and
1..512 depth. Invalid topology, dangling exits, missing required
items, invalid IDs, duplicate interactions, unsupported operations,
and modified receipts fail closed.

The resulting `after_source` can be passed directly to
`python -m skeleton scene-travel simulate`, or to the canonical
interactive scene travel player and portable save/export commands.
No filesystem writes, external calls or hidden state changes occur.
