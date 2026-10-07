"""Alpha zero disables the adapter, and rank follows the matrix."""

import pytest

from skeleton.intelligence.parametric_lora import ParametricLoRAWriteBack


def test_alpha_zero_is_kept_and_rank_matches_the_matrix() -> None:
    writer = ParametricLoRAWriteBack()
    matrix_a = [[1.0, 0.0], [0.0, 1.0]]
    matrix_b = [[1.0, 0.0], [0.0, 1.0]]
    layer = writer.add_layer("attn", matrix_a, matrix_b, alpha=0.0)
    assert layer.rank == 2
    assert layer.alpha == 0.0
    assert layer.effective_weight() == [[0.0, 0.0], [0.0, 0.0]]
    with pytest.raises(ValueError):
        writer.add_layer("bad", matrix_a, matrix_b, rank=0)
