"""Control layout, source binding, deterministic input observations, Godot integration."""
import copy
import json
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_controllers import (
    ButtonBinding,ControllerEvent,ControllerProfile,
    controller_profiles,profile_for,replay_controller,export_controller_profile,
)
from skeleton.jeeves.game_frontier_expedition_godot import (
    emit_expedition_godot_project,verify_expedition_godot_project,
)
from tests.test_game_frontier_expedition_godot import world,traveler


def test_seven_original_controller_profiles_have_usable_unambiguous_layouts():
    presets=controller_profiles()
    assert len(presets)==7
    assert len({p.profile_id for p in presets})==7
    for profile in presets:
        assert len(profile.digest)==64
        assert profile==profile_for(profile.profile_id)
        assert {"travel","rest","navigate_up","navigate_down"}.issubset(
            {b.action for b in profile.buttons})
        assert len({b.godot_button for b in profile.buttons})==len(profile.buttons)


def test_source_bound_godot_controller_is_real_resource_and_source_checked():
    w,p=world(),traveler()
    controller=profile_for("dual_stick")
    files=emit_expedition_godot_project(w,p,controller_profile=controller)
    assert "game/frontier/controller.json" in files
    data=json.loads(files["game/frontier/controller.json"])
    assert data["world_digest"]==w.digest
    assert data["hud_below_viewport"]
    assert data["input_map"]["ui_accept"]==0
    assert "InputEventJoypadButton.new()" in files["game/frontier/expedition.gd"]
    assert "_install_controller()" in files["game/frontier/expedition.gd"]
    assert verify_expedition_godot_project(
        files,w,p,controller_profile=controller)["asset_count"]==7
    with pytest.raises(ExpeditionError,match="differs"):
        verify_expedition_godot_project(
            files,w,p,controller_profile=profile_for("accessible"))


def test_press_release_repeat_input_is_deterministic_and_debounced():
    p=profile_for("four_button")
    events=(
        ControllerEvent(1,0,True),ControllerEvent(2,0,True),
        ControllerEvent(3,0,False),ControllerEvent(4,0,True),
        ControllerEvent(5,0,False),
    )
    first=replay_controller(p,events,world_digest="f"*64)
    second=replay_controller(p,events,world_digest="f"*64)
    assert first==second
    assert [e.action for e in first]==["travel","travel"]
    assert first[1].previous_receipt==first[0].receipt
    assert first[0].receipt!=first[1].receipt


def test_foreign_device_invalid_frame_and_unrecognized_profiles_fail_closed():
    profile=profile_for("arcade")
    with pytest.raises(ExpeditionError,match="foreign"):
        replay_controller(
            profile,(ControllerEvent(1,0,True,device=1),),
            world_digest="f"*64)
    with pytest.raises(ExpeditionError,match="frame order"):
        replay_controller(
            profile,(ControllerEvent(3,0,True),ControllerEvent(1,1,True)),
            world_digest="f"*64)
    with pytest.raises(ExpeditionError,match="not found"):
        profile_for("nonexistent")


def test_controller_duplicate_physical_indices_and_actions_block_binding():
    essentials=profile_for("four_button").buttons
    with pytest.raises(ExpeditionError,match="physical"):
        ControllerProfile("dupe","era",essentials[:3]+(
            ButtonBinding("other","rest",0,"duplicate"),))
    with pytest.raises(ExpeditionError,match="action mapping"):
        ControllerProfile("dupe","era",essentials+(
            ButtonBinding("other","travel",4,"same action"),))


def test_controller_source_is_not_physical_device_proof():
    data=export_controller_profile(profile_for("accessible"),"e"*64)
    assert not data["receipts_are_hid_observations"]
    assert data["world_digest"]=="e"*64
    assert data["receipt_digest"]
