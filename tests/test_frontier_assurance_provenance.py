import pytest

from skeleton.frontier.assurance.provenance import Provenance


def test_provenance_requires_complete_lineage():
    assert Provenance("gameforge-rs", "abc123", "promotion").revision == "abc123"
    with pytest.raises(ValueError):
        Provenance("", "abc123", "promotion")
