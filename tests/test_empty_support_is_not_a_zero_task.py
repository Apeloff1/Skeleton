"""An empty support set is not a task of zeros, and a short vector is not padded."""

import pytest

from skeleton.intelligence.metalearning import MetaLearner


def test_support_must_fill_the_parameter_dimension() -> None:
    learner = MetaLearner(parameter_dim=2)
    with pytest.raises(ValueError):
        learner.embed_task([], "empty")
    with pytest.raises(ValueError):
        learner.embed_task([{"flag": True, "name": "cat"}], "flags")
    with pytest.raises(ValueError):
        learner.embed_task([{"x": 1.0}], "short")
    task = learner.embed_task([{"x": 1.0, "y": 2.0}], "ready")
    assert task.embedding.data == [1.0, 2.0]
    with pytest.raises(ValueError):
        MetaLearner(parameter_dim=True)
