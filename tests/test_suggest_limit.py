"""A negative suggestion limit must not mean 'drop the tail'."""

import pytest

from skeleton.retrieval.suggest import Suggester


def test_negative_limit_is_rejected() -> None:
    suggester = Suggester(["alpha", "alpine", "beta"])
    with pytest.raises(ValueError):
        suggester.suggest("al", limit=-1)
    assert suggester.suggest("al", limit=0) == ()
    assert suggester.suggest("al", limit=1) == ("alpha",)
