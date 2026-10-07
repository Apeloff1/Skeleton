import math

import pytest

from skeleton.agents.swarm_fairness import FairShareLedger


@pytest.mark.parametrize("value", [0, -1, True, False, 1.5, math.nan, math.inf, -math.inf, "2"])
def test_default_weight_rejects_non_positive_or_non_integer_values(value: object) -> None:
    with pytest.raises(ValueError, match="default_weight must be a positive integer"):
        FairShareLedger(default_weight=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, -1, True, False, 1.5, math.nan, math.inf, -math.inf, "2"])
def test_configure_rejects_invalid_weight_without_mutating_existing_share(value: object) -> None:
    ledger = FairShareLedger()
    original = ledger.configure("tenant", weight=3)
    ledger.admit("tenant")

    with pytest.raises(ValueError, match="weight must be a positive integer"):
        ledger.configure("tenant", weight=value)  # type: ignore[arg-type]

    snapshot = ledger.snapshot()["tenant"]
    assert snapshot["weight"] == original.weight
    assert snapshot["admitted"] == 1
    assert snapshot["inflight"] == 1


def test_valid_weight_preserves_existing_accounting() -> None:
    ledger = FairShareLedger(default_weight=2)
    ledger.admit("tenant")
    updated = ledger.configure("tenant", weight=5)

    assert updated.weight == 5
    assert updated.admitted == 1
    assert updated.inflight == 1
    assert updated.completed == 0
    assert ledger.snapshot()["tenant"]["virtual_load"] == pytest.approx(0.2)
