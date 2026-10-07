from __future__ import annotations

import pytest

from skeleton.acquired.gaming.tension import (
    TensionConfig,
    TensionModel,
    TensionOutcome,
    TensionState,
)
from skeleton.kernel.events import EventBus


def test_source_tick_equation_is_preserved_without_randomness():
    model = TensionModel()
    state = TensionState(tension=0.2)

    next_state = model.step(
        state,
        resistance=0.5,
        environment_resistance=1.0,
        reel_speed=1.0,
        struggle=False,
    )

    # 0.2 + (0.5*0.08) + (1.0*0.05) - (1.0*0.06)
    assert next_state.tension == pytest.approx(0.23)
    assert next_state.elapsed_seconds == pytest.approx(0.2)
    assert next_state.outcome is TensionOutcome.REELING


def test_struggle_impulse_is_explicit_and_replayable():
    model = TensionModel()
    base = TensionState(tension=0.2)

    calm = model.step(base, resistance=0.5, reel_speed=1.0, struggle=False)
    struggle = model.step(base, resistance=0.5, reel_speed=1.0, struggle=True)

    assert struggle.tension - calm.tension == pytest.approx(0.15)


def test_line_breaks_at_threshold():
    model = TensionModel()
    state = TensionState(tension=0.95)

    result = model.step(
        state,
        resistance=1.0,
        environment_resistance=1.0,
        reel_speed=0.0,
    )
    assert result.outcome is TensionOutcome.LOST
    assert result.tension >= 1.0


def test_catch_requires_minimum_time_and_safe_tension():
    config = TensionConfig(min_reel_seconds=0.4)
    model = TensionModel(config)
    state = TensionState(tension=0.2)

    first = model.step(
        state,
        resistance=0.0,
        environment_resistance=0.0,
        reel_speed=1.0,
    )
    assert first.outcome is TensionOutcome.REELING

    second = model.step(
        first,
        resistance=0.0,
        environment_resistance=0.0,
        reel_speed=1.0,
    )
    assert second.elapsed_seconds == pytest.approx(0.4)
    assert second.outcome is TensionOutcome.CAUGHT


def test_terminal_state_is_idempotent():
    model = TensionModel()
    lost = TensionState(tension=1.0, elapsed_seconds=1.0, outcome=TensionOutcome.LOST)
    assert model.step(lost, resistance=2.0, struggle=True) is lost


def test_dt_normalizes_continuous_load_but_not_discrete_struggle():
    model = TensionModel()
    base = TensionState(tension=0.2)

    full = model.step(
        base,
        resistance=0.5,
        environment_resistance=1.0,
        reel_speed=1.0,
        dt=0.2,
    )
    half = model.step(
        base,
        resistance=0.5,
        environment_resistance=1.0,
        reel_speed=1.0,
        dt=0.1,
    )
    assert half.tension - 0.2 == pytest.approx((full.tension - 0.2) / 2)


def test_terminal_transition_is_published():
    bus = EventBus()
    events = []
    bus.subscribe("acquired.gaming.tension.*", events.append)
    model = TensionModel(bus=bus)

    result = model.step(
        TensionState(tension=0.99),
        resistance=1.0,
        reel_speed=0.0,
    )
    assert result.outcome is TensionOutcome.LOST
    assert [event.topic for event in events] == [
        "acquired.gaming.tension.step",
        "acquired.gaming.tension.lost",
    ]


def test_invalid_config_and_inputs_are_rejected():
    with pytest.raises(ValueError):
        TensionConfig(tick_seconds=0)
    with pytest.raises(ValueError):
        TensionConfig(catch_threshold=1.0, break_threshold=1.0)

    model = TensionModel()
    with pytest.raises(ValueError):
        model.step(TensionState(), resistance=True)
    with pytest.raises(ValueError):
        model.step(TensionState(), resistance=1.0, dt=0)
