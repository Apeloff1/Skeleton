"""Real synthesized quests, analytics, reference pixels and portable scene owners."""
from copy import deepcopy

import pytest

from skeleton.app.recovered_evidence import EvidenceError,digest
from skeleton.ai.game_builder.quest_playtest_analytics import qualify_cohort
from skeleton.ai.game_builder.synthesized_quest_planner import plan_campaign
from skeleton.ai.game_builder.synthesized_quest_runtime import solution
from skeleton.game.studio_frame_qualification import qualify_frames
from skeleton.game.gameplay.scene_travel import original_demo,new_session
from skeleton.game.gameplay.scene_byte_qualification import qualify_scene


def quest():
    return {"schema":"skeleton.synthesized-quest.order.v1","campaign_id":"recovery",
            "title":"Lantern","seed":8,"length":3,
            "world":{"start":"dock","edges":{"dock":["hill"],"hill":["dock"]},"npcs":{}},
            "policy":{"banned_terms":[],"max_reward_per_step":4,"max_total_reward":12,
                      "allowed_reward_kinds":["xp"]},
            "mechanics":{"registry":[
                {"id":"travel","provides":["travel"],"requires":[],"conflicts":[],"params":{}},
                {"id":"quest","provides":["quest"],"requires":["travel"],"conflicts":[],"params":{}},
            ],"selected":["travel","quest"],"overrides":{}}}


def scenario(count,limit,ending,collection=True):
    return {"count":count,"action_limit":limit,"ending":ending,
            "seconds_per_action":1,"collection":collection}


def cohort():
    campaign=quest()
    n=len(solution(plan_campaign(campaign,authorized=True)))
    return {"schema":"skeleton.quest-playtest-analytics.order.v1","campaign":campaign,
            "min_cohort":5,"scenarios":[scenario(6,n,"complete"),scenario(5,0,"abandon"),
                                     scenario(4,0,"truncate",False)]}


def test_real_synthetic_execution_and_privacy():
    report=qualify_cohort(cohort(),authorized=True)
    assert report["synthetic_actors_executed"]==15
    assert report["metrics"]["session_count"]==11
    assert report["metrics"]["funnel"]["reached"]==[11,6,6,6]
    assert report["metrics"]["difficulty_heatmap"]["cells"][0]["failures"]==5
    assert report["real_player_data"] is False
    assert report==qualify_cohort(cohort(),authorized=True)


def test_small_cohort_is_suppressed():
    order=cohort()
    order["scenarios"]=[scenario(4,0,"truncate")]
    assert qualify_cohort(order,authorized=True)["metrics"] is None


def test_false_terminal_claim_rejected():
    order=cohort()
    order["scenarios"]=[scenario(5,0,"complete")]
    with pytest.raises(EvidenceError):
        qualify_cohort(order,authorized=True)


def test_no_implicit_playtest():
    with pytest.raises(PermissionError):
        qualify_cohort({},authorized=False)


def frame(index,invert=False):
    mask="".join("1" if (x<4)!=invert else "0" for y in range(8) for x in range(8))
    return {"index":index,"mask":mask,"rgb":"".join("ffffff" if x=="1" else "000000" for x in mask)}


def frame_order():
    palette={"surface":"000000","foreground":"ffffff"}
    return {"schema":"skeleton.studio-frame-qualification.order.v1","subject":"dragon",
            "era":"32bit","tier":"premium","weeks":20,"width":8,"height":8,
            "palette":palette,"expected_palette_digest":digest(palette),
            "frames":[frame(0),frame(1)],"max_mask_change_ppm":100000,"max_rgb_change_ppm":100000}


def test_reference_metrics_and_production_guidance():
    result=qualify_frames(frame_order(),authorized=True)
    assert result["reference_sequence_passed"]
    assert result["transitions"][0]["metrics"]["mask_iou_ppm"]==1000000
    assert not result["renderer_executed"]
    assert len(result["production_guidance"]["milestones"])==5


def test_discontinuity_not_accepted_as_animation_qualification():
    order=frame_order()
    order["frames"][1]=frame(1,True)
    result=qualify_frames(order,authorized=True)
    assert result["all_reference_frames_passed"]
    assert not result["reference_sequence_passed"]
    assert result["production_guidance"]["followups"][0]["kind"]=="temporal_discontinuity"


def test_palette_and_pixel_tamper_rejected():
    order=frame_order()
    order["palette"]["surface"]="123456"
    with pytest.raises(EvidenceError):
        qualify_frames(order,authorized=True)
    order=frame_order()
    order["frames"][0]["mask"]="1"
    with pytest.raises(EvidenceError):
        qualify_frames(order,authorized=True)


def scene_order():
    world,actions=original_demo()
    return {"schema":"skeleton.scene-byte-qualification.order.v1","world":world,
            "expected_source_digest":new_session(world)["source_digest"],"actions":actions,
            "checkpoint_interval":1,"expected_phase":"won"}


def test_real_scene_bytes_and_earned_ending():
    result=qualify_scene(scene_order(),authorized=True)
    assert result["phase"]=="won"
    assert result["checkpoints"][-1]["actions_applied"]==result["actions_executed"]
    assert result["canonical_scene_executed"]
    assert result==qualify_scene(scene_order(),authorized=True)


def test_scene_source_and_end_claims_are_independent():
    order=scene_order()
    order["expected_source_digest"]="0"*64
    with pytest.raises(EvidenceError):
        qualify_scene(order,authorized=True)
    order=scene_order()
    order["expected_phase"]="active"
    with pytest.raises(EvidenceError):
        qualify_scene(order,authorized=True)
