"""#4167: weather + 30/50/60/120 FPS + LOD in the canonical native runtime loop."""
import pytest

from skeleton.ai.agents.jeeves.game_frontier_dynamics import (
    Cloud, WindField, WindLayer, WindVector,
)
from skeleton.game.frontier import (
    FrontierEntity, FrontierNativeRuntime, FrontierRuntimeError,
    prove_presentation_tiers,
)
from skeleton.game.render.lod_system import LODLevel, LODPolicy

D = "a" * 64


def _lod():
    return LODPolicy([LODLevel(0, 0, D), LODLevel(1, 20_000, "b" * 64),
                      LODLevel(2, 60_000, "c" * 64)])


def _wind():
    return WindField([WindLayer(0, WindVector(4.0, 1.0), 2.0),
                      WindLayer(2000, WindVector(12.0, -3.0), 4.0)], seed=7)


def _rt(fps, **kw):
    return FrontierNativeRuntime(
        fps=fps, wind=_wind(), lod=_lod(),
        entities=[FrontierEntity("hero", 0, 0, 0, vx_mps=10.0),
                  FrontierEntity("leaf", 5, 5, 2, wind_coupling=1.0)],
        clouds=[Cloud("c1", 0, 0, 1500, .6), Cloud("c2", 100, 50, 2500, .4)],
        **kw)


@pytest.mark.parametrize("fps", [30, 50, 60, 120])
def test_each_tier_presents_exact_frame_count(fps):
    rt = _rt(fps)
    frames = rt.run_seconds(2)
    assert len(frames) == 2 * fps
    assert frames[-1].deadline_ns == 2 * fps * 1_000_000_000 // fps
    assert rt.tick == 100  # 50 Hz physics, independent of fps
    assert all(0.0 <= f.interpolation_alpha < 1.0 for f in frames)


def test_physics_identical_across_tiers():
    proof = prove_presentation_tiers(_rt, seconds=3)
    assert proof["frames_exact"] and proof["deadlines_drift_free"]
    assert proof["physics_identical"]
    assert {m["simulation_ticks"] for m in proof["modes"].values()} == {150}
    assert all(m["dropped_catchup_ns"] == 0 for m in proof["modes"].values())


def test_weather_advances_clouds_and_wind_coupled_entities():
    rt = _rt(60)
    rt.run_seconds(1)
    c1 = {c.cloud_id: c for c in rt.clouds}["c1"]
    assert c1.x_m > 2.0  # pushed east by the wind layers
    ents = {e.entity_id: e for e in rt.entities}
    assert ents["leaf"].x_m > 5.0 and ents["hero"].x_m == pytest.approx(10.0)


def test_lod_switches_with_distance():
    rt = _rt(30)
    levels = [dict(f.lod_levels)["hero"] for f in rt.run_seconds(8)]
    assert levels[0] == 0 and 1 in levels and levels[-1] == 2
    assert levels == sorted(levels)  # moving away only coarsens


def test_deterministic_frame_digests():
    a = [f.frame_digest for f in _rt(120).run_seconds(1)]
    b = [f.frame_digest for f in _rt(120).run_seconds(1)]
    assert a == b and len(set(a)) == len(a)


def test_catchup_cap_records_lost_time_without_extra_ticks():
    rt = _rt(30, max_catchup_ticks=2)
    assert rt.advance_to(1_000_000_000) == 2
    assert rt.dropped_catchup_ns == 1_000_000_000 - 40_000_000
    assert rt.accumulator_ns == 0


def test_interpolated_clouds_between_ticks():
    rt = _rt(120)
    f = rt.present_next()  # 8.33ms < 20ms step: no tick yet
    assert f.simulation_tick == 0 and f.interpolation_alpha > 0
    assert dict((i, (x, y)) for i, x, y in f.cloud_positions_m)["c1"] == (0, 0)


@pytest.mark.parametrize("kw", [{"fps": 45}, {"fps": 60, "simulation_hz": 60},
                                {"fps": True}])
def test_rejects_invalid_config(kw):
    with pytest.raises(FrontierRuntimeError):
        FrontierNativeRuntime(wind=_wind(), lod=_lod(), **kw)


def test_rejects_duplicate_entities_and_time_reversal():
    with pytest.raises(FrontierRuntimeError):
        FrontierNativeRuntime(fps=60, wind=_wind(), lod=_lod(),
                              entities=[FrontierEntity("a", 0, 0, 0)] * 2)
    rt = _rt(60)
    rt.advance_to(100)
    with pytest.raises(FrontierRuntimeError):
        rt.advance_to(50)
