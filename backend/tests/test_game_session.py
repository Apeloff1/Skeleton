import pytest

from core.course_runtime import Course, Ring, Spawn
from core.flight_dynamics import FlightInput, FlightState
from core.game_session import GameSession
from core.progression import Medal
from core.terrain_field import HeightField, TerrainConfig


def flatish_field():
    return HeightField(
        120.0,
        24,
        config=TerrainConfig(world_size=120.0, lava_radius=12.0, rim_radius=40.0),
    )


def test_game_session_records_ghost_and_distance():
    terrain = flatish_field()
    course = Course("free", "Free", 0, Spawn(50, 80, 0, 0), ())
    session = GameSession(course, terrain=terrain, ghost_sample_interval=0.02)
    before = len(session.ghost)
    step = session.step(0.02, FlightInput())
    assert step.frame.tick == 1
    assert session.distance > 0
    assert len(session.ghost) > before


def test_game_session_crosses_ring_and_finishes():
    terrain = flatish_field()
    ring = Ring(0, 60, 0, 0, 0, 1, 10)
    course = Course("c", "Course", 10, Spawn(0, 60, -2, 0), (ring,))
    state = FlightState(x=0, y=60, z=-2, yaw=3.141592653589793, pitch=0, speed=40)
    session = GameSession(course, terrain=terrain, state=state, ghost_sample_interval=1)
    result = session.step(0.1, FlightInput())
    assert result.finished is True
    assert result.medal in {Medal.ELITE, Medal.GOLD}


def test_finish_payload_is_progression_ready():
    terrain = flatish_field()
    course = Course("free", "Free", 0, Spawn(50, 80, 0, 0), ())
    session = GameSession(course, terrain=terrain)
    session.step(0.05, FlightInput(roll=0.2))
    payload = session.finish_payload()
    assert payload["course_id"] == "free"
    assert payload["total_rings"] == 0
    assert payload["distance"] > 0
    assert payload["ghost"]
    assert {"t", "x", "y", "z", "yaw", "pitch", "bank", "speed"} <= set(payload["ghost"][0])


def test_invalid_ghost_interval_rejected():
    terrain = flatish_field()
    course = Course("free", "Free", 0, Spawn(0, 80, 0, 0), ())
    with pytest.raises(ValueError):
        GameSession(course, terrain=terrain, ghost_sample_interval=0)
