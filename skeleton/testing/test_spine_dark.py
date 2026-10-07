from __future__ import annotations

import pytest

from skeleton.persistence.spine_dark import SpineDark, SpineDarkError
from skeleton.persistence.spine_epoch_witness import SpineEpochWitness, SpineEpochWitnessError


def test_dark_card_stays_unwired() -> None:
    card = SpineDark().card(
        {"live_motor": False, "driver_imports": 0},
        {"called": False, "dispatcher_running": False},
        {"merged": False, "ci_green": False},
    )
    assert card["hit"] is False
    assert card["live_motor"] is False
    assert card["merged"] is False
    assert card["apply_landed"] is False
    assert card["completion_checkbox"] is False


def test_dark_card_refuses_a_green_input() -> None:
    with pytest.raises(SpineDarkError):
        SpineDark().card(
            {"live_motor": True, "driver_imports": 0},
            {"called": False, "dispatcher_running": False},
            {"merged": False, "ci_green": False},
        )


def test_epoch_witness_refuses_a_moved_fence() -> None:
    card = SpineEpochWitness().card(epoch_before=0, epoch_after=0, side={"kind": "spine_provider_probe"})
    assert card["moved"] is False
    assert card["epoch_before"] == card["epoch_after"] == 0
    with pytest.raises(SpineEpochWitnessError):
        SpineEpochWitness().card(epoch_before=0, epoch_after=1, side={"kind": "spine_provider_probe"})
