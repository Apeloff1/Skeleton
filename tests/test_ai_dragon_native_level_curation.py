"""Actually tailor original homebrew geometry to planned challenge with fair relief."""
from __future__ import annotations
from dataclasses import asdict
import json,pytest

from skeleton.ai.webcrawler.dragon_native_level_curation import (
    MAX_TRIALS,SCHEMA,curate_level,curation_report,
)
from skeleton.ai.webcrawler.dragon_native_puzzle import (
    transformed_level,solve_grid,emit_native_puzzle,
)
from skeleton.ai.webcrawler.dragon_native_multipath import (
    analyse_routes,verify_route_report,
)
from skeleton.ai.webcrawler.dragon_native_challenge_director import (
    make_challenge_plan,
)

@pytest.mark.parametrize("stage,seed,difficulty",[
    (0,1,2),(2,1977,5),(7,2026,9),
])
def test_balanced_game_preserves_legacy_original_geometry(stage,seed,difficulty):
    original=transformed_level(stage,seed,difficulty)
    candidate,report=curate_level(
        stage=stage,seed=seed,difficulty=difficulty,
        procedural=False,profile="balanced",
    )
    assert candidate==original
    assert report.schema==SCHEMA
    assert report.candidates_examined==1
    assert report.changed_from_baseline is False
    assert report.chosen_complexity==report.baseline_complexity

@pytest.mark.parametrize("profile",["gentle","challenging","spicy"])
def test_game_builders_actually_select_bounded_deterministic_solvable_original_worlds(profile):
    for stage in (0,1,3):
        first,evidence=curate_level(stage=stage,seed=1977,
                                     difficulty=6,procedural=False,
                                     profile=profile)
        second,again=curate_level(stage=stage,seed=1977,
                                  difficulty=6,procedural=False,
                                  profile=profile)
        assert first==second
        assert evidence==again
        assert evidence.source_seed>=0
        assert 1<=evidence.source_difficulty<=10
        assert evidence.candidates_examined==MAX_TRIALS
        assert 1<=evidence.distinct_solvable_candidates<=MAX_TRIALS
        assert 0<=evidence.chosen_complexity<=100
        moves,states=solve_grid(first)
        assert moves and 1<=len(moves)<=400 and states>=1
        native=transformed_level(stage,evidence.source_seed,
                                  evidence.source_difficulty,
                                  procedural=evidence.source_procedural)
        assert first==native

def test_spicy_original_worlds_have_deliberate_recovery_chapters_not_only_peaks():
    worlds=[]
    for stage in range(8):
        world,report=curate_level(
            stage=stage,seed=1977,difficulty=6,
            procedural=False,profile="spicy")
        worlds.append(report)
    assert worlds[1].tension_role=="deliberate_frustration_spike_with_escape"
    assert worlds[5].tension_role=="deliberate_frustration_spike_with_escape"
    assert worlds[0].tension_role=="exploration"
    assert worlds[3].tension_role=="deliberate_recovery"
    assert worlds[7].tension_role=="deliberate_recovery"
    for record in (worlds[3],worlds[7]):
        assert record.chosen_complexity<=record.baseline_complexity
    for stage in (0,1,2,4,5,6):
        assert worlds[stage].chosen_complexity>=worlds[stage].baseline_complexity

def test_original_creator_profile_is_reproducibly_embedded_into_game_source_and_graph():
    source=emit_native_puzzle(seed=1977,stages=4,difficulty=7,
                              challenge_profile="spicy")
    info=json.loads(source["dragon-puzzle-proof.json"])
    assert len(info["level_curation"])==4
    assert info["campaign_mode"]=="branching"
    assert info["challenge_director"]["profile"]=="spicy"
    for index,record in enumerate(info["level_curation"]):
        assert record["profile"]=="spicy"
        grid,expected=curate_level(
            stage=index,seed=1977,difficulty=7,procedural=False,
            profile="spicy",
        )
        assert record==curation_report(expected)
        solution,states=solve_grid(grid)
        assert solution==info["level_proofs"][index]["solution"]
        assert states==info["level_proofs"][index]["examined_states"]
        assert verify_route_report(grid,info["route_analysis"][index])["routes"]>=1

@pytest.mark.parametrize("invalid",[
    {"stage":8},{"stage":True},{"seed":-1},{"seed":2**32},
    {"difficulty":11},{"difficulty":0},{"procedural":"false"},
    {"profile":"unbounded punishment"},
])
def test_level_curation_rejects_unbounded_or_unconsented_generation_modes(invalid):
    kwargs=dict(stage=0,seed=1,difficulty=6,procedural=False,
                profile="balanced")
    kwargs.update(invalid)
    with pytest.raises(ValueError):
        curate_level(**kwargs)
