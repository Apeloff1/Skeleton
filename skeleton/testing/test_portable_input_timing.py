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

