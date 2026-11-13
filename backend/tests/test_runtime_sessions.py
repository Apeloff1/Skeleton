import pytest

from core.flight_dynamics import FlightInput, FlightState
from core.runtime_sessions import RuntimeSessionManager, SessionCapacityError, SessionNotFound


def test_create_step_and_close_session():
    manager = RuntimeSessionManager(capacity=2)
    session = manager.create(seed=7, resolution=16, thermal_count=2)
    assert manager.snapshot()["active"] == 1
    frame = manager.step(session.id, dt=0.02, controls=FlightInput(roll=0.1))
    assert frame.tick == 1
    closed = manager.close(session.id)
    assert closed.closed is True
    assert manager.snapshot()["closed"] == 1


def test_capacity_backpressures_active_sessions():
    manager = RuntimeSessionManager(capacity=1)
    manager.create(resolution=12, thermal_count=0)
    with pytest.raises(SessionCapacityError):
        manager.create(resolution=12, thermal_count=0)


def test_closed_session_frees_active_capacity():
    manager = RuntimeSessionManager(capacity=1)
    first = manager.create(resolution=12, thermal_count=0)
    manager.close(first.id)
    second = manager.create(resolution=12, thermal_count=0)
    assert second.id != first.id
    assert manager.snapshot()["active"] == 1


def test_missing_session_fails_closed():
    manager = RuntimeSessionManager()
    with pytest.raises(SessionNotFound):
        manager.get("missing")


def test_closed_session_cannot_step():
    manager = RuntimeSessionManager()
    session = manager.create(resolution=12, thermal_count=0)
    manager.close(session.id)
    with pytest.raises(RuntimeError, match="closed"):
        manager.step(session.id, dt=0.02, controls=FlightInput())


def test_prune_closed_keeps_newest_requested_count():
    manager = RuntimeSessionManager(capacity=4)
    ids = []
    for _ in range(3):
        session = manager.create(resolution=12, thermal_count=0)
        ids.append(session.id)
        manager.close(session.id)
    assert manager.prune_closed(keep=1) == 2
    assert manager.snapshot()["closed"] == 1


def test_crash_auto_closes_session():
    manager = RuntimeSessionManager()
    # The default terrain has a lava basin at -16; start just above it, pitched down.
    session = manager.create(
        resolution=16,
        thermal_count=0,
        initial_state=FlightState(x=0.0, y=-15.6, z=0.0, pitch=-0.6, speed=12.0),
    )
    frame = manager.step(session.id, dt=0.1, controls=FlightInput())
    assert frame.crashed is True
    assert manager.get(session.id).closed is True


def test_checkpoint_restores_exact_session_and_owner_scope(tmp_path):
    manager = RuntimeSessionManager(tmp_path, capacity=4)
    session = manager.create(owner="alice", seed=17, resolution=12, thermal_count=1)
    frame = manager.step(session.id, dt=0.02, controls=FlightInput(roll=0.25), owner="alice")

    restored = RuntimeSessionManager(tmp_path, capacity=4)
    loaded = restored.get(session.id, owner="alice")
    assert loaded.simulation.tick == frame.tick
    assert loaded.simulation.time == frame.time
    assert restored.inventory(owner="alice")[0]["session_id"] == session.id
    with pytest.raises(SessionNotFound):
        restored.get(session.id, owner="bob")


def test_corrupt_or_oversized_checkpoint_fails_closed(tmp_path):
    (tmp_path / "bad.json").write_text('{"schema_version":1,"session_id":"bad","owner":"alice","resolution":999999}', encoding="utf-8")
    manager = RuntimeSessionManager(tmp_path)
    with pytest.raises(SessionNotFound):
        manager.get("bad")


@pytest.mark.parametrize("field,value", [
    ("resolution", 513),
    ("thermal_count", 257),
    ("terrain_size", float("inf")),
    ("seed", True),
])
def test_create_rejects_unbounded_simulation_inputs(field, value):
    manager = RuntimeSessionManager()
    options = {"resolution": 12, "thermal_count": 0, field: value}
    with pytest.raises(ValueError):
        manager.create(**options)
