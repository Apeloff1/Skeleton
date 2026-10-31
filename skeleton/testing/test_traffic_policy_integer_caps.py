"""Traffic admission configuration must reject malformed capacity values."""
from __future__ import annotations

from dataclasses import fields

import pytest

from skeleton.automation.traffic_manager import TrafficManagerError, TrafficPolicy


FIELDS = tuple(field.name for field in fields(TrafficPolicy))


@pytest.mark.parametrize("name", FIELDS)
@pytest.mark.parametrize(
    "invalid",
    [0, -1, True, False, 1.5, float("nan"), float("inf"), "10", None],
)
def test_every_capacity_or_cooldown_rejects_nonpositive_or_noninteger_values(
    name: str, invalid: object,
) -> None:
    with pytest.raises(TrafficManagerError, match="positive integers"):
        TrafficPolicy(**{name: invalid})


def test_reviewed_integer_defaults_are_accepted() -> None:
    policy = TrafficPolicy()
    assert len(FIELDS) == 9
    assert all(type(getattr(policy, field)) is int for field in FIELDS)
    assert all(getattr(policy, field) > 0 for field in FIELDS)


def test_valid_integer_overrides_are_preserved_without_coercion() -> None:
    original = TrafficPolicy()
    values = {name: getattr(original, name) + 1 for name in FIELDS}
    changed = TrafficPolicy(**values)
    assert {name: getattr(changed, name) for name in FIELDS} == values
