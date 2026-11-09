from core.input_fusion import InputFusion, radial_deadzone
from core.sensory_cues import ambience, finish, ring
from core.vfx_cues import VfxState


def test_radial_deadzone_zeroes_small_input_and_rescales_large_input():
    assert radial_deadzone(0.05, 0.05) == (0.0, 0.0)
    x, y = radial_deadzone(0.5, 0.0)
    assert 0 < x < 0.5
    assert y == 0.0


def test_input_fusion_merges_sources_and_edges_pause():
    fusion = InputFusion()
    first = fusion.sample(keys={"KeyA", "Space", "Escape"}, touch_pitch=0.5)
    second = fusion.sample(keys={"Escape"})
    released = fusion.sample(keys=set())
    pressed_again = fusion.sample(keys={"Escape"})
    assert first.roll == 1.0
    assert first.pitch == 0.5
    assert first.flare == 1.0
    assert first.pause_pressed is True
    assert second.pause_pressed is False
    assert released.pause_pressed is False
    assert pressed_again.pause_pressed is True


def test_steer_override_wins_over_other_roll_sources():
    sample = InputFusion().sample(keys={"KeyA"}, touch_roll=1.0, steer_override=-0.25)
    assert sample.roll == -0.25


def test_sensory_cues_scale_from_runtime_state():
    low = ambience(12, 0)
    fast = ambience(92, 4)
    assert fast.intensity > low.intensity
    assert dict(fast.metadata)["thermal"] == 1.0
    assert ring(99).pitch == 440 + 8 * 48
    assert [cue.pitch for cue in finish()] == [392.0, 494.0, 587.0]


def test_vfx_trauma_decays_and_reduced_motion_disables_shake():
    state = VfxState()
    state.add_trauma(1.0)
    state.step(0.1)
    assert 0 < state.trauma < 1
    assert state.shake_offset(reduced_motion=True).x == 0.0
    offset = state.shake_offset()
    assert any(abs(v) > 0 for v in (offset.x, offset.y, offset.z))


def test_vfx_trail_is_bounded_and_streaks_are_speed_gated():
    state = VfxState(trail_limit=3)
    for i in range(5):
        state.push_trail(float(i), 0.0, 0.0)
    assert state.trail == [(2.0, 0.0, 0.0), (3.0, 0.0, 0.0), (4.0, 0.0, 0.0)]
    assert state.speed_streak_intensity(48.0) == 0.0
    assert state.speed_streak_intensity(102.0) == 1.0
