import pytest
from skeleton.security.experimental_features import *


def test_experiment_never_claims_production_capability():
    with pytest.raises(PermissionError):
        expose(
            ExperimentalFeature("x", "s", True),
            "shadow",
            ExperimentKillSwitch(False),
        )


def test_kill_switch_stops_exposure():
    exposure = expose(
        ExperimentalFeature("x", "s"),
        "synthetic",
        ExperimentKillSwitch(True),
    )
    assert not exposure.active


def test_nonboolean_kill_switch_rejected():
    with pytest.raises(ValueError):
        ExperimentKillSwitch(0)


def test_kill_switch_is_monotonic_for_existing_exposure():
    exposure = expose(
        ExperimentalFeature("x", "s"),
        "shadow",
        ExperimentKillSwitch(False),
    )
    stopped = apply_kill_switch(exposure, ExperimentKillSwitch(True))
    assert not stopped.active
    still_stopped = apply_kill_switch(stopped, ExperimentKillSwitch(False))
    assert not still_stopped.active


def test_unisolated_traffic_is_rejected():
    with pytest.raises(PermissionError):
        expose(
            ExperimentalFeature("x", "s"),
            "production",
            ExperimentKillSwitch(False),
        )
