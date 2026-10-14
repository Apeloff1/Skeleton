from __future__ import annotations

import random

import pytest

from skeleton.testing.property_invariants import (
    Invariant,
    InvariantRegistry,
    Property,
    PropertyCampaign,
    PropertyContractError,
    integer_toward_zero,
)


def registry() -> InvariantRegistry:
    result = InvariantRegistry()
    result.register(Invariant("balance.nonnegative", "Ledger", "balance >= 0"))
    return result


def test_campaign_replays_same_counterexample_from_seed() -> None:
    prop = Property(
        name="withdrawals",
        invariant="balance.nonnegative",
        generator=lambda rng: rng.randint(-100, 100),
        predicate=lambda value: value >= 0,
        shrinker=integer_toward_zero,
    )
    campaign = PropertyCampaign(registry(), max_cases=100, max_shrinks=32)
    first = campaign.run(prop, seed=73, cases=50)
    second = campaign.run(prop, seed=73, cases=50)
    assert first is not None
    assert first == second
    assert first.seed == 73
    assert first.digest == second.digest


def test_failure_shrinks_to_stable_small_counterexample() -> None:
    prop = Property(
        name="positive",
        invariant="balance.nonnegative",
        generator=lambda rng: -64,
        predicate=lambda value: value >= 0,
        shrinker=integer_toward_zero,
    )
    failure = PropertyCampaign(registry(), max_cases=1).run(prop, seed=1, cases=1)
    assert failure is not None
    assert failure.original == -64
    assert failure.minimal == -1


def test_unknown_invariant_fails_closed_before_generation() -> None:
    called = False

    def generator(_: random.Random) -> int:
        nonlocal called
        called = True
        return 1

    prop = Property("orphan", "missing.invariant", generator, lambda _: True)
    with pytest.raises(PropertyContractError, match="unknown invariant"):
        PropertyCampaign(registry()).run(prop, seed=1, cases=1)
    assert called is False


def test_campaign_budget_is_enforced() -> None:
    prop = Property("bounded", "balance.nonnegative", lambda rng: 1, lambda _: True)
    with pytest.raises(PropertyContractError, match="budget"):
        PropertyCampaign(registry(), max_cases=2).run(prop, seed=1, cases=3)


def test_predicate_must_return_boolean() -> None:
    prop = Property("typed", "balance.nonnegative", lambda rng: 1, lambda _: 1)  # type: ignore[arg-type]
    with pytest.raises(PropertyContractError, match="bool"):
        PropertyCampaign(registry(), max_cases=1).run(prop, seed=1, cases=1)


def test_duplicate_invariant_is_rejected() -> None:
    items = registry()
    with pytest.raises(PropertyContractError, match="duplicate"):
        items.register(Invariant("balance.nonnegative", "Other", "x"))
