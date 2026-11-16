"""Real synthesis, gameplay and canonical replay regression source."""
from copy import deepcopy
import json

import pytest

from skeleton.app.recovered_evidence import EvidenceError, seal, parse
from skeleton.ai.game_builder.synthesized_quest_planner import plan_campaign
from skeleton.ai.game_builder.synthesized_quest_runtime import Campaign, qualify_campaign
from skeleton.app.gameforge_quest_qualification import qualify_forge


def mechanics():
    return {"registry":[
        {"id":"movement","provides":["travel"],"requires":[],"conflicts":[],"params":{}},
        {"id":"objectives","provides":["quest"],"requires":["travel"],"conflicts":[],"params":{}},
    ],"selected":["movement","objectives"],"overrides":{}}


def policy():
    return {"banned_terms":[],"max_reward_per_step":20,"max_total_reward":100,
            "allowed_reward_kinds":["xp","gold"]}


@pytest.fixture
def order():
    return {"schema":"skeleton.synthesized-quest.order.v1","campaign_id":"lantern",
            "title":"Lantern expedition","seed":17,"length":7,
            "world":{"start":"harbor","edges":{"harbor":["wood"],"wood":["harbor","tower"],
                                               "tower":["wood"]},
                     "npcs":{"keeper":"tower","guide":"harbor","scout":"wood"}},
            "mechanics":mechanics(),"policy":policy()}


def start(order):
    plan=plan_campaign(order,authorized=True)
    return plan,Campaign.start(order,plan,expected_plan_digest=plan["digest"],authorized=True)


def test_real_quest_execution_and_reconstruction(order):
    receipt=qualify_campaign(order,authorized=True)
    assert receipt["final"]["status"]=="completed"
    assert len(receipt["final"]["reward_ledger"])==order["length"]
    assert receipt["replayed_actions"]>=order["length"]*2
    assert receipt==qualify_campaign(order,authorized=True)
    assert not receipt["process_restart_tested"]


def test_no_teleport_or_unearned_completion(order):
    plan,run=start(order)
    with pytest.raises(EvidenceError):
        run.apply({"op":"move","destination":"tower"})
    with pytest.raises(EvidenceError):
        run.apply({"op":"complete","objective":plan["quest"]["steps"][0]["id"]})
    assert not run.actions


def test_conversation_then_one_reward(order):
    plan,run=start(order)
    first=plan["quest"]["steps"][0]
    for dest in plan["routes"][0]["waypoints"][1:]:
        run.apply({"op":"move","destination":dest})
    with pytest.raises(EvidenceError):
        run.apply({"op":"complete","objective":first["id"]})
    run.apply({"op":"talk","npc":first["npc"]})
    run.apply({"op":"complete","objective":first["id"]})
    with pytest.raises(EvidenceError):
        run.apply({"op":"complete","objective":first["id"]})
    assert len(run.snapshot()["reward_ledger"])==1


def test_resealed_forged_plan(order):
    plan,_=start(order)
    body={k:deepcopy(v) for k,v in plan.items() if k!="digest"}
    body["quest"]["steps"][0]["rewards"][0]["amount"]=999
    forged=seal(body)
    with pytest.raises(EvidenceError):
        Campaign.start(order,forged,expected_plan_digest=forged["digest"],authorized=True)


def test_resealed_forged_save(order):
    plan,run=start(order)
    body={k:deepcopy(v) for k,v in run.snapshot().items() if k!="digest"}
    body["reward_totals"]={"gold":1}
    forged=seal(body)
    with pytest.raises(EvidenceError):
        Campaign.restore(order,plan,forged,expected_plan_digest=plan["digest"],
                         expected_save_digest=forged["digest"],authorized=True)


def test_abandon_is_terminal(order):
    _,run=start(order)
    run.apply({"op":"abandon"})
    assert run.snapshot()["status"]=="failed"
    with pytest.raises(EvidenceError):
        run.apply({"op":"move","destination":"wood"})


def test_rejects_missing_pack_requirement_and_graph_location(order):
    order["mechanics"]["registry"][1]["requires"]=["missing"]
    with pytest.raises(ValueError):
        plan_campaign(order,authorized=True)
    order["mechanics"]=mechanics()
    order["world"]["edges"]["wood"].append("ghost")
    with pytest.raises(EvidenceError):
        plan_campaign(order,authorized=True)


def test_gameforge_planning_plus_actual_quest():
    order={"schema":"skeleton.gameforge-quest.order.v1",
           "vision":{"title":"Lantern","pitch":"Explore lantern harbor",
                     "genre":"adventure","era":"HOUSE_ERA","pillars":["explore"],"target_minutes":10},
           "config":{"budget_bytes":1000000,"regions":1,"target":"web"},
           "quest":{"seed":4,"length":3,"policy":policy(),"mechanics":mechanics(),"npcs":{}}}
    report=qualify_forge(order,authorized=True)
    assert len(report["manifest"]["steps"])==7
    assert report["quest_campaign"]["final"]["status"]=="completed"
    assert report["declarative_artifacts_only"]
    assert not report["native_engine_executed"]


def test_installed_route(order,tmp_path,capsys):
    from skeleton.__main__ import main
    file=tmp_path/"order.json"
    file.write_text(json.dumps(order),encoding="utf-8")
    assert main(["synthesized-quest","qualify","--order",str(file),"--trusted-local-operator"])==0
    assert json.loads(capsys.readouterr().out)["final"]["status"]=="completed"


@pytest.mark.parametrize("raw",[b'{"x":1,"x":2}',b'{"a":NaN}',b'[]'])
def test_strict_evidence_parser(raw):
    with pytest.raises(EvidenceError):
        parse(raw)
