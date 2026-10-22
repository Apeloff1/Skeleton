"""Tests for emulation mapping starter."""
import pytest
from skeleton.native.emulation_mapping import EmulationFleet, EmulationError

def test_register_and_qualify():
    fleet = EmulationFleet()
    card = fleet.register("nes")
    assert not card.mapped
    qualified = fleet.qualify("nes", core=True, firmware=True, sdk=True)
    assert qualified.mapped
    assert fleet.inventory()["mapped"] == 1

def test_partial_qualify():
    fleet = EmulationFleet()
    fleet.register("snes")
    card = fleet.qualify("snes", core=True, firmware=False, sdk=True)
    assert not card.mapped

def test_unknown_target():
    fleet = EmulationFleet()
    with pytest.raises(EmulationError):
        fleet.qualify("unknown", True, True, True)
