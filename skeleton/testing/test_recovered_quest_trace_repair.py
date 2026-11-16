"""Real B039 repair, B038 provenance and canonical quest replay integration."""
from copy import deepcopy

import pytest

from skeleton.app.recovered_evidence import EvidenceError,digest
from skeleton.ai.game_builder.synthesized_quest_planner import plan_campaign
from skeleton.ai.game_builder.synthesized_quest_runtime import solution
from skeleton.ai.game_builder.quest_trace_repair import repair_trace
from skeleton.gameforge.batch_b038.provenance import ProvenanceLedger


def order():
    campaign={"schema":"skeleton.synthesized-quest.order.v1","campaign_id":"recovery",
              "title":"Lantern","seed":8,"length":3,
              "world":{"start":"dock","edges":{"dock":["hill"],"hill":["dock"]},"npcs":{}},
              "policy":{"banned_terms":[],"max_reward_per_step":4,"max_total_reward":12,
                        "allowed_reward_kinds":["xp"]},
              "mechanics":{"registry":[
                  {"id":"travel","provides":["travel"],"requires":[],"conflicts":[],"params":{}},
                  {"id":"quest","provides":["quest"],"requires":["travel"],"conflicts":[],"params":{}},
              ],"selected":["travel","quest"],"overrides":{}}}
    plan=plan_campaign(campaign,authorized=True)
    return {"schema":"skeleton.quest-trace-repair.order.v1","campaign":campaign,
            "plan":plan,"expected_plan_digest":plan["digest"],"trace":[],
            "max_mutations":12,"max_seconds":30,"chunk_actions":4}


def test_actual_empty_trace_repaired_and_provenance_verified():
    value=order()
    before=deepcopy(value)
    report=repair_trace(value,authorized=True)
    assert report["eligible_for_human_review"]
    assert report["candidate_status"]=="completed"
    assert report["mutation_count"]>=1
    assert report["candidate_trace_digest"]==digest({"actions":report["candidate_trace"]})
    assert ProvenanceLedger.verify(report["provenance"]["entries"])
    assert report["provenance"]["entries"][0]["record"]["artifact_digest"]==report["candidate_trace_digest"]
    assert not report["writes_authorized"]
    assert not report["local_model_invoked"]
    assert value==before


def test_invalid_trailing_action_can_be_removed_without_replaying_rewards_twice():
    value=order()
    value["trace"]=solution(value["plan"])+[{"op":"move","destination":"dock"}]
    result=repair_trace(value,authorized=True)
    assert result["eligible_for_human_review"]
    assert result["candidate_trace"]==solution(value["plan"])


def test_explicit_abandonment_is_not_repaired_away():
    value=order()
    value["trace"]=[{"op":"abandon"}]
    result=repair_trace(value,authorized=True)
    assert not result["eligible_for_human_review"]
    assert result["candidate_trace"]==value["trace"]
    assert result["candidate_status"]=="failed"


def test_exhausted_mutation_budget_does_not_promote():
    value=order()
    value["max_mutations"]=0
    result=repair_trace(value,authorized=True)
    assert not result["eligible_for_human_review"]
    assert result["status"]=="held_exhausted"
    assert result["mutation_count"]==0


def test_valid_trace_does_not_spend_mutations():
    value=order()
    value["trace"]=solution(value["plan"])
    result=repair_trace(value,authorized=True)
    assert result["eligible_for_human_review"]
    assert result["status"]=="already_passing"
    assert result["mutation_count"]==0


def test_source_pin_and_policy_are_not_repaired():
    value=order()
    value["campaign"]["policy"]["max_total_reward"]=9999
    with pytest.raises(EvidenceError):
        repair_trace(value,authorized=True)
    value=order()
    value["expected_plan_digest"]="0"*64
    with pytest.raises(EvidenceError):
        repair_trace(value,authorized=True)


def test_permission_boundary_precedes_source_execution():
    with pytest.raises(PermissionError):
        repair_trace({},authorized=False)
