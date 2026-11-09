"""Independent original game route exploration: diverse player choices, truthful limits."""
from __future__ import annotations
from dataclasses import asdict
import json
import pytest

from skeleton.ai.webcrawler.dragon_native_puzzle import (
    BASE_LEVELS,solve_grid,transformed_level,emit_native_puzzle,
)
from skeleton.ai.webcrawler.dragon_native_multipath import (
    SCHEMA,MAX_ALTERNATIVES,analyse_routes,route_report,
    verify_route_report,_walk,_search,
)
from skeleton.ai.webcrawler.dragon_native_puzzle_trace import simulate_grid


@pytest.mark.parametrize("seed,stage,difficulty",[
    (0,0,3),(17,1,7),(53,2,5),(1977,3,10),
])
def test_multiple_independent_solvers_produce_real_playable_game_routes(seed,stage,difficulty):
    board=transformed_level(stage,seed,difficulty)
    original,states=solve_grid(board)
    report=analyse_routes(board,max_routes=5,expansion_cap=3500)
    assert report.schema==SCHEMA
    assert report.exhaustive_alternatives is False
    assert report.routes[0].path==original
    assert report.routes[0].solver=="exact_bfs"
    assert report.routes[0].moves==len(original)
    assert 1<=len(report.routes)<=5
    assert len(set(x.path for x in report.routes))==len(report.routes)
    assert report.solvers_attempted[0]=="exact_bfs"
    assert 0<=report.difficulty_estimate<=100
    for route in report.routes:
        played=simulate_grid(board,route.path)
        assert played.solved and played.moves==route.moves
        assert played.pushes==route.pushes
        assert route.deadlock_pushes==0
        assert route.variation in ("baseline_optimal","distinct_push_strategy",
                                   "distinct_navigation")
        assert len(route.path_sha256)==64
    evidence=json.loads(json.dumps(route_report(report)))
    verified=verify_route_report(board,evidence)
    assert verified["routes"]==len(report.routes)
    assert verified["structural"]==report.structurally_distinct
    assert verified["navigation"]==report.navigationally_distinct


def test_push_first_and_astar_are_separate_actual_search_strategies():
    board=BASE_LEVELS[3]
    fastest,_=solve_grid(board)
    pushed,count_push=_search(board,mode="push_first",expansion_cap=18000)
    astar,count_astar=_search(board,mode="astar",expansion_cap=18000)
    assert fastest
    assert pushed and astar
    assert 0<count_push<=18000 and 0<count_astar<=18000
    for solver,moves in (("push_first",pushed),("astar",astar)):
        replay=simulate_grid(board,moves)
        assert replay.solved
        graded,_=_walk(board,moves,solver=solver,variation="candidate")
        assert graded.pushes==replay.pushes
        assert graded.moves==len(moves)
    assert len(astar)==len(fastest),"admissible matching-heuristic A* must return shortest walk"


def test_route_proofs_do_not_claim_unobserved_player_enjoyment_or_exhaustiveness():
    report=analyse_routes(BASE_LEVELS[0],max_routes=4,expansion_cap=2000)
    assert "NOT measured" in report.claim
    assert not report.exhaustive_alternatives
    assert report.routes
    assert all(record.variation!="identical_input_reordering"
               for record in report.routes)


def test_route_portfolio_fails_closed_on_corrupt_alternative_moves():
    original=route_report(analyse_routes(BASE_LEVELS[0],max_routes=3,
                                        expansion_cap=1500))
    content=json.loads(json.dumps(original))
    content["routes"][0]["path"]="a"*400
    with pytest.raises(ValueError):
        verify_route_report(BASE_LEVELS[0],content)
    content=json.loads(json.dumps(original))
    content["routes"][0]["pushes"]+=1
    with pytest.raises(ValueError):
        verify_route_report(BASE_LEVELS[0],content)
    content=json.loads(json.dumps(original))
    content["structurally_distinct"]+=1
    with pytest.raises(ValueError):
        verify_route_report(BASE_LEVELS[0],content)


@pytest.mark.parametrize("max_routes,search_budget",[
    (0,2000),(9,2000),(True,2000),(4,100),(4,120001),(4,False),
])
def test_multi_route_bfs_work_and_output_are_strictly_bounded(max_routes,search_budget):
    with pytest.raises(ValueError):
        analyse_routes(BASE_LEVELS[0],max_routes=max_routes,
                       expansion_cap=search_budget)


def test_source_generated_game_embeds_multiple_real_search_routes_with_proven_mechanics():
    source=emit_native_puzzle(seed=1977,stages=3,difficulty=7)
    proof=json.loads(source["dragon-puzzle-proof.json"])
    assert proof["route_analysis"]
    assert proof["stages"]==len(proof["route_analysis"])
    for index,report in enumerate(proof["route_analysis"]):
        board=transformed_level(index,1977,7)
        assert report["stage"]==index
        result=verify_route_report(board,report)
        assert result["routes"]>=1
        assert report["routes"][0]["moves"]==proof["level_proofs"][index]["steps"]
        assert report["routes"][0]["path"]==proof["level_proofs"][index]["solution"]
