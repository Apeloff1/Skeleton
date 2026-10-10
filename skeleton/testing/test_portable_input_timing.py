"""Real controller/frame scheduling contracts for deterministic ports."""
import pytest
from skeleton.ai.game_builder.portable_kernels.input_timing import (
    InputTimingError, frame_schedule, source_frame_at, edge_pressed, edge_released,
    deadzone_axis, digital_hysteresis, axis_to_eightway, debounce_buttons,
    button_auto_repeat, remap_buttons,
)

def test_rational_50_to_60_refresh_is_driven_by_integer_cumulative_clock():
    schedule=frame_schedule(50,60,50)
    assert sum(schedule)==60
    assert set(schedule)=={1,2}
    assert frame_schedule(60,50,60).count(0)==10
    with pytest.raises(InputTimingError):
        frame_schedule(0,60,1)

def test_target_display_samples_original_frame_without_time_inflation():
    sampled=tuple(source_frame_at(i,50,60) for i in range(120))
    assert sampled[0]==0 and sampled[-1]==99
    assert sampled==tuple(sorted(sampled))
    with pytest.raises(InputTimingError):
        source_frame_at(-1,50,60)


def test_pressed_edges_do_not_repeat_held_button_or_foreign_bit():
    assert edge_pressed(0b0010,0b0110)==0b0100
    assert edge_pressed(0b0010,0b0010)==0
    assert edge_pressed(0,0b0110,mask=0b0010)==0b0010
    with pytest.raises(InputTimingError):
        edge_pressed(-1,0)


def test_release_edges_only_when_button_transitions_high_to_low():
    assert edge_released(0b1110,0b0100)==0b1010
    assert edge_released(0b0100,0b0100)==0
    assert edge_released(0b1110,0b0100,0b0010)==0b0010
    with pytest.raises(InputTimingError):
        edge_released(0,65536)


def test_axis_deadzone_preserves_sign_and_no_center_drift():
    assert deadzone_axis(0)==0
    assert deadzone_axis(4096)==0
    assert deadzone_axis(32767)==32767
    assert deadzone_axis(-32768)==-32767
    assert deadzone_axis(8192)>0
    with pytest.raises(InputTimingError):
        deadzone_axis(1,threshold=32767)


def test_trigger_hysteresis_eliminates_oscillating_threshold_clicks():
    samples=(0,21000,19000,15000,13999,18000,22000)
    assert digital_hysteresis(samples)==(False,True,True,True,False,False,True)
    with pytest.raises(InputTimingError):
        digital_hysteresis((100,),press=10000,release=12000)


def test_eight_way_controller_ports_cardinals_and_diagonals():
    assert axis_to_eightway(0,0)=="neutral"
    assert axis_to_eightway(32767,-32768)=="ne"
    assert axis_to_eightway(-32768,32767)=="sw"
    assert axis_to_eightway(8192,0)=="neutral"
    with pytest.raises(InputTimingError):
        axis_to_eightway(True,0)


def test_button_debounce_waits_for_stable_contiguous_frames():
    samples=(0,1,0,1,1,1,0,0)
    assert debounce_buttons(samples,stable_frames=2)==(0,0,0,0,1,1,1,0)
    assert debounce_buttons((1,0),stable_frames=1)==(1,0)
    with pytest.raises(InputTimingError):
        debounce_buttons((1,),stable_frames=0)


def test_key_repeat_has_one_shot_then_periodic_held_events():
    assert button_auto_repeat((True,)*7,delay=2,interval=2)==(
        True,False,True,False,True,False,True)
    assert button_auto_repeat((True,False,True),delay=2)==(True,False,True)
    with pytest.raises(InputTimingError):
        button_auto_repeat((1,0))

