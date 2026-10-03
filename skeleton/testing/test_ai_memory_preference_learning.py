from __future__ import annotations

import math

from skeleton.memory.mag import PreferenceEmbedding as CanonicalPreferenceEmbedding
from skeleton.ai.runtime.memory.mag import (
    PreferenceEmbedding as AIPreferenceEmbedding,
)


def _exercise(embedding_type):
    preference=embedding_type(dimension=2)
    preference.update([1.0,0.0],weight=3.0)
    preference.update([0.0,1.0],weight=1.0)
    return preference


def test_large_first_weight_cannot_overshoot_observation() -> None:
    for embedding_type in (CanonicalPreferenceEmbedding,AIPreferenceEmbedding):
        preference=embedding_type(dimension=2)
        preference.update([0.25,-0.5],weight=100.0)

        assert preference.vector==[0.25,-0.5]
        assert preference.total_weight==100.0
        assert preference.update_count==1


def test_weighted_updates_produce_true_weighted_mean() -> None:
    for embedding_type in (CanonicalPreferenceEmbedding,AIPreferenceEmbedding):
        preference=_exercise(embedding_type)

        assert math.isclose(preference.vector[0],0.75,abs_tol=1e-12)
        assert math.isclose(preference.vector[1],0.25,abs_tol=1e-12)
        assert preference.total_weight==4.0
        assert preference.update_count==2


def test_weighted_preference_learning_is_order_stable() -> None:
    for embedding_type in (CanonicalPreferenceEmbedding,AIPreferenceEmbedding):
        forward=embedding_type(dimension=2)
        forward.update([1.0,0.0],weight=3.0)
        forward.update([0.0,1.0],weight=1.0)

        reverse=embedding_type(dimension=2)
        reverse.update([0.0,1.0],weight=1.0)
        reverse.update([1.0,0.0],weight=3.0)

        assert all(
            math.isclose(left,right,abs_tol=1e-12)
            for left,right in zip(forward.vector,reverse.vector)
        )


def test_fractional_weights_preserve_convex_hull() -> None:
    for embedding_type in (CanonicalPreferenceEmbedding,AIPreferenceEmbedding):
        preference=embedding_type(dimension=1)
        preference.update([1.0],weight=0.1)
        preference.update([-1.0],weight=0.9)

        assert -1.0 <= preference.vector[0] <= 1.0
        assert math.isclose(preference.vector[0],-0.8,abs_tol=1e-12)
