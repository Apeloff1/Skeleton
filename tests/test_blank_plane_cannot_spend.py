"""A blank plane cannot spend privacy budget, and a NaN budget is not unlimited."""

import pytest

from skeleton.memory.dp import PrivacyAccountant


def test_a_missing_plane_and_a_nan_budget_do_not_spend() -> None:
    with pytest.raises(ValueError):
        PrivacyAccountant(session_budget=float("nan"))
    with pytest.raises(ValueError):
        PrivacyAccountant(per_plane_budget=True)
    accountant = PrivacyAccountant(session_budget=1.0, per_plane_budget=0.4)
    assert accountant.spend(0.2, "laplace", "count") is False
    assert accountant.spend(float("nan"), "laplace", "count", plane="rag") is False
    assert accountant.remaining() == 1.0
    assert accountant.spend(0.2, "laplace", "count", plane="rag") is True
    assert accountant.spend(0.3, "laplace", "count", plane="rag") is False
    assert accountant.remaining() == pytest.approx(0.8)
