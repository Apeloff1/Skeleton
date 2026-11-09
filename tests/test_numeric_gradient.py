"""A zero finite-difference step must not divide by zero."""

import pytest

from skeleton.intelligence.metalearning import MetaLearner
from skeleton.intelligence._tensor import Tensor


def test_zero_epsilon_is_rejected() -> None:
    learner = MetaLearner(parameter_dim=2)
    params = Tensor([1.0, 2.0], (2,))
    with pytest.raises(ValueError):
        learner._numerical_gradient(params, lambda tensor: sum(tensor.data), epsilon=0.0)
