from __future__ import annotations

import json

import pytest

from skeleton.game import (
    REPLAY_SCHEMA_VERSION,
    ReplayError,
    ReplayTrace,
    compare,
    load_trace,
    record,
    replay,
    verify,
)
from skeleton.game.clock import ClockError, GameClock
from skeleton.game.engine import DeterministicEngine, EngineError


def _inputs() -> list[dict[str, object]]:
    return [
        {"t": 0, "verb": "attack"},
        {"t": 1, "verb": "defend"},
        {"t": 2, "verb": "grant_xp"},
        {"t": 3, "verb": "attack"},
        {"t": 4, "verb": "wait"},
    ]


def test_same_seed_same_digest() -> None:
    left = record(seed=8847291, inputs=_inputs())
    right = record(seed=8847291, inputs=_inputs())
    assert left.digest == right.digest
    assert left.digest == replay(left).digest
    assert compare(left, right)["match"] is True
    assert compare(left, right)["first_divergent_frame"] is None
    assert verify(left.to_dict())["ok"] is True


def test_seed_change_and_input_change_diverge() -> None:
    base = record(seed=1, inputs=_inputs())
    other_seed = record(seed=2, inputs=_inputs())
    other_input = record(seed=1, inputs=_inputs() + [{"t": 5, "verb": "attack"}])
    assert base.digest != other_seed.digest
    assert base.digest != other_input.digest
    report = compare(base, other_seed)
    assert report["match"] is False


def test_malformed_and_version_mismatch_fail_closed() -> None:
    with pytest.raises(ReplayError, match="empty"):
        load_trace("   ")
    with pytest.raises(ReplayError, match="malformed"):
        load_trace("{")
    good = record(seed=3, inputs=_inputs()).to_dict()
    good["schema_version"] = 99
    with pytest.raises(ReplayError, match="incompatible"):
        load_trace(good)
    good = record(seed=3, inputs=_inputs()).to_dict()
    del good["digest"]
    with pytest.raises(ReplayError, match="missing digest"):
        load_trace(good)
    good = record(seed=3, inputs=_inputs()).to_dict()
    good["digest"] = "0" * 64
    with pytest.raises(ReplayError, match="sealed digest"):
        verify(good)


def test_engine_rejects_unknown_verb_and_duplicate_ticks() -> None:
    engine = DeterministicEngine(seed=9)
    with pytest.raises(EngineError, match="unknown verb"):
        engine.apply("explode")
    with pytest.raises(EngineError, match="duplicate"):
        engine.run([{"t": 0, "verb": "wait"}, {"t": 0, "verb": "attack"}])


def test_clock_is_explicit_and_bounded() -> None:
    clock = GameClock(tick=0, hz=60)
    assert clock.seconds == 0.0
    assert clock.advance(2).tick == 2
    with pytest.raises(ClockError):
        GameClock(tick=-1)
    with pytest.raises(ClockError):
        GameClock(tick=0, hz=0)


def test_cli_replay_prints_digest(capsys: pytest.CaptureFixture[str]) -> None:
    from skeleton.__main__ import main

    assert main(["replay", "--seed", "8847291"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == REPLAY_SCHEMA_VERSION
    assert payload["ok"] is True
    assert len(payload["digest"]) == 64
    assert isinstance(payload["digest"], str)


def test_replay_trace_roundtrip_type() -> None:
    sealed = record(seed="house-era", inputs=_inputs(), hz=30)
    assert isinstance(sealed, ReplayTrace)
    again = load_trace(json.dumps(sealed.to_dict()))
    assert again.digest == sealed.digest
    assert again.hz == 30
