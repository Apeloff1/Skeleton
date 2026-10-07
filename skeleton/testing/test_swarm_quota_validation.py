import math

import pytest

from skeleton.agents.swarm_quota import Quota, QuotaLedger


@pytest.mark.parametrize("value", [0, -1])
def test_quota_rejects_non_positive_limits(value: int) -> None:
    with pytest.raises(ValueError):
        Quota(max_queued=value)


@pytest.mark.parametrize("value", [True, 1.5, math.nan, math.inf])
def test_quota_rejects_non_integer_limits(value: object) -> None:
    with pytest.raises(TypeError):
        Quota(max_leased=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["queued", "leased", "payload_bytes"])
@pytest.mark.parametrize("value", [True, 1.5, math.nan, math.inf])
def test_reserve_rejects_non_integer_deltas_without_mutation(field: str, value: object) -> None:
    ledger = QuotaLedger()
    kwargs = {field: value}
    with pytest.raises(TypeError):
        ledger.reserve("tenant", **kwargs)  # type: ignore[arg-type]
    assert ledger.snapshot() == {}


def test_release_rejects_unknown_fields_without_mutation() -> None:
    ledger = QuotaLedger()
    ledger.reserve("tenant", queued=1, payload_bytes=8)
    before = ledger.snapshot()
    with pytest.raises(TypeError, match="unknown quota release fields"):
        ledger.release("tenant", queued=1, typo=1)
    assert ledger.snapshot() == before


def test_release_rejects_non_integer_amount_without_mutation() -> None:
    ledger = QuotaLedger()
    ledger.reserve("tenant", queued=1, payload_bytes=8)
    before = ledger.snapshot()
    with pytest.raises(TypeError):
        ledger.release("tenant", queued=1.0)  # type: ignore[arg-type]
    assert ledger.snapshot() == before
