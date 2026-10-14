"""Original game tension targets, escape valves and voluntary player observations."""
from __future__ import annotations
from dataclasses import replace
import json,pytest
from skeleton.ai.webcrawler.dragon_native_puzzle import emit_native_puzzle
from skeleton.ai.webcrawler.dragon_native_multipath import (
    analyse_routes,route_report,
)
from skeleton.ai.webcrawler.dragon_native_challenge_director import (
    PROFILES,SCHEMA,PlayerAggregate,make_challenge_plan,challenge_report,
    review_player_tension,
)
from skeleton.ai.webcrawler.dragon_native_puzzle import BASE_LEVELS


def sample_routes(stages=4):
    reports=[]
    for stage in range(stages):
        from skeleton.ai.webcrawler.dragon_native_puzzle import transformed_level
        board=transformed_level(stage,1977,7)
        reports.append(route_report(
            analyse_routes(board,max_routes=4,expansion_cap=1200)))
    return tuple(reports)


@pytest.mark.parametrize("profile",["gentle","balanced","challenging","spicy"])
def test_challenge_director_uses_actual_solver_data_and_recovery_chapters(profile):
    analysis=make_challenge_plan(sample_routes(4),profile=profile,branching=True)
    assert analysis.schema==SCHEMA
    assert analysis.profile==profile
    assert len(analysis.stages)==4
    assert not analysis.has_player_observations
    assert "no player-rated" in analysis.player_feedback_scope
    assert len(analysis.plan_digest)==64
    assert all(stage.shortest_moves>=stage.shortest_pushes>=1
               for stage in analysis.stages)
    assert all(0<=stage.measured_complexity<=100 for stage in analysis.stages)
    assert all(stage.rescue_tools[:3]==(
        "manual_undo","manual_live_hint","replay_shortest_path",
    ) for stage in analysis.stages)
    assert json.loads(json.dumps(challenge_report(analysis)))["profile"]==profile


def test_spicy_intensity_has_deliberate_but_recoverable_tension_spikes():
    data=make_challenge_plan(sample_routes(5),profile="spicy",branching=True)
    spikes=[s for s in data.stages if s.spike]
    assert spikes
    assert all("optional_easier_campaign_branch" in s.rescue_tools for s in spikes)
    assert all(not s.recovery for s in spikes)
    assert any(s.recovery for s in data.stages)


def test_optional_real_feedback_is_distinct_from_algorithmic_fun_predictions():
    routes=sample_routes(2)
    observations=(
        PlayerAggregate(10,2,250,33,20,5,difficult_rating=5,enjoyment_rating=2),
        PlayerAggregate(10,8,310,4,1,1,difficult_rating=2,enjoyment_rating=5),
    )
    plan=make_challenge_plan(routes,player_samples=observations)
    assert plan.has_player_observations
    assert plan.observation_evidence_digest
    assert "stage_1:observed_high_abandonment" in plan.overall_fairness_warnings
    assert plan.stages[0].human_enjoyment_evidence
    advice=review_player_tension(plan.stages[0],observations[0])
    assert advice["completion_rate_percent"]==20
    assert "offer_alternative_chapter_route_or_opt_in_hint" in advice["suggestions"]
    assert "collect_consenting_qualitative_player_feedback" in advice["suggestions"]


@pytest.mark.parametrize("sample",[
    PlayerAggregate(0,0,0,0,0,0),
    PlayerAggregate(3,4,0,0,0,0),
    PlayerAggregate(3,1,0,0,0,3),
    PlayerAggregate(3,1,-1,0,0,0),
    PlayerAggregate(3,1,0,0,0,0,enjoyment_rating=6),
    PlayerAggregate(3,1,0,0,0,0,difficult_rating=True),
])
def test_observations_do_not_admit_forged_or_unbounded_player_data(sample):
    with pytest.raises(ValueError):
        sample.validate()


def test_native_puzzle_source_documents_distinct_tension_and_rest_recovery_signals():
    files=emit_native_puzzle(seed=23,stages=4,difficulty=7,
                             challenge_profile="spicy")
    proof=json.loads(files["dragon-puzzle-proof.json"])
    plan=proof["challenge_director"]
    assert plan["profile"]=="spicy"
    assert not plan["has_player_observations"]
    assert len(plan["stages"])==4
    assert all(stage["human_enjoyment_evidence"] is False
               for stage in plan["stages"])


@pytest.mark.parametrize("profile",["sabotage","frustration_without_recovery",""])
def test_game_director_rejects_unconsented_deceptive_frustration_targets(profile):
    with pytest.raises(ValueError):
        make_challenge_plan(sample_routes(2),profile=profile)
