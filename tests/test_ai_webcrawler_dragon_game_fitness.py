"""Auditable native game-generator candidate selection and static route scoring."""
from __future__ import annotations
from hashlib import sha256
import json
import pytest

from skeleton.ai.webcrawler.dragon_game_blueprints import design_campaign
from skeleton.ai.webcrawler.dragon_game_fitness import (
    evaluate_campaign,choose_campaign,selection_report,
)
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic


@pytest.mark.parametrize("style",[
    "racing","roguelike","arcade_score_attack","side_scrolling_platformer",
    "top_down_adventure","tactical_rpg",
])
@pytest.mark.parametrize("seed",[0,7,44,20261008])
def test_genetic_style_candidate_evaluator_never_invents_device_pass(style,seed):
    single=design_campaign(style=style,seed=seed,stages=4)
    baseline=evaluate_campaign(single)
    pick=choose_campaign(style=style,seed=seed,budget=8)
    assert pick==choose_campaign(style=style,seed=seed,budget=8)
    assert pick.budget==8 and len(pick.compared)==8
    assert pick.selected.static_quality>=baseline.static_quality
    assert len(pick.chosen.stages)==4
    assert pick.chosen.id==pick.selected.candidate_id
    assert all(report.shortest_route>=0 for report in pick.selected.stage_scores)
    assert all(report.reachable_pickups>=0 for report in pick.selected.stage_scores)
    assert all("inaccessible_pickups" not in report.issues
               for report in pick.selected.stage_scores)
    record=selection_report(pick)
    assert record["boundaries"]["emulator_executed"] is False
    assert record["boundaries"]["hardware_tested"] is False
    assert record["boundaries"]["xp_awarded"] is False
    assert record["selected"]["static_quality"]==pick.selected.static_quality
    assert len(record["compared"])==8


def test_optimiser_budget_and_seed_validated_fail_closed():
    for invalid in (0,-1,100,True):
        with pytest.raises(ValueError):
            choose_campaign(style="roguelike",seed=3,budget=invalid)
    for invalid in (-1,2**32,True):
        with pytest.raises(ValueError):
            choose_campaign(style="roguelike",seed=invalid,budget=8)
    with pytest.raises(ValueError):
        choose_campaign(style="not_a_real_game",seed=1)


def test_static_heuristics_expose_exploration_and_threat_without_fabricated_playtest():
    campaign=design_campaign(style="roguelike",seed=9831)
    verdict=evaluate_campaign(campaign)
    assert verdict.verdict=="static_layout_review_only"
    assert 0<=verdict.static_quality<=1
    assert 0<=verdict.diversity_score<=1
    assert len(verdict.stage_scores)==4
    for stage in verdict.stage_scores:
        assert stage.reachable_tiles<=stage.walkable_tiles
        assert stage.shortest_route>=1
        assert stage.weighted_risk_route>=stage.shortest_route
        assert stage.dead_ends>=0
        assert 0<=stage.blocked_ratio<=1
        assert 0<=stage.reachability_ratio<=1
        assert 0<=stage.quality<=1


def test_native_project_includes_recomputable_candidate_evaluation():
    p=render_native_project(
        title="Proof Bound Dragon",target_id="pc_linux",style="roguelike",
        candidate_id=sha256(b"proof-dragon").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )
    assert "dragon-generator-evaluation.json" in p.files
    report=json.loads(p.files["dragon-generator-evaluation.json"])
    stage=json.loads(p.files["dragon-campaign.json"])
    assert stage["id"]==report["selected"]["candidate_id"]
    assert report["candidate_budget"]==8
    assert len(report["compared"])==8
    assert report["boundaries"]["emulator_executed"] is False
    assert report["selected"]["static_quality"]>0
    assert p.digest
