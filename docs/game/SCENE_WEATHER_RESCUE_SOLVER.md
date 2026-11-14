# Bounded Weather Rescue Route Solver

`python -m skeleton scene-weather-rescue-solve demo` searches for a
replayable route that shelters the original canal medic before the deadline
without exceeding storm exposure. Search actions are actual canonical
weather-gated travel, item collection, wait, rescue and shelter commands.
A route is accepted only if the NPC reaches safety and the full source-bound
save, earned reward and event journal replay identically.

`solve --source-json ... [--resume-json ...] [--max-nodes 256]
[--max-depth 16]` accepts a source or verified checkpoint.
`verify --receipt-json ...` reruns the bounded search and checks the
entire witness, including each canonical weather action and save lineage.

The planner is deterministic and bounded. When the search budget is
exhausted, it reports `unproven_within_budget` rather than falsely
claiming impossibility. It is not a device-performance or release certificate.
