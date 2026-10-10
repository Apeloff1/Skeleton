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
