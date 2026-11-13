"""Source-preserving controller calibration and simultaneous input replay."""
from dataclasses import replace
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_controllers import (
    ControllerEvent,profile_for,
)
from skeleton.jeeves.game_frontier_expedition_input import (
    AnalogSample,AxisBinding,AxisCalibration,remap_controller,
    translate_analog,merge_input_replays,verify_input_replay,
)
WORLD="f"*64


def test_remap_is_source_revision_and_never_mutates_existing_game_profile():
    profile=profile_for("dual_stick")
    edited=remap_controller(profile,action="travel",button_index=20)
    assert edited.digest!=profile.digest
    assert next(b for b in edited.buttons if b.action=="travel").godot_button==20
    assert next(b for b in profile.buttons if b.action=="travel").godot_button==0
    assert edited.profile_id==profile.profile_id


def test_source_calibration_rejects_collision_undefined_action_and_nonfinite():
    p=profile_for("four_button")
    with pytest.raises(ExpeditionError,match="collides"):
        remap_controller(p,action="travel",button_index=1)
    with pytest.raises(ExpeditionError,match="not defined"):
        remap_controller(p,action="inventory",button_index=20)
    with pytest.raises(ExpeditionError,match="hysteresis"):
        AxisCalibration(axis=0,deadzone=.1,release=.7,engage=.5)
    with pytest.raises(ExpeditionError):
        AxisCalibration(axis=0,engage=float("nan"))


def test_actual_axis_samples_have_hysteresis_and_do_not_repeat_in_deadzone():
    binding=(AxisBinding(AxisCalibration(axis=1),-1,"navigate_up"),)
    samples=(
        AnalogSample(1,1,-.12),AnalogSample(2,1,-.7),
        AnalogSample(3,1,-.8),AnalogSample(4,1,-.43),
        AnalogSample(5,1,-.32),AnalogSample(6,1,-.79),
    )
    assert translate_analog(samples,binding)==(
        (2,"navigate_up"),(6,"navigate_up"),
    )


def test_negative_axis_inversion_changes_actual_action():
    inverted=(AxisBinding(AxisCalibration(axis=0,invert=True),1,"navigate_down"),)
    assert translate_analog(
        (AnalogSample(3,0,-.8),),inverted
    )==((3,"navigate_down"),)
    plain=(AxisBinding(AxisCalibration(axis=0),1,"navigate_down"),)
    assert translate_analog(
        (AnalogSample(3,0,-.8),),plain
    )==()


def test_digital_and_analog_streams_merge_at_source_frame_boundaries():
    p=profile_for("four_button")
    digital=(
        ControllerEvent(1,0,True),ControllerEvent(2,0,False),
        ControllerEvent(10,1,True),
    )
    analog=(
        AnalogSample(3,0,.85),AnalogSample(4,0,.1),
        AnalogSample(8,0,.95),
    )
    bindings=(AxisBinding(AxisCalibration(axis=0),1,"navigate_down"),)
    proof=merge_input_replays(
        p,digital,analog,bindings,world_digest=WORLD,
    )
    assert [x.action for x in proof]==[
        "travel","navigate_down","navigate_down","rest",
    ]
    assert [x.frame for x in proof]==[1,3,8,10]
    assert all(b.prior_receipt==a.receipt for a,b in zip(proof,proof[1:]))
    assert proof==merge_input_replays(
        p,digital,analog,bindings,world_digest=WORLD,
    )
    verify_input_replay(p,digital,analog,bindings,proof,world_digest=WORLD)


def test_adversarial_input_rewrite_fails_independent_source_replay():
    p=profile_for("arcade")
    events=(ControllerEvent(1,0,True),)
    evidence=merge_input_replays(
        p,events,(),(AxisBinding(AxisCalibration(0),1,"travel"),),
        world_digest=WORLD,
    )
    forged=(replace(evidence[0],action="rest"),)
    with pytest.raises(ExpeditionError,match="differs"):
        verify_input_replay(
            p,events,(),(AxisBinding(AxisCalibration(0),1,"travel"),),
            forged,world_digest=WORLD,
        )


def test_controller_device_isolation_and_monotonic_frame_enforced():
    bindings=(AxisBinding(AxisCalibration(0),1,"travel"),)
    with pytest.raises(ExpeditionError,match="foreign device"):
        translate_analog((AnalogSample(1,0,1,device=2),),bindings)
    with pytest.raises(ExpeditionError,match="frame order"):
        translate_analog((
            AnalogSample(2,0,1),AnalogSample(1,0,0),
        ),bindings)


def test_identical_digital_analog_frame_order_is_deterministic():
    p=profile_for("four_button")
    data=merge_input_replays(
        p,(ControllerEvent(2,0,True),),
        (AnalogSample(2,0,.9),),
        (AxisBinding(AxisCalibration(0),1,"navigate_up"),),
        world_digest=WORLD,
    )
    assert [x.source for x in data]==["digital","analog"]
    assert len({x.receipt for x in data})==2
