"""Auditable AI game-practice route plans and quest-state correctness."""
from __future__ import annotations
from hashlib import sha256
import json
import pytest
from skeleton.ai.webcrawler.dragon_game_blueprints import design_campaign
from skeleton.ai.webcrawler.dragon_playtest_planner import (
    plan_campaign,plan_stage,agent_report,MAX_STATES,
)
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

STYLES=("arcade_score_attack","side_scrolling_platformer",
        "roguelike","top_down_adventure","tactical_rpg","racing",
        "first_person_shooter")

@pytest.mark.parametrize("style",STYLES)
@pytest.mark.parametrize("seed",[1,7,2026])
def test_game_planner_produces_bounded_deterministic_routes(style,seed):
    source=design_campaign(style=style,seed=seed,stages=4)
    plan=plan_campaign(source)
    assert plan==plan_campaign(source)
    assert plan.campaign_id==source.id
    assert plan.all_abstract_routes_found
    assert len(plan.stages)==4
    assert len(plan.trace_digest)==64
    for stage,trace in zip(source.stages,plan.stages):
        assert trace.achieved_exit
        assert trace.commands[0].kind.startswith("move_")
        assert trace.commands[-1].kind=="reach_exit"
        assert trace.commands[-1].x==stage.goal[0]
        assert trace.commands[-1].y==stage.goal[1]
        assert trace.visited_states>0
        assert trace.visited_states<MAX_STATES*15
        assert "No controller replay" in trace.limitations[2]
        if source.mode=="arena":
            assert trace.crystals_collected==stage.pickups
        if source.mode in ("dungeon","adventure","tactics") and stage.stage_id>=1:
            cmds=[a.kind for a in trace.commands]
            assert "collect_key" in cmds
            assert cmds.index("collect_key")<cmds.index("reach_exit")
        if stage.quest and stage.quest["guardians"]:
            assert trace.guardian_encounters>=1
            assert [x.kind for x in trace.commands].index("abstract_guardian_encounter") < len(trace.commands)-1

def test_source_archives_include_nonfabricated_agent_plan_and_evidence():
    p=render_native_project(
        title="Original Dragon Quest",target_id="pc_linux",
        style="roguelike",candidate_id=sha256(b"planner").hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)
    plan=json.loads(p.files["dragon-playtest-plan.json"])
    source=json.loads(p.files["dragon-campaign.json"])
    assert plan["campaign_id"]==source["id"]
    assert plan["proof_scope"]=="abstract state-space navigation, not runtime gameplay"
    assert plan["all_abstract_routes_found"]
    assert len(plan["stages"])==len(source["stages"])
    assert all(len(s["trace_digest"])==64 for s in plan["stages"])
    assert all("abstract" in s["limitations"][1].lower() for s in plan["stages"])


def test_route_planner_rejects_corrupt_or_undocumented_map():
    campaign=design_campaign(style="roguelike",seed=9)
    from dataclasses import replace
    stage=campaign.stages[0]
    altered=list(stage.terrain)
    altered[stage.start[1]]=altered[stage.start[1]].replace("S","X")
    bad=replace(stage,terrain=tuple(altered))
    with pytest.raises(ValueError,match="spawn and exit"):
        plan_stage(bad,"dungeon")
    with pytest.raises(ValueError):
        plan_stage(stage,"quantum_mechanics")
