# dream path — arcane route profile

## Purpose
The `arcane_dream_path` profile models fictional-world route choice for the `arcane` engine. It uses a directed graph with explicit distance, danger, and energy costs. Routes are for game simulation, not physical navigation, aviation control, emergency response, or external transport systems.

## Navigation constraints
- Travel mode: `sail`.
- Domain: `arcane`.
- Directed nodes: start, crossroads, safehouse, lookout, goal.
- Maximum hops: 16.
- Maximum supported budget per independent dimension: 100000.
- Per-graph edge count: 8.
- Weight profile: distance 1, danger 2, energy 1 by default.
- All link costs are nonnegative integers; distance strictly increases on every link.

## Route graph
1. `start` → `crossroads`: distance 7, danger 7, energy 6.
2. `crossroads` → `goal`: distance 9, danger 8, energy 7.
3. `start` → `safehouse`: distance 9, danger 6, energy 8.
4. `safehouse` → `goal`: distance 10, danger 6, energy 6.
5. `crossroads` → `lookout`: distance 6, danger 10, energy 7.
6. `lookout` → `goal`: distance 7, danger 10, energy 6.
7. `safehouse` → `crossroads`: distance 7, danger 7, energy 6.
8. `start` → `goal`: distance 17, danger 6, energy 10.

## Planner integration
1. Bind the world instance and current capability permission set at the caller boundary.
2. Translate gameplay abilities into allowlisted blocked nodes and resource budgets.
3. Validate budgets and requested start and destination nodes before invoking the planner.
4. Call `plan` with explicit integer weights and resource constraints.
5. Reject any route that crosses blocked nodes or exceeds either budget.
6. Independently check a proposed route with `validate_route` before using it for movement.
7. Bind a chosen route to a deterministic world state revision before enacting movement.
8. Re-plan when world edges, hazards, inventory or mobility conditions change.

## Search algorithm
The planner enumerates bounded simple paths with a min-heap ordered by weighted cost and full path tuple. It does not collapse states solely by node because two paths can have different energy and danger consumption. This preserves feasibility for independently constrained resource budgets. The graph is small and intended as a domain fixture; a production-sized graph requires a stronger frontier bound and resource-dominance pruning.

## Authority boundary
The route evaluator does not authenticate travel permissions. Blocked-node lists are advisory inputs; the world engine must independently authorize node access, portal usage, faction rights, transport ownership, and regional access. A client-supplied route must never become a movement grant without a server-side check.

## Failure semantics
Unknown nodes, invalid budgets, duplicate blocked nodes, wrong parameter types, and zero-weight objectives reject explicitly. An unreachable destination returns `None`, not a fabricated fallback path. Routes violating a blocked-node constraint or edge sequence fail validation. Do not silently relax budgets when no route is found.

## Quality and device qualification
Run `python -m pytest -q skeleton/testing/route_planners_v1/test_arcane_dream_path.py`. Parse the request schema and the synthetic graph fixture; compile the source; then execute required exact-head repository tests and security scans. These synthetic graphs do not establish actual route optimality across a large world, native hardware performance, or consumer release readiness.

## Future design
Add terrain occupancy maps, temporal edges, dynamic hazards, stochastic forecasts, and cross-world transfer rules only behind versioned contracts. For multiplayer, route decisions must be fenced to an authoritative world tick, not simply recomputed from a client snapshot.
