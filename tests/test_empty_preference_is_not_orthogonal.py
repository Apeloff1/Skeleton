"""Two untouched preference vectors are not a measured similarity of zero."""

import pytest

from skeleton.memory.mag import PreferenceEmbedding


def test_unupdated_preferences_do_not_score_zero() -> None:
    with pytest.raises(ValueError):
        PreferenceEmbedding(True)
    left = PreferenceEmbedding(2)
    right = PreferenceEmbedding(2)
    with pytest.raises(ValueError):
        left.similarity(right)
    with pytest.raises(ValueError):
        left.update([1.0, True])
    left.update([1.0, 0.0])
    right.update([1.0, 0.0])
    assert left.similarity(right) == pytest.approx(1.0)
    zero = PreferenceEmbedding(2)
    zero.update([0.0, 0.0])
    with pytest.raises(ValueError):
        left.similarity(zero)
