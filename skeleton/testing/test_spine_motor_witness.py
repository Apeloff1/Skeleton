from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.persistence.spine_dispatch_witness import SpineDispatchWitness, SpineDispatchWitnessError
from skeleton.persistence.spine_motor_witness import SpineMotorWitness, SpineMotorWitnessError


def test_spine_modules_do_not_import_motor() -> None:
    card = SpineMotorWitness().card(Path("skeleton/persistence"))
    assert card["driver_imports"] == 0
    assert card["live_motor"] is False
    assert card["scanned"] > 0
    assert card["completion_checkbox"] is False


def test_planted_motor_import_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "spine_bad.py").write_text("import motor\n")
    with pytest.raises(SpineMotorWitnessError):
        SpineMotorWitness().card(tmp_path)


class _Runtime:
    def start_dispatcher(self) -> None:
        raise AssertionError("witness must not call start_dispatcher")

    def dispatcher_running(self) -> bool:
        return False


def test_dispatch_witness_does_not_start() -> None:
    card = SpineDispatchWitness().card(_Runtime())
    assert card["called"] is False
    assert card["dispatcher_running"] is False
    assert card["runtime_replaced"] is False

    class Running(_Runtime):
        def dispatcher_running(self) -> bool:
            return True

    with pytest.raises(SpineDispatchWitnessError):
        SpineDispatchWitness().card(Running())
