"""Neural match must not cosine-compare vectors of different lengths."""

import pytest

from skeleton.intelligence.neurosymbolic import NeuralSymbolicEngine
from skeleton.intelligence._tensor import Tensor


def test_cosine_rejects_a_dimension_mismatch() -> None:
    engine = NeuralSymbolicEngine()
    engine.add_fact("cat", Tensor([1.0, 0.0], (2,)))
    engine.add_fact("dog", Tensor([1.0, 0.0, 0.0], (3,)))
    with pytest.raises(ValueError):
        engine._neural_match("cat", ["dog"])
