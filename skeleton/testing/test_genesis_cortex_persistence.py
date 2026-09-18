from pathlib import Path

import pytest

from skeleton.cortex.live import (
    attach,
    configured_own_path,
    get_control,
    live_cortex,
    own_path,
    persist,
    persistence_configured,
    reset_live,
    status,
)
from skeleton.genesis import Genesis
from skeleton.kernel.events import EventBus


def _cortex_phase() -> Genesis:
    genesis = Genesis(seed=7)
    genesis._phase_cortex()
    return genesis


def test_unconfigured_genesis_keeps_fresh_cortex(monkeypatch):
    monkeypatch.delenv("SKELETON_OWN", raising=False)
    reset_live()

    first = _cortex_phase()
    second = _cortex_phase()

    assert persistence_configured() is False
    assert first.handles["cortex"] is not second.handles["cortex"]
    assert first.handles["jeeves"].cortex is first.handles["cortex"]
    assert second.handles["jeeves"].cortex is second.handles["cortex"]
    reset_live()


def test_configured_genesis_reuses_live_cortex_and_rebinds_bus(monkeypatch, tmp_path):
    state_path = tmp_path / "own.json"
    monkeypatch.setenv("SKELETON_OWN", str(state_path))
    reset_live(wipe_disk=True)

    first = _cortex_phase()
    first_cortex = first.handles["cortex"]
    second = _cortex_phase()

    assert persistence_configured() is True
    assert configured_own_path() == state_path
    assert second.handles["cortex"] is first_cortex
    assert live_cortex() is first_cortex
    assert second.handles["jeeves"].cortex is first_cortex
    assert first_cortex._bus is second.bus
    assert get_control() is not None
    assert get_control()._bus is second.bus
    reset_live(wipe_disk=True)


def test_configured_genesis_restores_persisted_cortex(monkeypatch, tmp_path):
    state_path = tmp_path / "own.json"
    monkeypatch.setenv("SKELETON_OWN", str(state_path))
    reset_live(wipe_disk=True)

    first = _cortex_phase()
    cortex = first.handles["cortex"]
    cortex.acquired["left"] = 7
    cortex._surpass.add("left")

    saved = persist()
    assert state_path.exists()
    assert saved["acquired"]["left"] == 7

    reset_live()
    restored = _cortex_phase()
    restored_cortex = restored.handles["cortex"]

    assert restored_cortex.acquired["left"] == 7
    assert "left" in restored_cortex._surpass
    assert restored.handles["jeeves"].cortex is restored_cortex
    assert restored_cortex._bus is restored.bus
    reset_live(wipe_disk=True)


def test_blank_persistence_env_keeps_legacy_path_without_sharing(monkeypatch):
    monkeypatch.setenv("SKELETON_OWN", "   ")
    reset_live()

    first = _cortex_phase()
    second = _cortex_phase()

    assert configured_own_path() is None
    assert persistence_configured() is False
    assert own_path() == Path(".skeleton") / "own.json"
    assert first.handles["cortex"] is not second.handles["cortex"]
    reset_live()


def test_configured_corrupt_state_fails_closed(monkeypatch, tmp_path):
    from skeleton.cortex.live import CortexPersistenceError, live_cortex

    state_path = tmp_path / "own.json"
    state_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("SKELETON_OWN", str(state_path))
    reset_live()

    with pytest.raises(CortexPersistenceError, match="failed to restore"):
        live_cortex()
    assert status()["last_load"]["ok"] is False
    reset_live()


def test_unconfigured_live_does_not_restore_legacy_disk(monkeypatch, tmp_path):
    import json

    from skeleton.cortex.live import live_cortex

    monkeypatch.delenv("SKELETON_OWN", raising=False)
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / ".skeleton" / "own.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"acquired": {"poison": 9}, "own": {}}), encoding="utf-8")
    reset_live()

    cortex = live_cortex()
    assert "poison" not in cortex.acquired
    assert status()["last_load"]["reason"] == "persistence_not_configured"
    reset_live()


def test_attach_tolerates_cortex_without_event_observer(monkeypatch, tmp_path):
    state_path = tmp_path / "own.json"
    monkeypatch.setenv("SKELETON_OWN", str(state_path))
    reset_live(wipe_disk=True)
    bus = EventBus()

    cortex = attach(bus)

    assert cortex._bus is bus
    assert get_control() is not None
    assert get_control()._bus is bus
    reset_live(wipe_disk=True)
