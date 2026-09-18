from __future__ import annotations

import json
import random
import time
import uuid
from itertools import count

import pytest

from skeleton.game import (
    REPLAY_SCHEMA,
    REPLAY_SCHEMA_VERSION,
    AIBehaviorSpec,
    CombatStyle,
    CombatSystemSpec,
    EconomySystemSpec,
    GameReplayError,
    MechanicsReplay,
    ProgressionStyle,
    ProgressionSystemSpec,
    ReplayStep,
)
from skeleton.game.replay import canonical_dumps, parse_trace


def _replay() -> MechanicsReplay:
    return MechanicsReplay()


def _systems() -> dict[str, object]:
    return {
        "combat": CombatSystemSpec(style=CombatStyle.TURN_BASED),
        "progression": ProgressionSystemSpec(
            style=ProgressionStyle.LINEAR,
            max_level=5,
            skill_tree_branches=0,
        ),
        "economy": EconomySystemSpec(currencies=("gold", "gems")),
        "ai_behavior": AIBehaviorSpec(entity_type="guard", behaviors=("raise_alarm",)),
    }


def _steps() -> tuple[ReplayStep, ...]:
    return (
        ReplayStep(
            kind="economy",
            action="transact",
            at_tick=0,
            payload={"currency": "gold", "delta": 50},
        ),
        ReplayStep(
            kind="combat",
            action="strike",
            at_tick=1,
            payload={"actor": "hero", "target": "slime", "base_damage": 12, "status": "poison"},
        ),
        ReplayStep(
            kind="progression",
            action="award_xp",
            at_tick=1,
            payload={"amount": 250},
        ),
        ReplayStep(
            kind="ai_behavior",
            action="transition",
            at_tick=2,
            payload={"to": "alert"},
        ),
        ReplayStep(
            kind="economy",
            action="transact",
            at_tick=2,
            payload={"currency": "gold", "delta": -15},
        ),
        ReplayStep(
            kind="combat",
            action="strike",
            at_tick=4,
            payload={"actor": "hero", "target": "slime", "base_damage": 8},
        ),
    )


def _record(**overrides: object):
    payload = {"seed": 42, "tick": 0, "steps": _steps(), **_systems(), **overrides}
    return _replay().record(**payload)  # type: ignore[arg-type]


def test_identical_inputs_seed_and_version_yield_identical_digests() -> None:
    first = _record()
    second = _record()

    assert first.schema == REPLAY_SCHEMA
    assert first.schema_version == REPLAY_SCHEMA_VERSION == 1
    assert first.spec_digest == second.spec_digest
    assert first.state_digest == second.state_digest
    assert first.result_digest == second.result_digest
    assert first.step_digests == second.step_digests
    assert len(first.spec_digest) == 64
    assert first.result_digest != first.state_digest


def test_replay_of_recorded_trace_is_stable_and_round_trips() -> None:
    recorded = _record()
    engine = _replay()
    dumped = engine.dumps(recorded)
    loaded = engine.loads(dumped)
    replayed = engine.replay(loaded)

    assert dumped == canonical_dumps(json.loads(dumped))
    assert loaded.result_digest == recorded.result_digest
    assert replayed.result_digest == recorded.result_digest
    assert engine.compare(recorded, replayed).identical is True


def test_mechanics_uuid_noise_does_not_leak_into_digests(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = count()
    monkeypatch.setattr(
        "skeleton.game.mechanics.uuid.uuid4",
        lambda: uuid.UUID(int=next(ids) + 1),
    )
    first = _record()
    second = _record()
    assert first.spec_digest == second.spec_digest
    assert first.result_digest == second.result_digest


def test_seed_change_is_detected_as_divergence() -> None:
    baseline = _record(seed=42)
    mutated = _record(seed=43)
    report = _replay().compare(baseline, mutated)

    assert report.identical is False
    fields = {item.field for item in report.mismatches}
    assert "seed" in fields
    assert "result_digest" in fields
    with pytest.raises(GameReplayError, match="divergent mechanics execution") as caught:
        report.reject_if_divergent()
    assert caught.value.context["reason"] == "divergence"
    assert caught.value.code == "GAME.REPLAY"


def test_step_payload_and_order_divergence_are_detected() -> None:
    baseline = _record()
    payload_changed = _record(
        steps=(
            ReplayStep(
                kind="economy",
                action="transact",
                at_tick=0,
                payload={"currency": "gold", "delta": 51},
            ),
            *_steps()[1:],
        )
    )
    # Combat and XP share at_tick=1, so swapping them is a legal reorder.
    original = _steps()
    reordered = _record(
        steps=(original[0], original[2], original[1], *original[3:])
    )

    payload_report = _replay().compare(baseline, payload_changed)
    order_report = _replay().compare(baseline, reordered)
    assert payload_report.identical is False
    assert order_report.identical is False
    assert "state_digest" in {item.field for item in payload_report.mismatches}
    assert "steps" in {item.field for item in order_report.mismatches}


def test_time_regression_fail_closed() -> None:
    with pytest.raises(GameReplayError, match="replay time went backwards") as caught:
        _record(steps=(_steps()[1], _steps()[0]))
    assert caught.value.context["reason"] == "time_regression"


def test_replay_rejects_tampered_result_digest() -> None:
    recorded = _record()
    tampered = dict(recorded.to_canonical())
    tampered["result_digest"] = "a" * 64
    with pytest.raises(GameReplayError, match="divergent mechanics execution") as caught:
        _replay().replay(tampered)
    assert caught.value.context["reason"] == "divergence"


def test_version_and_schema_mismatch_fail_closed() -> None:
    recorded = _record().to_canonical()
    versioned = dict(recorded)
    versioned["schema_version"] = REPLAY_SCHEMA_VERSION + 1
    foreign = dict(recorded)
    foreign["schema"] = "game.mechanics.replay.other"

    with pytest.raises(GameReplayError, match="incompatible replay schema") as version_error:
        parse_trace(versioned)
    with pytest.raises(GameReplayError, match="incompatible replay schema") as schema_error:
        _replay().replay(foreign)
    assert version_error.value.context["reason"] == "version_mismatch"
    assert schema_error.value.context["reason"] == "version_mismatch"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.pop("seed"),
        lambda payload: payload.__setitem__("seed", True),
        lambda payload: payload.__setitem__("tick", 0.5),
        lambda payload: payload.__setitem__("extra", 1),
        lambda payload: payload.__setitem__("steps", {"kind": "combat"}),
        lambda payload: payload["steps"][0].__setitem__("kind", "networking"),
        lambda payload: payload["steps"][0]["payload"].__setitem__("delta", 1.25),
        lambda payload: payload.__setitem__("spec_digest", "not-a-digest"),
        lambda payload: None,
    ],
)
def test_malformed_traces_fail_closed(mutator) -> None:
    payload = _record().to_canonical()
    mutated = mutator(payload)
    raw: object
    if mutated is None:
        raw = "{"
    else:
        raw = payload
    with pytest.raises(GameReplayError) as caught:
        parse_trace(raw)  # type: ignore[arg-type]
    assert caught.value.context["reason"] in {"malformed_trace", "unknown_kind", "non_canonical_json"}


def test_illegal_ai_transition_and_unknown_currency_fail_closed() -> None:
    with pytest.raises(GameReplayError, match="illegal AI-behavior transition") as ai_error:
        _record(
            steps=(
                ReplayStep(
                    kind="ai_behavior",
                    action="transition",
                    at_tick=0,
                    payload={"to": "attack"},
                ),
            )
        )
    with pytest.raises(GameReplayError, match="unknown currency"):
        _record(
            steps=(
                ReplayStep(
                    kind="economy",
                    action="transact",
                    at_tick=0,
                    payload={"currency": "souls", "delta": 1},
                ),
            )
        )
    assert ai_error.value.context["reason"] == "illegal_transition"
    assert ai_error.value.context["from"] == "idle"


def test_explicit_clock_and_seed_never_read_process_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("process global used")

    monkeypatch.setattr(time, "time", boom)
    monkeypatch.setattr(time, "monotonic", boom)
    monkeypatch.setattr(random, "random", boom)
    monkeypatch.setattr(random, "randint", boom)
    monkeypatch.setattr(random, "randrange", boom)

    recorded = _record(seed=7, tick=0)
    replayed = _replay().replay(recorded)
    assert recorded.result_digest == replayed.result_digest
    assert recorded.tick == 0
    assert recorded.seed == 7
    assert [step.at_tick for step in recorded.steps] == [0, 1, 1, 2, 2, 4]


def test_canonical_serialization_is_key_order_invariant() -> None:
    recorded = _record()
    as_dict = recorded.to_canonical()
    shuffled = {
        "result_digest": as_dict["result_digest"],
        "schema_version": as_dict["schema_version"],
        "tick": as_dict["tick"],
        "step_digests": as_dict["step_digests"],
        "seed": as_dict["seed"],
        "inputs": as_dict["inputs"],
        "state_digest": as_dict["state_digest"],
        "steps": as_dict["steps"],
        "spec_digest": as_dict["spec_digest"],
        "schema": as_dict["schema"],
    }
    engine = _replay()
    assert engine.dumps(shuffled) == engine.dumps(recorded)
    assert engine.replay(shuffled).result_digest == recorded.result_digest


def test_module_stays_credential_free_and_offline() -> None:
    import skeleton.game.replay as replay_mod

    forbidden = {"httpx", "requests", "aiohttp", "openai", "anthropic", "socket"}
    imported = set(replay_mod.__dict__).intersection(forbidden)
    assert imported == set()
    assert "time" not in replay_mod.__dict__
    assert "random" not in replay_mod.__dict__
