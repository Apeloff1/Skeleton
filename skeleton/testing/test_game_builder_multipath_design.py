"""Behavioral regressions for the independently replayable multi-route solvers."""
from __future__ import annotations

from dataclasses import replace
import pytest

from skeleton.ai.game_builder.multipath_design import (
    MultipathError, RouteProblem, evaluate_route, solve_route,
)

OPEN_LEVEL = (
    "#########",
    "#S..C..G#",
    "#.......#",
    "#.#.#.#.#",
    "#...H...#",
    "#.#.#.#.#",
    "#.......#",
    "#.......#",
    "#########",
)

HAZARD_LEVEL = (
    "#########",
    "#S.H.C.G#",
    "#.......#",
    "#.......#",
    "#.......#",
    "#.......#",
    "#.......#",
    "#.......#",
    "#########",
)


def test_objective_state_bfs_is_deterministic_and_replayable():
    problem = RouteProblem.from_rows(OPEN_LEVEL)
    first = solve_route(problem)
    assert first == solve_route(problem)
    assert first.problem_digest == problem.digest
    assert first.collectible_order == ((4, 1),)
    assert first.positions[0] == problem.start
    assert first.positions[-1] == problem.goal
    assert first.steps == 6
    assert first.cost == first.steps
    assert first.hazard_visits == 0
    assert first.digest == solve_route(problem).digest
    assert evaluate_route(problem, first.actions).positions == first.positions


def test_weighted_solver_uses_policy_to_choose_safe_detour():
    problem = RouteProblem.from_rows(HAZARD_LEVEL)
    risky = solve_route(problem, algorithm="dijkstra", allow_hazards=True,
                        hazard_cost=0)
    safe = solve_route(problem, algorithm="dijkstra", allow_hazards=True,
                       hazard_cost=20)
    assert risky.steps == 6
    assert risky.hazard_visits == 1
    assert safe.hazard_visits == 0
    assert safe.steps > risky.steps
    assert safe.cost < risky.cost + 20
    assert safe == solve_route(problem, algorithm="dijkstra",
                               allow_hazards=True, hazard_cost=20)
    assert solve_route(problem).hazard_visits == 0


def test_invalid_route_replay_never_claims_completion():
    problem = RouteProblem.from_rows(OPEN_LEVEL)
    for actions in ((), ("right",), ("left",), ("invent",)):
        with pytest.raises(MultipathError):
            evaluate_route(problem, actions)


@pytest.mark.parametrize("mutation", [
    lambda rows: rows[:-1],
    lambda rows: (".........",) + rows[1:],
    lambda rows: rows[:2] + ("#S.....G#",) + rows[3:],
    lambda rows: rows[:1] + ("#S.....G#",) + rows[2:],
    lambda rows: rows[:1] + ("#S..C..?#",) + rows[2:],
])
def test_grid_admission_rejects_broken_boundaries_and_objectives(mutation):
    with pytest.raises(MultipathError):
        RouteProblem.from_rows(mutation(OPEN_LEVEL))


def test_explicit_search_budget_fails_closed():
    problem = RouteProblem.from_rows(OPEN_LEVEL)
    with pytest.raises(MultipathError, match="expansion budget"):
        solve_route(problem, max_expansions=1)
    with pytest.raises(MultipathError, match="BFS admits only"):
        solve_route(problem, algorithm="bfs", allow_hazards=True)
    with pytest.raises(MultipathError, match="invalid state expansion"):
        solve_route(problem, max_expansions=True)


def test_edge_penalty_influences_route_and_cannot_reference_walls():
    problem = RouteProblem.from_rows(OPEN_LEVEL)
    costly = {((1, 1), (2, 1)): 100}
    result = solve_route(problem, algorithm="dijkstra", edge_penalties=costly)
    assert result.actions[0] == "down"
    assert result.cost < 100
    with pytest.raises(MultipathError, match="non-walkable transition"):
        solve_route(problem, algorithm="dijkstra",
                    edge_penalties={((0, 0), (0, 1)): 3})
    with pytest.raises(MultipathError, match="invalid edge penalty"):
        solve_route(problem, algorithm="dijkstra",
                    edge_penalties={((1, 1), (2, 1)): -1})

def test_directed_route_edge_lineage_is_ordered_and_exact():
    route = solve_route(RouteProblem.from_rows(OPEN_LEVEL))
    edges = route_edges(route)
    assert len(edges) == route.steps
    assert edges[0][0] == (1, 1)
    assert edges[-1][1] == (7, 1)
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in edges)


def test_revisits_count_real_tiles_not_length_surrogates():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    direct = solve_route(p)
    loop = ("down", "up") + direct.actions
    replay = evaluate_route(p, loop)
    assert route_revisits(direct) == 0
    assert route_revisits(replay) == 1
    assert replay.steps == direct.steps + 2


def test_turn_metric_distinguishes_direct_route_from_detour():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    direct = solve_route(p)
    assert route_turns(direct) == 0
    detour = evaluate_route(p, ("down", "right", "up") + ("right",) * 5)
    assert route_turns(detour) == 3
    assert detour.steps == 8


def test_corridor_overlap_is_symmetric_and_identity_exact():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    a = solve_route(p)
    b = solve_route(p, algorithm="dijkstra",
                    edge_penalties={((1, 1), (2, 1)): 100})
    assert route_overlap_ppm(a, a) == 1_000_000
    assert 0 <= route_overlap_ppm(a, b) < 1_000_000
    assert route_overlap_ppm(a, b) == route_overlap_ppm(b, a)
    with pytest.raises(MultipathError, match="same verified world"):
        route_overlap_ppm(a, solve_route(RouteProblem.from_rows(HAZARD_LEVEL)))


def test_novelty_is_exact_complement_of_overlap():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    a = solve_route(p)
    b = solve_route(p, algorithm="dijkstra",
                    edge_penalties={((1, 1), (2, 1)): 30})
    assert route_diversity_ppm(a, a) == 0
    assert route_diversity_ppm(a, b) == 1_000_000 - route_overlap_ppm(a, b)


def test_route_portfolio_finds_real_distinct_routes_and_caps_work():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    portfolio = route_portfolio(p, max_routes=4)
    assert 2 <= len(portfolio) <= 4
    assert portfolio == route_portfolio(p, max_routes=4)
    assert len({route.actions for route in portfolio}) == len(portfolio)
    assert all(evaluate_route(p, r.actions).positions == r.positions
               for r in portfolio)
    assert any(route_diversity_ppm(portfolio[0], route) > 0
               for route in portfolio[1:])
    with pytest.raises(MultipathError):
        route_portfolio(p, max_routes=0)


def test_walkable_cell_catalog_distinguishes_hazard_cost():
    p = RouteProblem.from_rows(HAZARD_LEVEL)
    safe = walkable_cells(p)
    all_cells = walkable_cells(p, include_hazards=True)
    assert (3, 1) not in safe and (3, 1) in all_cells
    assert len(all_cells) == len(safe) + 1
    assert all(p.tile(point) != "#" for point in all_cells)


def test_flood_fill_respects_hazards_and_real_connectivity():
    p = RouteProblem.from_rows(HAZARD_LEVEL)
    safe = flood_fill(p, p.start)
    full = flood_fill(p, p.start, allow_hazards=True)
    assert p.goal in safe
    assert (3, 1) not in safe and (3, 1) in full
    with pytest.raises(MultipathError):
        flood_fill(p, (0, 0))


def test_regions_find_unreachable_pockets_and_cover_grid():
    rows = list(OPEN_LEVEL)
    rows[4] = "#########"
    rows[1] = "#S.....G#"
    rows[5] = "#..C....#"
    p = RouteProblem.from_rows(rows)
    pieces = connected_regions(p)
    assert len(pieces) == 2
    assert p.start in pieces[0] and p.collectibles[0] in pieces[1]
    assert set().union(*pieces) == set(walkable_cells(p))
    with pytest.raises(MultipathError):
        solve_route(p)


def test_objective_reachability_identifies_missing_collectibles():
    rows = list(OPEN_LEVEL)
    rows[4] = "#########"
    rows[1] = "#S.....G#"
    rows[5] = "#..C....#"
    report = objective_reachability(RouteProblem.from_rows(rows))
    assert report["exit_reachable"] is True
    assert report["all_collectibles_reachable"] is False
    assert report["missing_collectibles"] == ((3, 5),)
    good = objective_reachability(RouteProblem.from_rows(OPEN_LEVEL))
    assert good["all_collectibles_reachable"] and good["exit_reachable"]


def test_branch_histogram_accounts_for_each_safe_tile():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    h = degree_histogram(p)
    assert set(h) == {0, 1, 2, 3, 4}
    assert sum(h.values()) == len(walkable_cells(p))
    assert h[4] > 0


def test_dead_end_report_distinguishes_objective_endpoints():
    rows = (
        "#########", "#S.C...G#", "#########",
        "#########", "#########", "#########",
        "#########", "#########", "#########",
    )
    p = RouteProblem.from_rows(rows)
    assert dead_end_cells(p) == ()
    assert dead_end_cells(p, include_objectives=True) == ((1, 1), (7, 1))
    assert degree_histogram(p)[1] == 2


def test_tarjan_identifies_real_single_corridor_chokepoints():
    p = RouteProblem.from_rows((
        "#########", "#S.C...G#", "#########", "#########",
        "#########", "#########", "#########", "#########", "#########",
    ))
    assert articulation_cells(p) == tuple((x, 1) for x in range(2, 7))
    assert (1, 1) not in articulation_cells(p)
    assert (7, 1) not in articulation_cells(p)


def test_bridges_enumerate_each_critical_corridor_edge_once():
    line = RouteProblem.from_rows((
        "#########", "#S.C...G#", "#########", "#########",
        "#########", "#########", "#########", "#########", "#########",
    ))
    bridges = bridge_corridors(line)
    assert len(bridges) == 6
    assert set(bridges) == {
        ((x, 1), (x + 1, 1)) for x in range(1, 7)
    }
    assert len(bridge_corridors(RouteProblem.from_rows(OPEN_LEVEL))) < 6


def test_cycle_rank_distinguishes_tree_world_from_open_alternatives():
    line = RouteProblem.from_rows((
        "#########", "#S.C...G#", "#########", "#########",
        "#########", "#########", "#########", "#########", "#########",
    ))
    assert cycle_rank(line) == 0
    assert cycle_rank(RouteProblem.from_rows(OPEN_LEVEL)) > 0


def test_exact_tile_distances_match_single_corridor_ground_truth():
    p = RouteProblem.from_rows((
        "#########", "#S.C...G#", "#########", "#########",
        "#########", "#########", "#########", "#########", "#########",
    ))
    distances = tile_distances(p, p.start)
    assert distances[p.goal] == 6
    assert distances[p.collectibles[0]] == 2
    assert len(distances) == 7


def test_branch_choices_count_real_player_decisions():
    p = RouteProblem.from_rows(OPEN_LEVEL)
    solved = solve_route(p)
    choices = route_branch_choices(p, solved)
    assert len(choices) == solved.steps
    assert choices[0] == 2
    assert max(choices) >= 3
    with pytest.raises(MultipathError):
        route_branch_choices(RouteProblem.from_rows(HAZARD_LEVEL), solved)


def test_hazard_awareness_map_excludes_hazard_tile_and_respects_radius():
    p = RouteProblem.from_rows(HAZARD_LEVEL)
    sensed = hazard_proximity(p, radius=1)
    assert (3, 1) not in sensed
    assert sensed[(2, 1)] == 1
    assert sensed[(3, 2)] == 1
    assert sensed[(1, 1)] == 0
    with pytest.raises(MultipathError):
        hazard_proximity(p, radius=0)


def test_hazard_exposure_counts_near_misses_without_collision():
    p = RouteProblem.from_rows(HAZARD_LEVEL)
    route = solve_route(p)
    assert route.hazard_visits == 0
    assert route_exposure_score(p, route, radius=2) > 0
    assert route_exposure_score(p, route, radius=1) <= route_exposure_score(p, route, radius=2)

