import math

import pytest

from core.flight_dynamics import FlightInput, FlightModel, FlightState
from core.playable_simulation import PlayableSimulation
from core.terrain_field import HeightField, TerrainConfig, Thermal, seeded_thermals, thermal_lift


def test_height_field_is_deterministic_and_bilinear():
    field_a = HeightField(120.0, 24, config=TerrainConfig(world_size=120.0, lava_radius=12.0, rim_radius=40.0))
    field_b = HeightField(120.0, 24, config=TerrainConfig(world_size=120.0, lava_radius=12.0, rim_radius=40.0))
    points = [(-20.5, 14.25), (0.0, 0.0), (45.2, -33.8)]
    assert [field_a.sample(x, z) for x, z in points] == pytest.approx(
        [field_b.sample(x, z) for x, z in points]
    )


def test_seeded_thermals_are_repeatable():
    assert seeded_thermals(5, seed=42) == seeded_thermals(5, seed=42)
    assert seeded_thermals(5, seed=42) != seeded_thermals(5, seed=43)


def test_thermal_lift_peaks_near_center_and_respects_ceiling():
    thermal = Thermal(x=0.0, z=0.0, radius=20.0, strength=10.0, ceiling=100.0)
    center = thermal_lift(0.0, 20.0, 0.0, [thermal])
    edge = thermal_lift(15.0, 20.0, 0.0, [thermal])
    above = thermal_lift(0.0, 101.0, 0.0, [thermal])
    assert center > edge > 0.0
    assert above == 0.0


def test_flight_input_is_clamped_and_state_moves_forward():
    state = FlightState(x=0.0, y=100.0, z=0.0, yaw=0.0, pitch=0.0, speed=38.0)
    model = FlightModel()
    model.step(state, 0.1, FlightInput(roll=4.0, pitch=-4.0, flare=3.0))
    assert -0.98 <= state.bank <= 0.98
    assert -0.72 <= state.pitch <= 0.82
    assert state.z < 0.0
    assert 12.0 <= state.speed <= 102.0


def test_thermal_can_increase_altitude_vs_no_thermal():
    cold = FlightState(x=0.0, y=100.0, z=0.0, yaw=0.0, pitch=0.0, speed=38.0)
    hot = FlightState(x=0.0, y=100.0, z=0.0, yaw=0.0, pitch=0.0, speed=38.0)
    model = FlightModel()
    model.step(cold, 1.0, FlightInput(), thermal_lift=0.0)
    model.step(hot, 1.0, FlightInput(), thermal_lift=20.0)
    assert hot.y > cold.y


def test_simulation_ticks_and_reports_frame():
    terrain = HeightField(120.0, 24, config=TerrainConfig(world_size=120.0, lava_radius=12.0, rim_radius=40.0))
    state = FlightState(x=50.0, y=100.0, z=0.0, speed=30.0)
    sim = PlayableSimulation(terrain=terrain, state=state)
    frame = sim.step(0.05, FlightInput(roll=0.2))
    assert frame.tick == 1
    assert frame.time == pytest.approx(0.05)
    assert frame.state["alive"] is True
    assert frame.clearance > 0


def test_simulation_crashes_on_terrain_contact():
    terrain = HeightField(120.0, 24, config=TerrainConfig(world_size=120.0, lava_radius=12.0, rim_radius=40.0))
    ground = terrain.sample(50.0, 0.0)
    state = FlightState(x=50.0, y=ground + 0.1, z=0.0, pitch=-0.4, speed=12.0)
    sim = PlayableSimulation(terrain=terrain, state=state, crash_clearance=1.0)
    frame = sim.step(0.05, FlightInput())
    assert frame.crashed is True
    assert sim.state.alive is False


def test_run_stops_on_crash_or_max_steps():
    terrain = HeightField(120.0, 24, config=TerrainConfig(world_size=120.0, lava_radius=12.0, rim_radius=40.0))
    state = FlightState(x=50.0, y=100.0, z=0.0, speed=20.0)
    sim = PlayableSimulation(terrain=terrain, state=state)
    frames = sim.run(dt=0.02, controls=[FlightInput()] * 50, max_steps=7)
    assert len(frames) == 7
    assert frames[-1].tick == 7


def test_negative_or_zero_time_is_rejected():
    state = FlightState()
    model = FlightModel()
    with pytest.raises(ValueError):
        model.step(state, -0.1, FlightInput())
    sim = PlayableSimulation(state=FlightState())
    with pytest.raises(ValueError):
        sim.step(0.0)
