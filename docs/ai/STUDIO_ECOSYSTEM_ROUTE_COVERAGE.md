# Authored branching-quest route coverage

`explore_quest_routes(read_blueprint(project), authorized=True)` explores each
authored stage alternative through a deterministic topological order. It
replays all actions, verifies terminal session digests and records whether the
configured CPU/work frontier budget permitted full exploration.

A budget-limited search reports `coverage_complete: false` and
`truncated_by_resource_budget: true`; never pretend unvisited story branches
were explored. Authored narrative endings requiring external witness/device
evidence remain ineligible unless genuinely proven elsewhere. The results
do not certify native game features, assets, or consumer releases.
