"""Actual source gameplay, digital/analogue parity, and SQLite checkpoint reuse."""
import pytest
from skeleton.app.recovered_evidence import EvidenceError
from skeleton.app.expedition_controller_model import plan_journey,source
from skeleton.app.expedition_controller_qualification import qualify_journey,compile_input
from skeleton.app.expedition_controller_bridge import Journey
from skeleton.jeeves.game_frontier_expedition_controllers import controller_profiles
from skeleton.jeeves.game_frontier_expedition_input import merge_input_replays,GameInput
from skeleton.jeeves.game_frontier_expedition import ExpeditionEpisode
from skeleton.jeeves.game_frontier_expedition_save_store import ExpeditionSaveStore,ExpeditionSaveError


def order():
    return {"schema":"skeleton.expedition-controller-journey.order.v1","project_id":"original_journey",
            "seed":7,"islands":3,"gdd_digest":"a"*64,"objective":"fastest"}


def test_all_known_profiles_reach_same_actual_state():
    doc=order()
    plan=plan_journey(doc,authorized=True)
    report=qualify_journey(doc,expected_plan_digest=plan["digest"],authorized=True)
    assert report["profile_count"]==7
    assert report["executed_variant_count"]==21
    assert len({r["snapshot_digest"] for r in report["variants"]})==1
    assert all(r["actual_save_generations"]==2 for r in report["variants"])
    assert report["hardware_devices_tested"]==0


def test_analog_hysteresis_and_button_bounce_do_not_duplicate_actions():
    p=controller_profiles()[0]
    actions=("navigate_up","navigate_down","travel","rest")
    for variant in ("digital","remapped","mixed_analog"):
        profile,digital,analog,bindings=compile_input(p,actions,variant)
        actual=merge_input_replays(profile,digital,analog,bindings,world_digest="a"*64)
        assert tuple(x.action for x in actual)==actions


def test_source_pin_and_authority():
    with pytest.raises(PermissionError):
        qualify_journey({},expected_plan_digest="a"*64,authorized=False)
    with pytest.raises(EvidenceError):
        qualify_journey(order(),expected_plan_digest="a"*64,authorized=True)


def test_invalid_originated_input_does_not_mutate_game():
    world,player,_=source(order())
    journey=Journey(ExpeditionEpisode(world,player))
    initial=journey.episode.snapshot()
    with pytest.raises(EvidenceError):
        journey.apply(GameInput(2,0,"travel",0,"digital","a"*64,"b"*64))
    assert journey.episode.snapshot()==initial


def test_forged_live_episode_rejected_before_save(tmp_path):
    world,player,_=source(order())
    episode=ExpeditionEpisode(world,player)
    episode.stamina=0
    with ExpeditionSaveStore(tmp_path/"s.db") as store:
        with pytest.raises(ExpeditionSaveError):
            store.save("forged",episode)
        assert store.load("forged",world,player) is None
