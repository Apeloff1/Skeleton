"""An empty tensor has no mean, and true is not a tensor value."""

import pytest

from skeleton.intelligence._tensor import Tensor


def test_empty_tensor_has_no_mean() -> None:
    empty = Tensor([], (0,))
    with pytest.raises(ValueError):
        empty.mean()
    with pytest.raises(ValueError):
        empty.std()
    with pytest.raises(ValueError):
        Tensor([True], (1,))
    with pytest.raises(ValueError):
        Tensor([1.0], (True,))
    one = Tensor([4.0], (1,))
    assert one.mean() == 4.0
    with pytest.raises(ValueError):
        one.std()
    pair = Tensor([1.0, 3.0], (2,))
    assert pair.mean() == 2.0
    assert pair.std() == pytest.approx(1.41421356237)
