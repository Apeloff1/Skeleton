"""Tests for sheaf facade starter."""
import pytest
from skeleton.knowledge.graphs.sheaf_facade import capabilities, promote_section, SheafFacadeError

def test_capabilities_card():
    card = capabilities()
    assert card["stored_prose"] == 0
    assert card["kind"] == "sheaf_facade"
    assert "citation" in card

def test_promote_bound():
    d = promote_section("sec-1", bound=True)
    assert len(d) == 64

def test_promote_unbound():
    with pytest.raises(SheafFacadeError):
        promote_section("sec-2", bound=False)
