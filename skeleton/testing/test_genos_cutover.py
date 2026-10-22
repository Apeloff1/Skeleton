"""Tests for genos cutover starter."""
import pytest
from skeleton.foundation.architecture.genos_cutover import ownership_card, bind_owner, CutoverError

def test_unbound_card():
    card = ownership_card(bound=False)
    assert card["status"] == "unresolved"
    assert card["stored_prose"] == 0

def test_bind_ok():
    d = bind_owner("skeleton.simulation.genos")
    assert len(d) == 64

def test_bad_owner():
    with pytest.raises(CutoverError):
        bind_owner("bad/path")
