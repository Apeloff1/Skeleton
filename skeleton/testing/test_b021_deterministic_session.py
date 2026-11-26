"""B021: deterministic loop + mechanics session over the canonical replay contract."""

from __future__ import annotations

import json
import random
import time
from dataclasses import replace

import pytest

from skeleton.game import (
    AIBehaviorSpec,
    CombatStyle,
    CombatSystemSpec,
    DeterministicError,
    DeterministicLoop,
    EconomySystemSpec,
    MechanicsReplay,
    MechanicsSession,
    MechanicsSessionError,
    ProgressionStyle,
    ProgressionSystemSpec,
    ReplayStep,
    SeededDraws,
    SessionPlan,
    assert_identical_runs,
    bounded_draw,
    seeded_skirmish_steps,
)
from skeleton.game.deterministic import LoopFrame


def _plan(seed: int = 42, **overrides: object) -> SessionPlan:
    base = dict(
        seed=seed,
        tick=0,
        steps=seeded_skirmish_steps(42, rounds=4)
        + (
            ReplayStep("progression", "award_xp", 5, {"amount": 250}),
            ReplayStep("ai_behavior", "transition", 6, {"to": "alert"}),
        ),
        combat=CombatSystemSpec(style=CombatStyle.TURN_BASED),
        progression=ProgressionSystemSpec(
            style=ProgressionStyle.LINEAR, max_level=5, skill_tree_branches=0
        ),
        economy=EconomySystemSpec(currencies=("gold", "gems")),
        ai_behavior=AIBehaviorSpec(entity_type="guard", behaviors=("raise_alarm",)),
    )
    base.update(overrides)
    return SessionPlan(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------- bounded draws


def test_bounded_draw_is_pure_and_in_range() -> None:
    values = [bounded_draw(7, 3, "combat", i, 10) for i in range(50)]
    assert values == [bounded_draw(7, 3, "combat", i, 10) for i in range(50)]
    assert all(0 <= v < 10 for v in values)
    assert len(set(values)) > 1


def test_bounded_draw_separates_seed_tick_lane_index() -> None:
    base = bounded_draw(7, 3, "combat", 0, 2**32)
    assert base != bounded_draw(8, 3, "combat", 0, 2**32)
    assert base != bounded_draw(7, 4, "combat", 0, 2**32)
    assert base != bounded_draw(7, 3, "loot", 0, 2**32)
    assert base != bounded_draw(7, 3, "combat", 1, 2**32)


@pytest.mark.parametrize(
    "args",
    [
        (-1, 0, "a", 0, 2),
        (2**31, 0, "a", 0, 2),
        (0, -1, "a", 0, 2),
        (0, 1_000_001, "a", 0, 2),
        (0, 0, "Bad Lane", 0, 2),
        (0, 0, "a", -1, 2),
        (0, 0, "a", 0, 0),
        (0, 0, "a", 0, 2**32 + 1),
        (True, 0, "a", 0, 2),
        (0, 0, "a", 0, 2.0),
    ],
)
def test_bounded_draw_fails_closed(args: tuple) -> None:
    with pytest.raises(DeterministicError):
        bounded_draw(*args)


def test_bounded_draw_ignores_process_entropy(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = bounded_draw(1, 1, "x", 0, 1000)
    monkeypatch.setattr(random, "random", lambda: 0.123)
    monkeypatch.setattr(time, "time", lambda: 1.0)
    assert bounded_draw(1, 1, "x", 0, 1000) == expected


# ---------------------------------------------------------------- seeded draws


def test_lanes_are_isolated() -> None:
    a = SeededDraws(5)
    combat_only = [a.draw("combat", 100) for _ in range(5)]
    b = SeededDraws(5)
    interleaved = []
    for _ in range(5):
        b.draw("loot", 100)
        interleaved.append(b.draw("combat", 100))
    assert combat_only == interleaved


def test_snapshot_restore_continues_sequence() -> None:
    a = SeededDraws(9)
    for _ in range(3):
        a.draw("ai", 50)
    snap = json.loads(json.dumps(a.snapshot()))
    b = SeededDraws.restore(snap)
    assert b.digest() == a.digest()
    assert [a.draw("ai", 50) for _ in range(4)] == [b.draw("ai", 50) for _ in range(4)]


def test_restore_rejects_tampered_snapshot() -> None:
    snap = SeededDraws(1).snapshot()
    with pytest.raises(DeterministicError):
        SeededDraws.restore({**snap, "schema_version": 2})
    with pytest.raises(DeterministicError):
        SeededDraws.restore({**snap, "extra": 1})
    with pytest.raises(DeterministicError):
        SeededDraws.restore({**snap, "counters": {"ok": -1}})


def test_chance_bounds() -> None:
    d = SeededDraws(3)
    assert not any(d.chance("c", 0, 10) for _ in range(20))
    assert all(d.chance("c", 10, 10) for _ in range(20))
    with pytest.raises(DeterministicError):
        d.chance("c", 11, 10)


# ---------------------------------------------------------------- loop


def _walker(state, tick, draws):
    step = draws.draw("walk", 3) - 1
    return {"x": state["x"] + step, "visits": state["visits"] + [tick]}


def test_loop_is_reproducible_and_verifiable() -> None:
    loop = DeterministicLoop(_walker)
    first = loop.run(seed=11, ticks=20, initial_state={"x": 0, "visits": []})
    second = loop.run(seed=11, ticks=20, initial_state={"x": 0, "visits": []})
    assert first.trace_digest == second.trace_digest
    assert first.final_state == second.final_state
    assert [f.tick for f in first.frames] == list(range(1, 21))
    assert DeterministicLoop.trace_digest(first) == first.trace_digest
    assert loop.run(seed=12, ticks=20, initial_state={"x": 0, "visits": []}).trace_digest != (
        first.trace_digest
    )


def test_loop_detects_tampered_frame() -> None:
    run = DeterministicLoop(_walker).run(seed=1, ticks=5, initial_state={"x": 0, "visits": []})
    frames = list(run.frames)
    frames[2] = LoopFrame(frames[2].tick, "f" * 64, frames[2].chain_digest)
    with pytest.raises(DeterministicError):
        DeterministicLoop.trace_digest(replace(run, frames=tuple(frames)))
    with pytest.raises(DeterministicError):
        DeterministicLoop.trace_digest(replace(run, entropy_digest="0" * 64))


def test_loop_step_cannot_mutate_caller_state() -> None:
    initial = {"x": 0, "visits": []}

    def mutate(state, tick, draws):
        state["visits"].append(tick)
        return state

    DeterministicLoop(mutate).run(seed=0, ticks=3, initial_state=initial)
    assert initial == {"x": 0, "visits": []}


@pytest.mark.parametrize(
    "bad",
    [lambda s, t, d: [1], lambda s, t, d: {"v": float("nan")}, lambda s, t, d: {"v": {1, 2}}],
)
def test_loop_fails_closed_on_non_canonical_state(bad) -> None:
    with pytest.raises(DeterministicError):
        DeterministicLoop(bad).run(seed=0, ticks=1, initial_state={})


def test_loop_budget_fails_closed() -> None:
    loop = DeterministicLoop(_walker, max_ticks=10)
    with pytest.raises(DeterministicError):
        loop.run(seed=0, ticks=11, initial_state={"x": 0, "visits": []})
    with pytest.raises(DeterministicError):
        loop.run(seed=0, ticks=5, start_tick=999_999, initial_state={"x": 0, "visits": []})


def test_assert_identical_runs_catches_hidden_entropy() -> None:
    loop = DeterministicLoop(_walker)
    digest = assert_identical_runs(
        lambda: loop.run(seed=4, ticks=8, initial_state={"x": 0, "visits": []}), runs=4
    )
    assert len(digest) == 64
    leak = iter(range(100))

    def impure(state, tick, draws):
        return {"x": state["x"] + next(leak)}

    with pytest.raises(DeterministicError) as info:
        assert_identical_runs(
            lambda: DeterministicLoop(impure).run(seed=4, ticks=3, initial_state={"x": 0})
        )
    assert info.value.context["reason"] == "divergence"
    with pytest.raises(DeterministicError):
        assert_identical_runs(lambda: "not-a-digest")


# ---------------------------------------------------------------- session


def test_session_wraps_existing_replay_contract() -> None:
    plan = _plan()
    session = MechanicsSession()
    trace = session.record(plan)
    direct = MechanicsReplay().record(**plan.record_kwargs())
    assert trace.result_digest == direct.result_digest
    assert session.replay(trace).result_digest == trace.result_digest
    assert session.compare(trace, direct).identical


def test_prove_deterministic() -> None:
    proof = MechanicsSession().prove_deterministic(_plan(), runs=3)
    assert proof.runs == 3 and proof.roundtrip_identical and proof.replay_identical
    assert proof.step_count == 10
    assert proof.digest == MechanicsSession().prove_deterministic(_plan(), runs=3).digest
    assert proof.result_digest != MechanicsSession().prove_deterministic(_plan(seed=43)).result_digest


def test_plan_digest_normalizes_specs_and_mappings() -> None:
    session = MechanicsSession()
    as_spec = _plan()
    as_mapping = _plan(economy={"currencies": ["gold", "gems"], "include_trading": True,
                                "include_crafting": False, "inflation_model": False})
    assert session.plan_digest(as_spec) == session.plan_digest(as_mapping)


def test_envelope_roundtrip_and_tamper() -> None:
    session = MechanicsSession()
    envelope = session.envelope(session.record(_plan()))
    wire = json.loads(json.dumps(envelope))
    assert session.open_envelope(wire).result_digest == envelope["result_digest"]
    tampered = json.loads(json.dumps(envelope))
    tampered["trace"]["steps"][0]["payload"]["base_damage"] += 1
    with pytest.raises(MechanicsSessionError):
        session.open_envelope(tampered)
    with pytest.raises(MechanicsSessionError):
        session.open_envelope({**envelope, "schema_version": 2})


def test_seeded_skirmish_lanes_are_stable() -> None:
    steps = seeded_skirmish_steps(77, rounds=3)
    assert steps == seeded_skirmish_steps(77, rounds=3)
    assert [s.kind for s in steps] == ["combat", "economy"] * 3
    assert steps != seeded_skirmish_steps(78, rounds=3)
    with pytest.raises(MechanicsSessionError):
        seeded_skirmish_steps(77, rounds=0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"seed": -1},
        {"tick": 1_000_001},
        {"steps": ()},
        {"steps": [ReplayStep("economy", "transact", 0, {"currency": "gold", "delta": 1})]},
        {"combat": None, "progression": None, "economy": None, "ai_behavior": None},
    ],
)
def test_session_plan_fails_closed(overrides: dict) -> None:
    with pytest.raises(MechanicsSessionError):
        _plan(**overrides)


def test_prove_deterministic_rejects_bad_runs() -> None:
    with pytest.raises(MechanicsSessionError):
        MechanicsSession().prove_deterministic(_plan(), runs=1)
